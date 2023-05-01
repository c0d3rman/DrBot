import re
import praw
from copy import deepcopy
from datetime import datetime
from dateutil.relativedelta import relativedelta
from .config import settings
from .log import log
from .util import user_exists, get_thing, send_modmail
from .Handler import Handler
from .PointMap import PointMap


class PointsHandler(Handler):
    def init(self, data_store: dict, reddit: praw.Reddit):
        super().init(data_store, reddit)
        self.point_map = PointMap(reddit)

    def handle(self, mod_action):
        # If a removal reason is added, add the violation to the user's record
        if mod_action.action == "addremovalreason":
            self.add(mod_action)
        # If a comment has been re-approved, remove it from the record
        elif mod_action.action == "approvecomment":
            removed = self.remove_violation(mod_action.target_author, mod_action.target_fullname, should_exist=False)
            if not removed is None:
                log.info(f"-{removed['cost']} to u/{mod_action.target_author} from {mod_action.target_fullname} (re-approved), now at {self.get_user_total(mod_action.target_author)}.")
        # If a user finishes a ban, henceforth ignore all violations from before that ban ended
        elif mod_action.action == "unbanuser":
            if mod_action.target_author in self.data_store and "record" in self.data_store[mod_action.target_author]:
                self.data_store[mod_action.target_author]["record"]["cutoff"] = datetime.fromtimestamp(mod_action.created_utc)

    def add(self, mod_action):
        """Add points for a removal.
        Returns true if it was added and false if it wasn't (e.g. because it costs 0 points).
        Triggers a ban if the addition causes the user goes over the threshold."""
        removal_reason_id = mod_action.description
        violation_fullname = mod_action.target_fullname
        username = mod_action.target_author
        removal_time = datetime.fromtimestamp(mod_action.created_utc)
        violation = None  # For if/when we fetch the violation, so we don't do it twice

        log.debug(f"Processing removal of {violation_fullname} with reason: {removal_reason_id}")

        # Skip submissions by u/[deleted]
        if username == "[deleted]":
            log.debug(f"{violation_fullname}'s author has deleted their account; skipping.")
            return False

        # Get point cost
        point_cost = self.point_map[removal_reason_id]
        if settings.custom_point_mod_notes:  # Check for manual point exception in mod note
            if violation is None:
                violation = get_thing(self.reddit, mod_action.target_fullname)
            if not violation.mod_note is None:
                result = re.search(r"\[(\d+)\]", violation.mod_note)
                if not result is None:
                    point_cost = int(result.group(1))
                    log.info(f"{violation_fullname} has a custom point cost of {point_cost} as set by its mod note.")
        if point_cost == 0:
            log.debug(f"{violation_fullname} costs 0 points; skipping.")
            return False

        # Check if this submission is already accounted for
        if username in self.data_store and violation_fullname in self.data_store[username]["violations"]:
            log.debug(f"{violation_fullname} already accounted for; skipping.")
            return False

        # Safe mode checks
        if settings.safe_mode:
            # Check if the user's account was deleted/suspended
            if not user_exists(self.reddit, username):
                log.debug(f"u/{username}'s account doesn't exist anymore; skipping.")
                return False

            # If exclude_mods is on, check if the user is a mod
            if settings.exclude_mods and len(self.reddit.subreddit(settings.subreddit).moderator(username)) > 0:
                log.debug(f"u/{username} is a mod; skipping.")
                return False

            # Check if this submission has already been re-approved
            if violation is None:  # Technically we can do this for free if custom_point_mod_notes is on, but we don't unless safe_mode is active for consistency
                violation = get_thing(self.reddit, mod_action.target_fullname)
            if not violation.removed:
                log.debug(f"{violation_fullname} already re-approved; skipping.")

        # Calculate expiration
        expiration_duration = self.point_map.get_expiration(removal_reason_id)
        if not expiration_duration is None:
            if violation is None:
                violation = get_thing(self.reddit, mod_action.target_fullname)
            expiration = datetime.fromtimestamp(violation.created_utc) + relativedelta(months=self.point_map.get_expiration(removal_reason_id))
            # Check if this submission has already expired
            if datetime.now() >= expiration:
                log.debug(f"{violation_fullname} already expired before it was added; skipping.")
                return False

        # Add the submission to the user's record
        if not username in self.data_store:
            self.data_store[username] = {"violations": {}}
        elif violation_fullname in self.data_store[username]["violations"]:
            log.warning(f"Can't add {violation_fullname} to u/{username} (already exists).")
            return False
        self.data_store[username]["violations"][violation_fullname] = {"cost": point_cost}
        if not expiration is None:
            self.data_store[username]["violations"][violation_fullname]["expires"] = expiration
        log.debug(f"Added {violation_fullname} to u/{username}.")

        new_total = self.get_user_total(username)
        log.info(f"+{point_cost} to u/{username} from {violation_fullname}, now at {new_total}.")

        # Check whether this addition should trigger a ban
        if new_total >= settings.point_threshold:
            self.act_on(username, new_total)

        return True

    def remove_user(self, username: str) -> bool:
        """Wipe a user's record completely.
        Used for wiping deleted accounts, mods, etc."""
        if not username in self.data_store:
            log.debug(f"Can't remove u/{username} (doesn't exist).")
            return False
        log.debug(f"Removed u/{username}.")
        del self.data_store[username]
        return True

    def remove_violation(self, username: str, violation_fullname: str, should_exist: bool = True) -> dict | None:
        """Remove a violation from a user's record.
        Returns the removed violation in case you want to use/log it,
        or returns None if no removal occured."""

        if not username in self.data_store:
            if should_exist:
                log.warning(f"Can't remove {violation_fullname} from u/{username} (user doesn't exist).")
            return
        if not violation_fullname in self.data_store[username]["violations"]:
            if should_exist:
                log.warning(f"Can't remove {violation_fullname} from u/{username} (violation doesn't exist).")
            return
        removed = self.data_store[username]["violations"][violation_fullname]
        del self.data_store[username]["violations"][violation_fullname]
        log.debug(f"Removed {violation_fullname} from u/{username}.")
        if len(self.data_store[username]["violations"]) == 0 and not "record" in self.data_store[username]:
            del self.data_store[username]
        return removed

    def get_user_total(self, username: str) -> int:
        """Get the total points from a user (0 by default if we have no data)."""
        if not username in self.data_store:
            return 0
        return sum(v["cost"] for v in self.data_store[username]["violations"].values())

    def scan(self, username, check_mod=True):
        """Scan a user's record for expired or re-approved submissions (and remove them).
        Returns true if anything was removed and false otherwise.
        Has an option not to check if the user's a mod because scan_all does it more efficiently as a batch."""
        log.debug(f"Scanning u/{username}.")
        change = False

        # If u/[deleted] ends up in the dataset somehow, gettem outta here
        if username == "[deleted]":
            log.warning("u/[deleted] was scanned somehow (which shouldn't happen) - expunging.")
            return self.remove_user("[deleted]")
        if not username in self.data_store:
            log.warning(f"Tried to scan user u/{username} for which we have no data.")
            return False
        # If the user doesn't exist anymore (most often because they deleted their account), dump eet
        if not user_exists(self.reddit, username):
            log.info(f"u/{username}'s account doesn't exist anymore - expunging.")
            return self.remove_user(username)
        # Exclude mods if requested
        if check_mod and settings.exclude_mods and len(self.reddit.subreddit(settings.subreddit).moderator(username)) > 0:
            log.info(f"u/{username} is a mod - expunging.")
            return self.remove_user(username)

        violations = deepcopy(self.data_store[username]["violations"])  # Get a copy because we'll be modifying it during iteration
        for violation_fullname, violation_data in violations.items():
            violation = get_thing(self.reddit, violation_fullname)
            reason = None

            # Check for re-approval
            if not violation.removed:
                reason = "re-approved"
            # Check for expiration
            elif "expires" in violation_data and datetime.now() >= violation_data["expires"]:
                reason = "expired"
            # Check for submissions before the cutoff (meaning they were already acted on)
            elif "record" in self.data_store[username] and datetime.fromtimestamp(violation.created_utc) <= self.data_store[username]["record"]["cutoff"]:
                reason = "already acted-on"

            if not reason is None:
                if self.remove_violation(username, violation_fullname) is None:
                    log.error(f"Failed to remove {reason} violation {violation_fullname} from u/{username}.")
                    continue
                change = True
                log.info(f"-{violation_data['cost']} to u/{username} from {violation_fullname} ({reason}), now at {self.get_user_total(username)}.")
                continue

        return change

    def scan_all(self):
        """Scan the entire data store for expired or re-approved submissions.
        Also cleans up mod entries if exclude_mods is on; this is done here so we can make a single request to get a list of mods instead of slowing down other operations with constant requests."""
        users = set(self.data_store.keys())

        log.info(f"Starting full scan ({len(users)} users).")

        if settings.exclude_mods:
            mods = set(mod.name for mod in self.reddit.subreddit(settings.subreddit).moderator())
            for mod in mods:
                if mod in users and self.remove_user(mod):
                    log.info(f"Wiped record of u/{mod} because they're a mod.")
            users -= mods

        for username in users:
            self.scan(username, check_mod=False)

    def act_on(self, username, total):
        """Act on a user hitting the threshold.
        Bans them and/or sends the mods a modmail warning, depending on your settings.
        Double-checks that all submissions are still removed and not past their expirations, and that the user isn't a mod if exclude_mods is on.
        Returns true if an action was taken or false if none was."""

        # Double check
        self.scan(username)
        if self.get_user_total(username) < settings.point_threshold:
            return False

        # Don't act if already banned
        if next(self.reddit.subreddit(settings.subreddit).banned(username), None) is not None:
            log.info(f"u/{username} is already banned; skipping action.")
            return False

        # Create permanent record
        if not "record" in self.data_store[username]:
            log.debug(f"Creating permanent record for u/{username}.")
            self.data_store[username]["record"] = {"bans": []}

        # Handle modmail notification
        if settings.autoban_mode in [1, 2]:
            log.info(f"Sending modmail about u/{username} for reaching {total} points.")

            # Henceforth, ignore all violations from before this notification
            self.data_store[username]["record"]["cutoff"] = datetime.now()

            # Prepare modmail message
            message = f"u/{username}'s violations have passed the {settings.point_threshold} point threshold:\n\n"
            for fullname in self.data_store[username]["violations"]:
                violation = get_thing(self.reddit, fullname)
                if fullname.startswith("t1_"):
                    kind = "comment"
                    text = violation.body
                elif fullname.startswith("t3_"):
                    kind = "post"
                    text = violation.title
                else:
                    raise Exception(f"Unexpected object type for fullname {fullname}")
                text = re.sub(r"\s*\n\s*", " ", text)  # Strip newlines
                if settings.modmail_truncate_len > 0 and len(text) > settings.modmail_truncate_len:
                    text = text[:settings.modmail_truncate_len - 3] + "..."
                date = datetime.fromtimestamp(violation.banned_at_utc).strftime("%m/%d/%y")
                points = self.data_store[username]["violations"][fullname]['cost']
                message += f"- {date} {kind} ({points} point{'s' if points > 1 else ''}): [{text}]({violation.permalink}) ({violation.mod_reason_title})\n"
            message += f"{'A' if settings.autoban_mode >= 2 else 'No'} ban has been issued."

            # Send modmail
            send_modmail(self.reddit, subject=f"{'Ban' if settings.autoban_mode >= 2 else 'Point'} alert for u/{username}",
                         body=message)

        # Handle autoban
        if settings.autoban_mode in [2, 3]:
            log.info(f"Banning u/{username} for {'TBD - duration'} for reaching {total} points.")

            # TBD - calculate cutoff based on when ban ends (though technically they shouldn't be able to post during a ban)
            # self.data_store[username]["record"]["cutoff"] = datetime.now() + ????

            # TBD - add bans to record

            if settings.dry_run:
                log.info(f"[DRY RUN: would have banned u/{username} for {'TBD - duration'}.]")
            else:
                pass  # TBD

        # Wipe out current violations since they've been acted on
        self.data_store[username]["violations"] = {}

        return True
