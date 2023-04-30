from praw.models.reddit import widgets
from .config import settings
from .log import log


class SidebarSyncAgent:
    """Takes your new reddit sidebar and changes the old reddit sidebar to match it."""
    SIDEBAR_WIKI = "config/sidebar"

    def __init__(self, reddit):
        self.reddit = reddit

    def run(self) -> None:
        subreddit = self.reddit.subreddit(settings.subreddit)
        markdown = self.get_markdown().strip()
        current = subreddit.wiki[SidebarSyncAgent.SIDEBAR_WIKI].content_md.strip()

        if markdown == current:
            return

        log.info("Detected sidebar change - syncing new reddit to old reddit.")
        log.debug(markdown)

        if settings.dry_run:
            log.info("(Not actually changing sidebar because dry_run is on.)")
        else:
            subreddit.wiki[SidebarSyncAgent.SIDEBAR_WIKI].edit(content=markdown, reason="Automated sidebar sync by DRBOT")

    def get_markdown(self) -> str:
        """Get the new reddit sidebar represented as markdown."""

        bar = []

        # TBD: make this non-manual
        bar.append("""[](#/RES_SR_Config/NightModeCompatible)

[](https://discord.gg/wWYnXBu/)

[](http://www.reddit.com/r/DebateReligionCSS/submit?selftext=true&title=%5BOn%2DTopic%5D)""")

        # ID card
        id_card = self.reddit.subreddit(settings.subreddit).widgets.id_card
        bar.append(f"#### {settings.subreddit}\n\n{id_card.description}")  # TBD: special styling

        # Sidebar widgets
        for widget in self.reddit.subreddit(settings.subreddit).widgets.sidebar:
            if type(widget) is widgets.RulesWidget:
                bar.append("#### Rules\n\n" + "\n\n".join(f"{i+1}. **{rule['shortName']}**  \n{rule['description']}" for i, rule in enumerate(widget.data)))
            elif type(widget) is widgets.TextArea:
                bar.append(f"#### {widget.shortName}\n\n{widget.text}")
            else:
                # TBD: make a single image widget + random image widget - https://www.reddit.com/r/csshelp/wiki/snippets/#wiki_random_image_above_sidebar
                log.warning(f"{type(widget).__name__} ({widget.shortName}) not supported by SidebarSyncAgent. Skipping.")

        # TBD make non-manual
        bar.append("""#### Filter posts by subject

[Christianity](http://ch.reddit.com/r/DebateReligion/#ch) [Atheism](http://at.reddit.com/r/DebateReligion/#at) [Islam](http://iz.reddit.com/r/DebateReligion/#iz) [Theism](http://ts.reddit.com/r/DebateReligion/#ts) [Abrahamic](http://ab.reddit.com/r/DebateReligion/#ab) [Buddhism](http://bu.reddit.com/r/DebateReligion/#bu) [Hinduism](http://hz.reddit.com/r/DebateReligion/#hz) [Judaism](http://jz.reddit.com/r/DebateReligion/#jz) [Bah](http://ba.reddit.com/r/DebateReligion/#ba) [Meta](http://me.reddit.com/r/DebateReligion/#me) [Paganism](http://pa.reddit.com/r/DebateReligion/#pa) [All](http://reddit.com/r/DebateReligion/#all)
""")

        return "\n\n".join(bar)
