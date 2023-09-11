from __future__ import annotations
import re
from praw.models import ModAction, ModNote, Submission, Comment
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from drbot import settings, log, reddit
from drbot.stores import PointMap
from drbot.agents import Agent
from drbot.handlers import Handler


def escape_markdown(text: str | None):
    """Helper to escape markdown, since apparently no one but python-telegram-bot has standardized one of these and I'm not making that a dependency."""

    if text is None:
        return None
    escape_chars = r"\_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)


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
        if not self.removal_note is None:
            options.append(self.removal_note.created_at)
        if not self.removal_reason is None:
            options.append(self.removal_reason.created_at)
        assert len(options) != 0
        return max(options)

    @property
    def target_id(self) -> str:
        """Get the ID of the removed item.
        Errors if called on a removal that hasn't been populated yet."""
        if not self.removal_reason is None:
            return self.removal_reason.reddit_id
        return self.removal_note.reddit_id


class ViolationInterval:
    """An interval of removals, which ends with a ban
    (or with None if the removals happened after the most recent ban)."""

    def __init__(self, removals: list[Removal], ban: ModNote | None = None) -> None:
        self.removals = removals
        self.ban = ban

    def to_string(self, points_handler: PointsHandler, include_points: bool = True, relevant_only: bool = False, cache: bool = False) -> str:
        """Turn a ViolationInterval into a human-readable string.
        Ends with a newline (unless there are no violations).
        You can choose whether the points for each violation should be shown or not with include_points.
        If relevant_only is true, only shows violations which contributed at least 1 point."""

        message = ""
        removals = self.removals
        if relevant_only:
            removals = [r for r in removals if points_handler.get_point_cost(r) > 0]
        for removal in self.removals:
            fullname = removal.target_id
            target = points_handler.get_thing(fullname, cache=cache)
            if fullname.startswith("t1_"):
                kind = "comment"
                text = target.body
            elif fullname.startswith("t3_"):
                kind = "post"
                text = target.title
            else:
                raise Exception(f"Unexpected object type for fullname {fullname}")
            text = re.sub(r"\s*\n\s*", " ", text)  # Strip newlines
            if settings.modmail_truncate_len > 0 and len(text) > settings.modmail_truncate_len:
                text = text[:settings.modmail_truncate_len - 3] + "..."
            date = datetime.fromtimestamp(target.banned_at_utc, timezone.utc).strftime("%m/%d/%y")
            message += f"- {date} {kind}"
            if include_points:
                points = points_handler.get_point_cost(removal, cache=cache)
                message += f" ({points} point{'s' if points > 1 else ''})"
            message += f": [{escape_markdown(text)}]({target.permalink}) ({escape_markdown(target.mod_reason_title)})\n"
        return message


