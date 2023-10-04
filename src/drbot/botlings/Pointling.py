from __future__ import annotations
import re
import json
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
import prawcore
import schedule
from praw.models import ModAction, ModNote, Submission, Comment, ModmailConversation
from ..util import escape_markdown, get_dupes, markdown_comment, get_markdown_comments
from ..log import log
from ..reddit import reddit
from ..Botling import Botling


class Removal:
    """An object which tracks the modnotes associated with a removal:
    one for the removal itself and one for the removal reason."""

    removal_note: ModNote | None = None
    removal_reason: ModNote | None = None

    @property
    def date(self) -> float:
        """Get the date of the removal, which we consider to be
        whatever the date of the most recent modnote associated with it is.
        Errors if called on a removal that hasn't been populated yet."""
        options = []
        if self.removal_note:
            options.append(self.removal_note.created_at)
        if self.removal_reason:
            options.append(self.removal_reason.created_at)
        assert len(options) != 0
        return max(options)

    @property
    def target_id(self) -> str:
        """Get the ID of the removed item.
        Errors if called on a removal that hasn't been populated yet."""
        if self.removal_reason:
            return self.removal_reason.reddit_id
        return self.removal_note.reddit_id


class ViolationInterval:
    """An interval of removals, which ends with a ban
    (or with None if the removals happened after the most recent ban)."""

    def __init__(self, removals: list[Removal], ban: ModNote | None = None) -> None:
        self.removals = removals
        self.ban = ban

    def to_string(self, pointling: Pointling, include_points: bool = True, relevant_only: bool = False, cache: bool = False) -> str:
        """Turn a ViolationInterval into a human-readable string.
        Ends with a newline (unless there are no violations).
        You can choose whether the points for each violation should be shown or not with include_points.
        If relevant_only is true, only shows violations which contributed at least 1 point."""

        message = ""
        removals = self.removals
        if relevant_only:
            removals = [r for r in removals if pointling.get_point_cost(r) > 0]
        for removal in removals:
            fullname = removal.target_id
            target = pointling.get_thing(fullname, cache=cache)
            if fullname.startswith("t1_"):
                kind = "comment"
                text = target.body
            elif fullname.startswith("t3_"):
                kind = "post"
                text = target.title
            else:
                raise Exception(f"Unexpected object type for fullname {fullname}")
            text = re.sub(r"\s*\n\s*", " ", text)  # Strip newlines
            if pointling.DR.settings.misc.modmail_truncate_len > 0 and len(text) > pointling.DR.settings.misc.modmail_truncate_len:
                text = text[:pointling.DR.settings.misc.modmail_truncate_len - 3] + "..."
            date = datetime.fromtimestamp(target.banned_at_utc, timezone.utc).strftime("%m/%d/%y")
            message += f"- {date} {kind}"
            if include_points:
                points = pointling.get_point_cost(removal, cache=cache)
                message += f" ({points} point{'s' if points > 1 else ''})"
            message += f": [{escape_markdown(text)}]({target.permalink}) ({escape_markdown(target.mod_reason_title)})\n"
        return message


