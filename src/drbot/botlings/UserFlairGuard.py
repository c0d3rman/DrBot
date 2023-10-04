from __future__ import annotations
from ..log import log
from ..reddit import reddit
from ..Botling import Botling


class UserFlairGuard(Botling):
    """Allows you to set a restricted phrase that can only be used by certain users in their flair, and resets any illegal flairs.
    Scans every single user who has ever assigned themselves flair in your sub, so this is not a good idea for bigger subs.
    When possible, it's recommended to use an automod rule instead, though that will only catch changed flair when the user makes a comment/post."""

    default_settings = {
        "restricted_phrase": "",
        "modmail_message": "",  # Leave blank to send no modmail. You can use the following fill-ins: {username}, {flair}, {restricted_phrase}
        "permitted_css_class": "",  # Leave blank to ban for everyone.
    }

    def setup(self) -> None:
        self.DR.scheduler.every().hour.do(self.scan)

    def scan(self) -> None:
        log.info(f'Scanning user flair.')

        count = 0  # For logging
        for flair in reddit.sub.flair(limit=None):
            count += 1

            if self.DR.settings.permitted_css_class != "" and flair.get('flair_css_class', None) == self.DR.settings.permitted_css_class:
                continue
            if flair.get('flair_text', None) in ["", None]:
                continue
            if self.DR.settings.restricted_phrase not in flair['flair_text']:
                continue

            log.info(f'u/{flair["user"].name} (class "{flair["flair_css_class"]}") has illegal flair "{flair["flair_text"]}". Resetting their flair.')

            if self.DR.global_settings.dry_run:
                log.info(f"DRY RUN: would have reset the flair.")
            else:
                reddit.sub.flair.delete(flair['user'].name)

            if self.DR.settings.modmail_message != "":
                reddit.DR.send_modmail(recipient=flair['user'].name, add_common=False,
                                       subject="Your flair was illegal and has been reset",
                                       body=self.DR.settings.modmail_message.format(username=flair['user'].name, flair=flair["flair_text"], restricted_phrase=self.DR.settings.restricted_phrase))

        log.info(f"Scanned flair for {count} users.")

    def validate_settings(self) -> None:
        assert isinstance(self.DR.settings.restricted_phrase, str) and self.DR.settings.restricted_phrase != "", "You must set a restricted phrase."
        assert isinstance(self.DR.settings.modmail_message, str), 'modmail_message must be a string. If you don\'t want to send a modmail, set it to the empty string "".'
        assert isinstance(self.DR.settings.permitted_css_class, str), 'permitted_css_class must be a string. If you don\'t want to have a permitted CSS class, set it to the empty string "".'
