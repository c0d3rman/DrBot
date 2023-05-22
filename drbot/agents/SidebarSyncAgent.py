import re
import os
import urllib.request
from urllib.parse import urlparse
from praw.models.reddit import widgets
from praw.exceptions import RedditAPIException
from drbot import settings, log, reddit
from drbot.agents import Agent
from drbot.stores import DataStore


class SidebarSyncAgent(Agent):
    """Takes your new reddit sidebar and changes the old reddit sidebar to match it."""
    SIDEBAR_WIKI = "config/sidebar"
    CSS_START_STR = "/* DRBOT START - do not edit */\n"
    CSS_END_STR = "\n/* DRBOT END - do not edit */"

    def __init__(self, data_store: DataStore, name: str | None = None) -> None:
        super().__init__(data_store, name)

        # Some subs don't have an old-reddit sidebar wiki page
        if not reddit().page_exists(SidebarSyncAgent.SIDEBAR_WIKI):
            if settings.dry_run:
                log.info(f"[DRY RUN: would have created the {SidebarSyncAgent.SIDEBAR_WIKI} wiki page.]")
            else:
                reddit().sub.wiki.create(
                    name=SidebarSyncAgent.SIDEBAR_WIKI,
                    content="",
                    reason="Automated page for DRBOT")

    def run(self) -> None:
        markdown = self.get_markdown()
        if markdown is None:
            return
        current = reddit().sub.wiki[SidebarSyncAgent.SIDEBAR_WIKI].content_md.strip()
        if markdown == current:
            return

        log.info("Detected sidebar change - syncing new reddit to old reddit.")
        log.debug(markdown)

        if len(markdown) > 10240:  # Check if we're past the maximum size of the sidebar
            log.error(f"Sidebar is too long to be synced to old reddit! ({len(markdown)}/10240 characters.) Check log for full markdown.")
            return

        if settings.dry_run:
            log.info(f"[DRY RUN: would have changed the old-reddit sidebar content to:\n\n{markdown}\n\n]")
        else:
            reddit().sub.wiki[SidebarSyncAgent.SIDEBAR_WIKI].edit(content=markdown, reason="Automated sidebar sync by DRBOT")

    def get_markdown(self) -> str | None:
        """Get the new reddit sidebar represented as markdown."""

        bar = []

        # TBD: make this non-manual
        bar.append("""[](#/RES_SR_Config/NightModeCompatible)

[](https://discord.gg/wWYnXBu/)

[](http://www.reddit.com/r/DebateReligionCSS/submit?selftext=true&title=%5BOn%2DTopic%5D)""")

        # ID card
        id_card = reddit().sub.widgets.id_card
        bar.append(f"#### {settings.subreddit}\n\n{id_card.description}")  # TBD: special styling

        # Sidebar widgets
        image_i = 1
        drbot_css = ""
        for widget in reddit().sub.widgets.sidebar:
            if type(widget) is widgets.RulesWidget:
                bar.append("#### Rules\n\n" + "\n\n".join(f"{i+1}. **{rule['shortName']}**  \n{rule['description']}" for i, rule in enumerate(widget.data)))
            elif type(widget) is widgets.TextArea:
                bar.append(f"#### {widget.shortName}\n\n{widget.text}")
            elif type(widget) is widgets.ImageWidget:  # Due to CSS restrictions, this only uses the first image from a random image widget
                # Download first image from new reddit and upload to old reddit
                image = widget.data[0]
                name = f"drbot-image-{image_i}"
                downloadpath = f"data/{os.path.basename(urlparse(image.url).path)}"
                uploadpath, _ = urllib.request.urlretrieve(image.url, downloadpath)
                reddit().sub.stylesheet.upload(name=name, image_path=uploadpath)

                # Create widget
                bar.append(f"#### {widget.shortName}\n\n[](#{name})\n&nbsp;")

                # Add the image widget CSS
                drbot_css += f"""a[href="#{name}"] {{
    content: url('%%{name}%%');
    width: 100%;
    height: auto;
    font-size: 0;
}}
"""

                # Increment image counter to avoid conflicts with multiple image widgets
                image_i += 1
            else:
                log.warning(f"Widget type {type(widget).__name__} ({widget.shortName}) not supported by SidebarSyncAgent. Skipping.")

        # If we need to modify CSS, do so here
        drbot_css = drbot_css.strip()
        if drbot_css != "":
            curr_css = reddit().sub.stylesheet().stylesheet
            result = re.search(fr"^(.*{re.escape(SidebarSyncAgent.CSS_START_STR)}).*?({re.escape(SidebarSyncAgent.CSS_END_STR)}.*)$", curr_css, re.DOTALL)
            if result:
                new_css = result.group(1) + drbot_css + result.group(2)
            else:
                new_css = f"{curr_css}\n\n{SidebarSyncAgent.CSS_START_STR}{drbot_css}{SidebarSyncAgent.CSS_END_STR}"
            try:
                reddit().sub.stylesheet.update(new_css, reason="Automated DRBOT update (image widget sync)")
            except RedditAPIException:
                log.error("Reddit rejected invalid CSS upload. This is either due to a CSS error in DRBOT, or your sub's CSS is invalid somehow (which usually happens because of a deleted image).")
                log.debug(new_css)
                return

        # TBD make non-manual
        bar.append("""#### Filter posts by subject

[Christianity](http://ch.reddit.com/r/DebateReligion/#ch) [Atheism](http://at.reddit.com/r/DebateReligion/#at) [Islam](http://iz.reddit.com/r/DebateReligion/#iz) [Theism](http://ts.reddit.com/r/DebateReligion/#ts) [Abrahamic](http://ab.reddit.com/r/DebateReligion/#ab) [Buddhism](http://bu.reddit.com/r/DebateReligion/#bu) [Hinduism](http://hz.reddit.com/r/DebateReligion/#hz) [Judaism](http://jz.reddit.com/r/DebateReligion/#jz) [Bah](http://ba.reddit.com/r/DebateReligion/#ba) [Meta](http://me.reddit.com/r/DebateReligion/#me) [Paganism](http://pa.reddit.com/r/DebateReligion/#pa) [All](http://reddit.com/r/DebateReligion/#all)
""")

        return "\n\n".join(bar).strip()