class PointMap:
    """
    Class that handles the mapping between removal reasons and their point costs.
    Also manages info about expiration durations.
    """

    def __init__(self, pointling: Pointling) -> None:
        self.pointling = pointling

        log.debug("Loading removal reasons.")

        raw_map = pointling.DR.settings.points.map

        # Check for dupes
        if len(raw_map) != len(set(entry["id"] for entry in raw_map)):
            log.error("Duplicate removal reason IDs in point_map (the last instance of each one will be used):" +
                      "".join(f"\n\t{r}" for r in get_dupes(entry["id"] for entry in raw_map)))

        # Build the map
        self.point_map: dict[str, dict[str, int]] = {}
        for entry in raw_map:
            self.point_map[entry["id"]] = {"points": int(entry["points"])}
            if "expires" in entry:
                self.point_map[entry["id"]]["expires"] = int(entry["expires"])
        log.debug(f"Point map: {json.dumps(self.point_map)}")

        # Check for removal reasons on your sub that aren't in the map
        missing_reasons = set(r.title for r in reddit.sub.mod.removal_reasons) - set(self.point_map.keys())
        if len(missing_reasons) > 0:
            log.warning("Some removal reasons on your sub don't have an entry in your settings (they will be treated as costing 0 points):" +
                        "".join(f"\n\t{r}" for r in missing_reasons))

    def __getitem__(self, removal_reason: str) -> int:
        """Get the point value for a removal reason."""
        if removal_reason not in self.point_map:
            log.debug(f"Unknown removal reason '{removal_reason}', defaulting to 0 points.")
            return 0
        return self.point_map[removal_reason]["points"]

    def get_expiration(self, removal_reason: str) -> int | None:
        """Get the expiration months for a removal reason (or the default if no special duration is specified)."""

        # Use default if this removal reason is unknown
        default_expiration = self.pointling.DR.settings.points.expiration_months
        if removal_reason not in self.point_map:
            log.debug(f"Unknown removal reason '{removal_reason}', using default expiration ({default_expiration}).")
            expiration = default_expiration
        # Otherwise, use the specific duration if available or the default if not
        else:
            expiration = self.point_map[removal_reason].get("expires", default_expiration)
        # Return None
        return expiration if expiration > 0 else None


