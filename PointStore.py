import os
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

from config import settings
import util


class PointStore:
    """
    Class handling the data structure that stores information about user points.
    Modifications to this data structure are what trigger bans.
    """

    def __init__(self, logger, reddit, point_map, data_store):
        self.logger = logger
        self.reddit = reddit
        self.point_map = point_map
        self.data_store = data_store

    def add(self, mod_action):
        """
        Add points for a removal.
        Returns true if it was added and false if it wasn't (e.g. because it costs 0 points).
        Triggers a ban if the addition causes the user goes over the threshold.
        """
        removal_reason_id = mod_action.description
        violation_fullname = mod_action.target_fullname
        username = mod_action.target_author
        removal_time = mod_action.created_utc

        self.logger.debug(f"Processing removal of {violation_fullname} with reason: {removal_reason_id}")

        # Skip submissions by u/[deleted]
        if username == "[deleted]":
            self.logger.debug(f"{violation_fullname}'s author has deleted their account; skipping.")
            return False

        # Get point cost
        point_cost = self.point_map[removal_reason_id]
        if point_cost == 0:
            self.logger.debug(f"{violation_fullname} costs 0 points; skipping.")
            return False

        # Check if this submission is already accounted for
        if violation_fullname in self.data_store.get_user(username):
            self.logger.debug(f"{violation_fullname} already accounted for; skipping.")
            return False
        
        # Safe mode checks
        if settings.safe_mode:
            # If exclude_mods is on, check if the user is a mod
            if settings.exclude_mods and len(self.reddit.subreddit(settings.subreddit).moderator(username)) > 0:
                self.logger.debug(f"u/{username} is a mod; skipping.")
                return False

            # Check if this submission has already been re-approved
            m = self.reddit.comment if violation_fullname.startswith("t1_") else self.reddit.submission
            if not m(violation_fullname[3:]).removed:
                self.logger.debug(f"{violation_fullname} already re-approved; skipping.")

        # Calculate expiration
        expiration_duration = self.point_map.get_expiration(removal_reason_id)
        if not expiration_duration is None:
            expiration = datetime.fromtimestamp(removal_time) + relativedelta(months=self.point_map.get_expiration(removal_reason_id))
            # Check if this submission has already expired (should almost never happen)
            if datetime.now() >= expiration:
                self.logger.debug(f"{violation_fullname} already expired before it was added; skipping.")
                return False

        # Add the submission to the user's record
        if not self.data_store.add(username, violation_fullname, point_cost, expires=expiration):
            self.logger.error(f"Failed to add violation {violation_fullname} to u/{username} (DataStore issue).")
            return False

        new_total = self.data_store.get_user_total(username)
        self.logger.info(f"+{point_cost} to u/{username} from {violation_fullname}, now at {new_total}.")

        # Check whether this addition should trigger a ban
        if new_total >= settings.point_threshold:
            self.ban(username, new_total)

        return True

    def scan(self, username, check_mod=True):
        """
        Scan a user's record for expired or re-approved submissions (and remove them).
        Returns true if anything was removed and false otherwise.
        Has an option not to check if the user's a mod because scan_all does it more efficiently as a batch.
        """
        self.logger.debug(f"Scanning u/{username}.")
        change = False

        # If u/[deleted] ends up in the dataset somehow, gettem outta here
        if username == "[deleted]":
            self.logger.warning("u/[deleted] was scanned somehow (which shouldn't happen) - expunging.")
            return self.data_store.remove_user("[deleted]")
        # If the user doesn't exist anymore (most often because they deleted their account), dump eet
        if not util.user_exists(username):
            self.logger.info(f"u/{username} doesn't exist anymore (probably because their account was deleted) - expunging.")
            return self.data_store.remove_user(username)
        # Exclude mods if requested
        if settings.exclude_mods and len(self.reddit.subreddit(settings.subreddit).moderator(username)) > 0:
            self.logger.info(f"u/{username} is a mod - expunging.")
            return self.data_store.remove_user(username)
        
        userdict = self.data_store.get_user(username)
        for violation_fullname in userdict:
            # Check for re-approval
            m = self.reddit.comment if violation_fullname.startswith("t1_") else self.reddit.submission
            violation = m(violation_fullname[3:])
            if not violation.removed:
                if not self.data_store.remove(username, violation_fullname):
                    self.logger.error(f"Failed to remove re-approved violation {violation_fullname} from u/{username} (DataStore issue)")
                    continue
                change = True
                self.logger.info(f"-{userdict[violation_fullname]['cost']} to u/{username} from {violation_fullname} (re-approved), now at {self.data_store.get_user_total(username)}.")
                continue

            # Check for expiration
            if "expires" in userdict[violation_fullname] and datetime.now() >= userdict[violation_fullname]["expires"]:
                if not self.data_store.remove(username, violation_fullname):
                    self.logger.error(f"Failed to remove expired violation {violation_fullname} from u/{username} (DataStore issue)")
                    continue
                change = True
                self.logger.info(f"-{userdict[violation_fullname]['cost']} to u/{username} from {violation_fullname} (expired), now at {self.data_store.get_user_total(username)}.")
                continue

        return change

    def scan_all(self):
        """
        Scan the entire data store for expired or re-approved submissions.
        Also cleans up mod entries if exclude_mods is on; this is done here so we can make a single request to get a list of mods instead of slowing down other operations with constant requests.
        """
        self.logger.info(f"Starting full scan.")

        users = set(self.data_store.all_users())

        if settings.exclude_mods:
            mods = set(mod.name for mod in self.reddit.subreddit(settings.subreddit).moderator())
            for mod in mods:
                if mod in users and self.data_store.remove_user(mod):
                    self.logger.info(f"Wiped record of u/{mod} because they're a mod.")
            users -= mods

        for username in users:
            self.scan(username, check_mod=False)

    def ban(self, username, total):
        """
        Act on a user hitting the threshold.
        Either bans them or just sends modmail.
        Double-checks that all submissions are still removed and not past their expirations, and that the user isn't a mod if exclude_mods is on.
        Returns true if the ban/modmail went through and false if it didn't.
        """

        # Double check
        self.scan(username)
        if self.data_store.get_user_total(username) < settings.point_threshold:
            return False

        # Handle autoban
        if settings.autoban_mode in [2, 3]:
            self.logger.info(f"Banning u/{username} for reaching {total} points.")

            print(self.reddit.subreddit(settings.subreddit).banned(username))
            pass  # TBD

        # Handle modmail notification
        if settings.autoban_mode in [1, 2]:
            didBan = settings.autoban_mode == 2

            self.logger.info(f"Sending modmail about u/{username} for reaching {total} points.")

            # Prepare modmail message
            userdict = self.data_store.get_user(username)
            message = f"u/{username}'s violations have passed the {settings.point_threshold} point threshold:\n\n"
            for fullname in userdict:
                if fullname.startswith("t1_"):
                    submission = self.reddit.comment(fullname[3:])
                    kind = "comment"
                    text = submission.body
                else:
                    submission = self.reddit.submission(fullname[3:])
                    kind = "post"
                    text = submission.title
                text = re.sub(r"\s*\n\s*", " ", text)  # Strip newlines
                if settings.modmail_truncate_len > 0 and len(text) > settings.modmail_truncate_len:
                    text = text[:settings.modmail_truncate_len - 3] + "..."
                date = datetime.fromtimestamp(submission.banned_at_utc).strftime("%m/%d/%y")
                points = userdict[fullname]['cost']
                message += f"- {date} {kind} ({points} point{'s' if points > 1 else ''}): [{text}]({submission.permalink}) ({submission.mod_reason_title})\n"
            message += f"\n(This is an automated message, {'a' if didBan else 'no'} ban has been issued.)"

            # Send modmail
            if not settings.dry_run:
                self.reddit.subreddit(settings.subreddit).modmail.create(
                    subject=f"DRBOT: {'ban' if didBan else 'point'} alert for u/{username}",
                    body=message,
                    recipient=None)  # None makes it create a moderator discussion

        return True
