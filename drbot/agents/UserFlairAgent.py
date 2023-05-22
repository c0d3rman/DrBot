from drbot import settings, log, reddit
from drbot.agents import Agent
from drbot.stores import DataStore


class UserFlairAgent(Agent):
    """Allows you to set a restricted phrase that can only be used by certain users in their flair.
    Scans every single user who has ever assigned themselves flair in your sub,
    so this is not a good idea for bigger subs.
    Recommended alongside an automod rule, which will instantly catch changed flair if the user makes a comment/post."""

    def __init__(self, data_store: DataStore, restricted_phrase: str, permitted_css_class: str | None = None, name: str | None = None) -> None:
        super().__init__(data_store, name)
        self.restricted_phrase = restricted_phrase
        self.permitted_css_class = permitted_css_class

    def _run(self) -> None:
        log.info(f'Scanning user flair for restricted phrase "{self.restricted_phrase}", which is only permitted for users with CSS class "{self.permitted_css_class}".')
        count = 0
        with reddit() as r:
            flairs = list(r.sub.flair(limit=None))
        for flair in flairs:
            count += 1
            if (flair['flair_css_class'] != self.permitted_css_class
                    and not flair['flair_text'] is None
                    and self.restricted_phrase in flair['flair_text']):
                log.warning(f"u/{flair['user'].name} (class {flair['flair_css_class']}) has banned flair: <{flair['flair_text']}>. Resetting their flair and sending modmail.")
                with reddit() as r:
                    if settings.dry_run:
                        log.info(f"[DRY RUN: would have reset flair for u/{flair['user'].name}]")
                    else:
                        r.sub.flair.delete(flair['user'].name)
                    r.send_modmail(recipient=flair['user'].name,
                                   subject="Your flair was illegal and has been reset",
                                   body=f"""Hi u/{flair['user'].name}, your flair contained a star ⭐ which is only for [star users](https://www.reddit.com/r/DebateReligion/wiki/star_hall_of_fame/).
                             
Your flair has been reset. If you are a star user and this was done in error, please respond to this message.""", add_common=False)

        log.info(f"Scanned flair for {count} users.")