class Pointling(Botling):
    default_settings = {
        "points": {
            # When a user has this many points, Pointling will take action.
            "threshold": 12,

            # How many points does each removal cost?
            # For example:
            #   point_map = [
            #       {id="Some removal reason title", points=3, expires=2},
            #       {id="Another one", points=0}
            #   ]
            # The ID of a removal reason must be its exact title.
            # You can optionally set a different expiration time (in months) for each removal reason;
            # If you don't it will use the default from expiration_months.
            "map": [],

            # Number of months before a removal is forgiven and wiped from the record.
            # Set to 0 to never expire. You can override this for individual reasons in the point_map.
            "expiration_months": 6,

            # You can make exceptions for individual removals and give them custom point values
            # by putting the point number inside square brackets anywhere in the mod note of the removal, like this:
            #   [0]
            # This lets you make special exceptions to not count a removal as a strike against a user or give extra points for a removal.
            # This requires extra requests though, which slows down the bot, so you can turn it off here.
            "allow_custom": True,
        },
        "action": {
            # Should Pointling notify the mods when a user passes the point threshold?
            "notify_mods": True,

            # Should Pointling automatically ban a user when they pass the point threshold?
            # WARNING: If you have this on but notify_mods off, this will result in silent bans!
            "autoban": False,

            # When a user is banned (whether manually or automatically),
            # Pointling can reply to the ban with a summary of their violations.
            "user_violations_notice": False,
        },
        "misc": {
            # By default, Pointling will not ban mods or track their points.
            # You can force it to include mods by setting this to false.
            # This may cause permissions issues with your sub - mods can't always ban other mods.
            "exclude_mods": True,

            # Truncate long comments/post previews to this length in the modmails we send.
            "modmail_truncate_len": 100,
        },
    }

    VIOLATIONS_NOTICE_MARKER_COMMENT = "Pointling Violations Notice"

    def setup(self) -> None:
        self.point_map = PointMap(self)

        # Init data store
        if "outstanding_alerts" not in self.DR.storage:
            self.DR.storage["outstanding_alerts"] = {}

        # Init caches
        self.cache_violations: dict[str, list[ViolationInterval]] = {}
        self.cache_points: dict[Removal, int] = {}
        self.cache_scans: set[str] = set()
        self.cache_items: dict[str, Submission | Comment] = {}

        # Subscribe to relevant streams
        if self.DR.settings.action.autoban or self.DR.settings.action.notify_mods:
            self.DR.streams.modlog.subscribe(self, self.handle_modlog, self.start_run_modlog)
        if self.DR.settings.action.user_violations_notice:
            self.DR.streams.modmail_conversation.subscribe(self, self.handle_modmail)

    def handle_modlog(self, item: ModAction) -> None:
        # If a relevant action like a removal or approval happens, scan the involved user
        if item.action in ['removecomment', 'removelink', 'addremovalreason', 'approvelink', 'approvecomment']:
            self.scan(item.target_author, cache=True)
        # If a user is banned, we want to purge them from the outstanding alerts and sunset their point alert.
        if item.action == 'banuser':
            log.warning(f"Checking ban for u/{item.target_author}")
            if item.target_author not in self.DR.storage["outstanding_alerts"]:
                return
            reason = self.valid_user(item.target_author)
            if reason is not None:
                log.debug(f"Clearing outstanding alert data for u/{item.target_author} because: {reason}.")
                self.clear_user(item.target_author)
                return

            # Schedule a task to reply to the point message (to note that the user has already been banned).
            # This has to happen after a short delay, otherwise the ban note may not have come in yet.
            log.warning(f"Scheduled task to reply to point alert {self.DR.storage['outstanding_alerts'][item.target_author]['modmail']} for u/{item.target_author}")
            self.DR.scheduler.every(5).seconds.do(self.reply_to_alert,
                                                  username=item.target_author,
                                                  modmail_id=self.DR.storage["outstanding_alerts"][item.target_author]["modmail"],
                                                  ban_id=self.DR.storage["outstanding_alerts"][item.target_author]["ban"])

            # Purge data.
            del self.DR.storage["outstanding_alerts"][item.target_author]

    def start_run_modlog(self) -> None:
        # Invalidate all our caches
        self.cache_violations.clear()
        self.cache_points.clear()
        self.cache_scans.clear()
        self.cache_items.clear()

    def reply_to_alert(self, username: str, modmail_id: str, ban_id: str):
        """Internal method used to schedule replying to a point alert once the user in question has been banned.
        Has to happen on a delay to give reddit time to register the ban mod note."""

        # Fetch the most recent ban.
        last_ban = next(reddit.sub.mod.notes.redditors(username, all_notes=True, params={"filter": "BAN"}), None)
        if last_ban is None:
            log.error(f"Modlog reported that u/{username} was banned, but we could not find the corresponding ban mod note. This could lead to point alerts no longer being sent for this user.")
            return schedule.CancelJob

        # Make sure we haven't already seen this ban somehow.
        if ban_id == last_ban.id:
            log.info(f"We've already seen ban {last_ban.id} for u/{username}, which is strange. Taking no action.")
            return schedule.CancelJob

        # Send a reply to the point alert and archive it.
        point_alert = reddit.sub.modmail(modmail_id)
        try:  # Make sure it exists.
            point_alert.num_messages
        except prawcore.exceptions.Forbidden:
            log.error(f"Recorded point alert {modmail_id} for user u/{username} does not exist. This shouldn't happen, but also shouldn't break anything.")
            return schedule.CancelJob
        message = f"u/{username} has been banned."
        if self.DR.global_settings.dry_run:
            log.info(f"""DRY RUN: would have sent the following reply to modmail {point_alert.id}:
{message}""")
        else:
            point_alert.reply(author_hidden=True, body=message)

        # This is a one-time job
        return schedule.CancelJob

    def get_thing(self, id: str, cache: bool = False) -> Submission | Comment:
        """Wrapper for the normal get_thing that handles caching."""

        if cache and id in self.cache_items:
            return self.cache_items[id]
        item = reddit.DR.get_thing(id)
        if cache:
            self.cache_items[id] = item
        return item

    def valid_user(self, username: str) -> str | None:
        """Check if a user is a valid target for Pointling -
        meaning they exist, aren't deleted, and aren't a mod (if the setting for that is enabled).
        Returns None if valid, or a string with the reason if invalid."""

        if username == "[deleted]":
            return "deleted user"
        if not reddit.DR.user_exists(username):
            return "account doesn't exist anymore"
        if self.DR.settings.misc.exclude_mods and reddit.DR.is_mod(username):
            return "user is a mod"
        return None

    def clear_user(self, username: str) -> None:
        """Helper to clear the outstanding alert data of a user (if present)."""

        if username in self.DR.storage["outstanding_alerts"]:
            del self.DR.storage["outstanding_alerts"]

    def get_violations(self, username: str, exclude_automod: bool = True, cache: bool = False) -> list[ViolationInterval]:
        """Gather all of a user's removals and bans, accounting for things that were later reapproved.
        Returns a list of ViolationIntervals, which divide the removals up into intervals between each ban, sorted from earliest to latest."""

        if cache and username in self.cache_violations:
            return self.cache_violations[username]

        removals: dict[str, Removal] = {}
        bans: list[ModNote] = []

        # We iterate in reverse order so we can use a later reapproval to cancel an earlier removal.
        for note in reversed(list(reddit.sub.mod.notes.redditors(username))):
            if note.action in ['removecomment', 'removelink']:
                if note.reddit_id not in removals:
                    removals[note.reddit_id] = Removal()
                removals[note.reddit_id].removal_note = note
            elif note.action == 'addremovalreason':
                if note.reddit_id not in removals:
                    removals[note.reddit_id] = Removal()
                removals[note.reddit_id].removal_reason = note
            elif note.action in ['approvelink', 'approvecomment'] and note.reddit_id in removals:
                del removals[note.reddit_id]
            elif note.action == 'banuser':
                bans.append(note)

            # TBD: deal with unbanning. How should it affect intervals?

        # Exclude any automod removals
        # We do this at the end to avoid any weirdness where both automod and a human mod act on the same post/comment,
        # e.g. mod removes it and automod reapproves it. (This happens sometimes.)
        if exclude_automod:
            for id in list(removals.keys()):  # Get a list of keys to avoid issues with dictionary changing size during iteration
                # We check for the operator this way because sometimes AutoModerator does the initial removal and then a human mod adds a removal reason.
                # If a human touched any part of the process we don't remove it.
                # This assumes there's at least one of removal or removal_reason, which should always be true.
                if removals[id].removal_note and removals[id].removal_note.operator != "AutoModerator":
                    continue
                if removals[id].removal_reason and removals[id].removal_reason.operator != "AutoModerator":
                    continue
                del removals[id]

        # Make sure each removal's target item is actually still removed right now,
        # since sometimes reddit lets a reapproved item slip through the cracks somehow or a "that comment is missing" throws us off.
        # This unfortunately requires us to fetch each removed item, which slows things down considerably.
        # If you're having speed issues and don't mind having an odd item slip through the cracks once in a while, you can remove this at your own peril.
        for id in list(removals.keys()):
            target = self.get_thing(removals[id].target_id, cache=cache)
            if target.banned_at_utc is None:
                log.debug(f"Due to Reddit weirdness, removed item {target.id} wasn't actually removed; ignoring.")
                del removals[id]

        # Now divide removals into intervals based on bans.
        # We do this after the fact (even though we lose the order) because we need to associate removals with the removal reasons and reapprovals first.
        violations: list[object] = []
        i = 0  # Start index for an interval
        j = 0  # End index (sweeps forward)
        sortedRemovals = sorted(removals.values(), key=lambda r: r.date)
        for ban in bans:  # Assumes bans are sorted from earliest to latest, since they should be
            # Gobble all removals before this ban
            while j < len(sortedRemovals) and sortedRemovals[j].date <= ban.created_at:
                j += 1
            # Create the interval
            violations.append(ViolationInterval(sortedRemovals[i:j], ban=ban))
            # Move start marker up
            i = j
        # Add a final interval for removals after the most recent ban
        violations.append(ViolationInterval(sortedRemovals[i:]))

        if cache:
            self.cache_violations[username] = violations

        return violations

    def get_point_cost(self, removal: Removal, cache: bool = False) -> int:
        """Get the point cost of a removal using the removal reasons point map."""

        if cache and removal in self.cache_points:
            return self.cache_points[removal]

        # If there's no removal reason, cost is 0
        if removal.removal_reason is None:
            return 0

        reason = removal.removal_reason.description

        # Check if this removal has already expired
        expiration_duration = self.point_map.get_expiration(reason)
        if expiration_duration is not None and datetime.now(timezone.utc) >= datetime.fromtimestamp(removal.date, timezone.utc) + relativedelta(months=expiration_duration):
            return 0

        # Get base point cost
        point_cost = self.point_map[reason]

        # Check for manual point exception in mod note
        if self.DR.settings.points.allow_custom:
            note = self.get_thing(removal.target_id, cache=cache).mod_note
            if note:
                result = re.search(r"\[(\d+)\]", note)
                if result:
                    point_cost = int(result.group(1))
                    log.debug(f"{removal.target_id} has a custom point cost of {point_cost} as set by its mod note.")

        if cache:
            self.cache_points[removal] = point_cost

        return point_cost

    def get_user_total(self, username: str, cache: bool = False) -> int:
        """Get the total points from a user (0 by default if we have no data).
        Does not check it against the threshold or take any action.
        This only counts violations since the last ban."""

        violations = self.get_violations(username, cache=cache)
        return sum(self.get_point_cost(removal, cache=cache) for removal in violations[-1].removals)

    def scan(self, username: str, cache: bool = False) -> None:
        """Scan a user to see if they're over the point threshold.
        Acts if necessary."""

        # If we've already scanned this user during this run, don't do it again
        if cache:
            if username in self.cache_scans:
                log.debug(f"Skipping u/{username} because we've already scanned them this run.")
                return
            self.cache_scans.add(username)

        # Make sure the user is valid, and clear their data if they're not
        reason = self.valid_user(username)
        if reason:
            log.debug(f"Skipping u/{username} and clearing record: {reason}.")
            self.clear_user(username)
            return

        log.debug(f"Scanning u/{username}.")

        # Get point total
        total = self.get_user_total(username, cache=cache)
        log.debug(f"u/{username} has {total} points.")

        # Check total against threshold and act if necessary
        if total >= self.DR.settings.points.threshold:
            log.info(f"u/{username} has {total} points, which is over the threshold ({self.DR.settings.points.threshold}).")
            self.act_on(username, cache=cache)

    def act_on(self, username: str, cache: bool = False) -> None:
        """Act on a user hitting the threshold.
        Bans them and/or sends the mods a modmail warning, depending on your settings.
        Should only be called once you have determined that the user passed the threshold."""

        # Double check that the user isn't already banned (though we should have seen it in the mod notes if they were)
        if next(reddit.sub.banned(username), None) is not None:
            log.info(f"u/{username} is already banned; skipping action.")
            return

        # Handle autoban
        didBan = False
        if self.DR.settings.action.autoban:
            log.info(f"Banning u/{username} for {'TBD - duration'} for passing the point threshold.")

            if self.DR.global_settings.dry_run:
                log.info(f"DRY RUN: would have banned u/{username} for {'TBD - duration'}.")
            else:
                raise NotImplementedError()  # TBD
            didBan = True

        # Handle modmail notification
        if self.DR.settings.action.notify_mods:
            # Get the most recent ban ID (or "" if there was none) for tracking purposes
            violations = self.get_violations(username, cache=cache)
            last_ban_id = "" if len(violations) == 1 else violations[-2].ban.id

            # Make sure we haven't sent this alert already for a previous removal
            if username in self.DR.storage["outstanding_alerts"] and self.DR.storage["outstanding_alerts"][username]["ban"] == last_ban_id:
                log.debug(f"Skipping modmail action for u/{username} because we've done it already for a past removal and they haven't been banned since.")
                return

            log.info(f"Sending modmail to mods about u/{username} for passing the point threshold.")

            # Prepare modmail message
            interval = violations[-1]
            message = f"u/{username}'s violations have reached {self.get_user_total(username, cache=cache)} points and passed the {self.DR.settings.points.threshold}-point threshold:\n\n"
            message += interval.to_string(self, cache=cache, relevant_only=True)
            message += f"\n{'A' if didBan else 'No'} ban has been issued."
            if not didBan:
                message += f" You can ban them [here](https://www.reddit.com/r/{self.DR.global_settings.subreddit}/about/banned)."

            # Send modmail
            modmail = reddit.DR.send_modmail(subject=f"{'Ban' if didBan else 'Point'} alert for u/{username}", body=message)

            # If this is a point warning that we might need to reply to later,
            # record the fact that we sent it so we don't send another one for the next removal.
            if not self.DR.settings.action.autoban:
                self.DR.storage["outstanding_alerts"][username] = {"ban": last_ban_id, "modmail": modmail.id}
            # Otherwise clear any previous alerts they may have
            else:
                self.clear_user(username)

    def handle_modmail(self, item: ModmailConversation) -> None:
        """Notify users of the violations that led to their ban."""
        if not self.DR.settings.action.user_violations_notice:
            return
        if not item.is_auto:
            return
        if item.is_internal:
            return
        if not item.is_repliable:
            return
        if not re.match(fr"^u/[^ ]+ is (?:temporarily|permanently) banned from r/{self.DR.global_settings.subreddit}$", item.subject, re.IGNORECASE):
            return

        # Make sure the user is valid
        reason = self.valid_user(item.participant)
        if reason:
            log.info(f"Not sending a violations notice to u/{item.participant} on modmail {item.id}: {reason}.")
            return

        # Make sure we haven't already left a violations notice on this conversation
        for message in item.messages[1:]:
            if message.author == reddit.user.me().name and Pointling.VIOLATIONS_NOTICE_MARKER_COMMENT in get_markdown_comments(message.body_markdown):
                log.debug(f"Not sending a violations notice to u/{item.participant} on modmail {item.id} since we already sent one.")
                return

        # Make sure the user isn't muted, since for some reason reddit freaks out if we try to message them
        if len(reddit.request(method="GET", path="/r/DebateReligion/about/muted",
                              params={"user": item.participant})['data']['children']) > 0:
            log.info(f"Couldn't send a violations notice to u/{item.participant} on modmail {item.id} since they are muted and reddit freaks out about that.")
            return

        # Find the ban message's associated ViolationInterval by matching their timestamps.
        # Sadly there's no ID or similar that we can use, but unless you're banning a user multiple times a minute it really shouldn't be an issue.
        ban_date = datetime.fromisoformat(item.messages[0].date)
        violations = self.get_violations(item.participant)[:-1]  # Don't include violations after the most recent ban
        interval_distances = [(interval, abs(datetime.fromtimestamp(interval.ban.created_at, timezone.utc) - ban_date)) for interval in violations]
        closest_interval, time_gap = min(interval_distances, key=lambda p: p[1])
        epsilon = timedelta(hours=1)  # The maximum time gap before we consider a ban message not associated with a ban anymore
        if time_gap >= epsilon:  # Technically the ban message should always come after the ban, but who knows what Reddit might do, so we compare the absolute time gap
            log.warning(f"No matching ban could be found for ban message {item.id} of user u/{item.participant}, so no violations notice could be sent.")
            return
        log.debug(f"Found a matching ban {closest_interval.ban.id} within {time_gap} of ban message {item.id}.")

        # Prepare modmail message
        violation_string = closest_interval.to_string(self, include_points=False, relevant_only=True)
        if len(violation_string.strip()) == 0:
            log.info(f"Skipping violations notice for banned user u/{item.participant} because they have no relevant violations on record.")
            return
        message = f"Beep boop, I'm a robot. Here's a list of recent violations which contributed to your ban:\n\n"
        message += violation_string
        message += f"\n{markdown_comment(Pointling.VIOLATIONS_NOTICE_MARKER_COMMENT)}"

        log.info(f"Sending banned user u/{item.participant} a summary of their violations for ban notice {item.id}.")

        if self.DR.global_settings.dry_run:
            log.info(f"""DRY RUN: would have sent the following reply to modmail {item.id}:
{message}""")
        else:
            item.reply(author_hidden=True, body=message)
            item.archive()
