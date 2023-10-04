from __future__ import annotations
from datetime import datetime, timedelta
from dateutil import tz
from praw.models import Submission
from ..log import log
from ..reddit import reddit
from ..Botling import Botling


class WeekdayFlairEnforcer(Botling):
    """Only allows posts with certain flair during given days of the week."""

    default_settings = {
        "weekdays": [],  # A list of weekday numbers to restrict flairs on - 0 for Sunday, 1 for Monday, etc.
        "allowed_flairs": [],  # A list of flair IDs to allow. Use "" as a list item to allow no flair. If you set this to an invalid option like ["X"] DrBot will give you a list of valid options.
        "timezone": "",  # A timezone to use, e.g. "PST" or "America/Los_Angeles". Leave blank to use your default timezone.
        "only_current": True,  # If on, posts will only be removed during the actual weekday. If you turn this off, in some circumstances the bot can remove old posts or remove posts a day late, which may confuse users.
        "removal_reason_id": ""  # You can set this to a removal reason ID if you want the removals to have a reason. If you set this to an invalid option like "X" DrBot will give you a list of valid options.
    }

    def setup(self) -> None:
        self.timezone = tz.gettz(self.DR.settings.timezone) if self.DR.settings.timezone != "" else tz.tzlocal()
        self.DR.streams.post.subscribe(self, self.handle)

    def handle(self, item: Submission) -> None:
        if self.DR.settings.only_current:
            # Check that it's currently a relevant weekday
            if datetime.now(self.timezone).weekday() not in self.DR.settings.weekdays:
                return
            # Check that the post is from todayish
            if abs(datetime.now(self.timezone) - datetime.fromtimestamp(item.created_utc, self.timezone)) > timedelta(days=1):
                return

        # Check that the post was made on a relevant weekday
        if datetime.fromtimestamp(item.created_utc, self.timezone).weekday() not in self.DR.settings.weekdays:
            return

        # Check that the post doesn't already have a legal flair template ID (guarding for no flair)
        try:
            if item.link_flair_template_id in self.DR.settings.allowed_flairs:
                return
        except AttributeError:
            # Check whether no flair is an allowed flair
            if "" in self.DR.settings.allowed_flairs:
                return

        # Check that the post isn't already removed
        if item.removed:
            return

        # Ignore mod posts
        if reddit.DR.is_mod(item.author):
            return

        # Remove the post
        log.info(f"Removing post {item.fullname} due to illegal weekday flair.")
        if self.DR.global_settings.dry_run:
            log.info(f"DRY RUN: would have removed post {item.fullname}")
        else:
            item.mod.remove(mod_note="DrBot: removed for weekday flair restriction", reason_id=self.DR.settings.removal_reason_id if self.DR.settings.removal_reason_id != "" else None)

        # Make sure the user still exists
        if item.author is None:
            log.info(f"Couldn't message the author of post {item.fullname} about the weekday removal because they don't exist. They may have deleted their account.")
            return

        # Modmail the user
        title = "Your post was removed due to Rule 8: Fresh Friday"
        message = f"""Hi u/{item.author}, your [post](https://reddit.com{item.permalink}) was removed because of Rule 8: Fresh Friday.

On Fridays, all posts must discuss fresh topics. We encourage posts about religions other than Christianity/Islam/atheism. Banned topics include: problem of evil, Kalam, fine tuning, disciple martyrdom, Quranic miracles, classical theism.

To make a post on Friday, you must flair your post with “Fresh Friday.” If your post was on a fresh topic, please post it again with the correct flair."""
        if self.DR.global_settings.dry_run:
            log.info(f"""DRY RUN: would have sent the following removal message to u/{item.author} for item {item.fullname}:
Title: {title}
{message}""")
        else:
            item.mod.send_removal_message(message=message, title=title, type="private_exposed")

    def validate_settings(self) -> None:
        assert isinstance(self.DR.settings.weekdays, list) and all(isinstance(x, int) and 0 <= x and x <= 6 for x in self.DR.settings.weekdays), "weekdays must be a list of numbers from 0 to 6 inclusive, e.g. [0, 1] would be Monday and Tuesday."
        assert len(self.DR.settings.weekdays) > 0, "you must set at least one weekday."

        assert isinstance(self.DR.settings.allowed_flairs, list) and all(isinstance(x, str) for x in self.DR.settings.allowed_flairs), "allowed_flairs must be a list of strings"
        assert len(self.DR.settings.allowed_flairs) > 0, "you must set at least one allowed flair."
        flair_ids = list(x['id'] for x in reddit.sub.flair.link_templates)
        for flair_id in self.DR.settings.allowed_flairs:
            assert flair_id == "" or flair_id in flair_ids, f"flair template ID {flair_id} doesn't exist on your sub. Options:       " + "       ".join(f"{flair['id']}: `{flair['text']}`" for flair in reddit.sub.flair.link_templates)

        assert isinstance(self.DR.settings.timezone, str) and (self.DR.settings.timezone == "" or tz.gettz(self.DR.settings.timezone) is not None), "invalid timezone."
        assert isinstance(self.DR.settings.only_current, bool), "only_current must be true or false"

        assert isinstance(self.DR.settings.removal_reason_id, str), "removal_reason_id must be a string."
        assert self.DR.settings.removal_reason_id == "" or self.DR.settings.removal_reason_id in [x.id for x in reddit.sub.mod.removal_reasons], f"removal reason ID {self.DR.settings.removal_reason_id} doesn't exist on your sub. Options:       " + "       ".join(f"{reason.id}: `{reason.title}`" for reason in reddit.sub.mod.removal_reasons)