class PointsHandler(Handler[ModAction]):
    def setup(self, agent: Agent[ModAction]) -> None:
        super().setup(agent)
        self.point_map = PointMap()

        # Init data store
        if not "outstanding_alerts" in self.data_store:
            self.data_store["outstanding_alerts"] = {}

        # Init caches
        self.cache_violations: dict[str, list[ViolationInterval]] = {}
        self.cache_points: dict[Removal, int] = {}
        self.cache_scans: set[str] = set()
        self.cache_items: dict[str, Submission | Comment] = {}

    def handle(self, item: ModAction) -> None:
        # If a relevant action like a removal or approval happens, scan the involved user
        if item.action in ['removecomment', 'removelink', 'addremovalreason', 'approvelink', 'approvecomment']:
            self.scan(item.target_author, cache=True)
        # If a user is banned, we want to purge them from the outstanding alerts and sunset their point alert.
        if item.action == 'banuser':
            if not item.target_author in self.data_store["outstanding_alerts"]:
                return
            if not self.valid_user(item.target_author) is None:
                self.clear_user(item.target_author)
                return

            # Fetch the most recent ban.
            last_ban = next(reddit().sub.mod.notes.redditors(item.target_author, all_notes=False, params={"filter": "BAN"}))
            if last_ban is None:
                log.error(f"Modlog reported that u/{item.target_author} was banned, but we could not find the corresponding ban mod note. This could lead to point alerts no longer being sent for this user.")
                return

            # Make sure we haven't already seen this ban somehow.
            if self.data_store["outstanding_alerts"][item.target_author]["ban"] == last_ban.id:
                log.info(f"We've already seen ban {last_ban.id} for u/{item.target_author}, which is strange. Taking no action.")
                return

            # Send a reply to the point alert and archive it.
            point_alert = reddit().sub.modmail.conversation(self.data_store["outstanding_alerts"][item.target_author]["modmail"])
            message = f"u/{item.target_author} has been banned."
            if settings.dry_run:
                log.info(f"""[DRY RUN: would have sent the following reply to modmail {point_alert.id}:
    {message}]""")
            else:
                item.reply(author_hidden=True, body=message)
                item.archive()

            # Purge data.
            del self.data_store["outstanding_alerts"][item.target_author]

    def start_run(self) -> None:
        # Invalidate all our caches
        self.cache_violations.clear()
        self.cache_points.clear()
        self.cache_scans.clear()
        self.cache_items.clear()

    def get_thing(self, id: str, cache: bool = False) -> Submission | Comment:
        """Wrapper for the normal get_thing that handles caching."""

        if cache and id in self.cache_items:
            return self.cache_items[id]
        item = reddit().get_thing(id)
        if cache:
            self.cache_items[id] = item
        return item

    def valid_user(self, username: str) -> str | None:
        """Check if a user is a valid target for PointsHandler -
        meaning they exist, aren't deleted, and aren't a mod (if the setting for that is enabled).
        Returns None if valid, or a string with the reason if invalid."""

        if username == "[deleted]":
            return "deleted user"
        if not reddit().user_exists(username):
            return "account doesn't exist anymore"
        if settings.exclude_mods and reddit().is_mod(username):
            return "user is a mod"
        return None

    def clear_user(self, username: str) -> None:
        """Helper to clear the outstanding alert data of a user (if present)."""

        if username in self.data_store["outstanding_alerts"]:
            del self.data_store["outstanding_alerts"]

    def get_violations(self, username: str, exclude_automod: bool = True, cache: bool = False) -> list[ViolationInterval]:
        """Gather all of a user's removals and bans, accounting for things that were later reapproved.
        Returns a list of ViolationIntervals, which divide the removals up into intervals between each ban, sorted from earliest to latest."""

        if cache and username in self.cache_violations:
            return self.cache_violations[username]

        removals: dict[str, Removal] = {}
        bans: list[ModNote] = []

        # We iterate in reverse order so we can use a later reapproval to cancel an earlier removal.
        for note in reversed(list(reddit().sub.mod.notes.redditors(username))):
            if note.action in ['removecomment', 'removelink']:
                if not note.reddit_id in removals:
                    removals[note.reddit_id] = Removal()
                removals[note.reddit_id].removal_note = note
            elif note.action == 'addremovalreason':
                if not note.reddit_id in removals:
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
                if not removals[id].removal_note is None and removals[id].removal_note.operator != "AutoModerator":
                    continue
                if not removals[id].removal_reason is None and removals[id].removal_reason.operator != "AutoModerator":
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
        if not expiration_duration is None and datetime.now(timezone.utc) >= datetime.fromtimestamp(removal.date, timezone.utc) + relativedelta(months=expiration_duration):
            return 0

        # Get base point cost
        point_cost = self.point_map[reason]

        # Check for manual point exception in mod note
        if settings.custom_point_mod_notes:
            note = self.get_thing(removal.target_id, cache=cache).mod_note
            if not note is None:
                result = re.search(r"\[(\d+)\]", note)
                if not result is None:
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
        if not reason is None:
            log.debug(f"Skipping u/{username} and clearing record: {reason}.")
            self.clear_user(username)
            return

        log.debug(f"Scanning u/{username}.")

        # Get point total
        total = self.get_user_total(username, cache=cache)
        log.debug(f"u/{username} has {total} points.")

        # Check total against threshold and act if necessary
        if total >= settings.point_threshold:
            log.info(f"u/{username} has {total} points, which is over the threshold ({settings.point_threshold}).")
            self.act_on(username, cache=cache)

    def act_on(self, username: str, cache: bool = False) -> None:
        """Act on a user hitting the threshold.
        Bans them and/or sends the mods a modmail warning, depending on your settings.
        Should only be called once you have determined that the user passed the threshold."""

        # Double check that the user isn't already banned (though we should have seen it in the mod notes if they were)
        if next(reddit().sub.banned(username), None) is not None:
            log.info(f"u/{username} is already banned; skipping action.")
            return

        # Handle autoban
        didBan = False
        if settings.autoban_mode in [2, 3]:
            log.info(f"Banning u/{username} for {'TBD - duration'} for passing the point threshold.")

            if settings.dry_run:
                log.info(f"[DRY RUN: would have banned u/{username} for {'TBD - duration'}.]")
            else:
                raise NotImplementedError()  # TBD

        # Handle modmail notification
        if settings.autoban_mode in [1, 2]:
            # Get the most recent ban ID (or "" if there was none) for tracking purposes
            violations = self.get_violations(username, cache=cache)
            last_ban_id = "" if len(violations) == 1 else violations[-2].ban.id

            # Make sure we haven't sent this alert already for a previous removal
            if username in self.data_store["outstanding_alerts"] and self.data_store["outstanding_alerts"][username]["ban"] == last_ban_id:
                log.debug(f"Skipping modmail action for u/{username} because we've done it already for a past removal and they haven't been banned since.")
                return

            log.info(f"Sending modmail to mods about u/{username} for passing the point threshold.")

            # Prepare modmail message
            interval = violations[-1]
            message = f"u/{username}'s violations have reached {self.get_user_total(username, cache=cache)} points and passed the {settings.point_threshold}-point threshold:\n\n"
            message += interval.to_string(self, cache=cache, relevant_only=True)
            message += f"\n{'A' if didBan else 'No'} ban has been issued."
            if not didBan:
                message += f" You can ban them [here](https://www.reddit.com/r/{settings.subreddit}/about/banned)."

            # Send modmail
            modmail = reddit().send_modmail(subject=f"{'Ban' if didBan else 'Point'} alert for u/{username}", body=message)

            # Record the fact that we sent this alert, so we don't send another one for the next removal
            self.data_store["outstanding_alerts"][username] = {"ban": last_ban_id, "modmail": modmail.id}
