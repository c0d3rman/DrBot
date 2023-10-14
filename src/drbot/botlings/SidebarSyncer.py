from __future__ import annotations
import re
import os
import urllib.request
from urllib.parse import urlparse
from praw.models.reddit import widgets
from praw.exceptions import RedditAPIException
from ..log import log
from ..reddit import reddit
from ..Botling import Botling


class SidebarSyncer(Botling):
    """Takes your new reddit sidebar and changes the old reddit sidebar to match it.
    Keeps any existing old-reddit CSS in place."""

    SIDEBAR_WIKI = "config/sidebar"
    CSS_START_STR = "/* DRBOT START - do not edit */\n"
    CSS_END_STR = "\n/* DRBOT END - do not edit */"

    default_settings = {
        "prefix": "",
        "suffix": ""
    }

    def setup(self) -> None:
        # Some subs don't have an old-reddit sidebar wiki page
        if not reddit.DR.wiki_exists(SidebarSyncer.SIDEBAR_WIKI):
            if self.DR.global_settings.dry_run:
                log.info(f"DRY RUN: would have created the {SidebarSyncer.SIDEBAR_WIKI} wiki page.")
            else:
                reddit.sub.wiki.create(name=SidebarSyncer.SIDEBAR_WIKI, content="", reason="Automated page for DrBot")

        self.sync()  # Sync immediately
        self.DR.scheduler.every(1).days.do(self.sync)  # Schedule a daily sync

    def sync(self) -> None:
        log.debug("Checking for sidebar changes...")
        markdown, css = self.convert_sidebar()

        # Get current CSS and markdown
        current_markdown = reddit.sub.wiki[SidebarSyncer.SIDEBAR_WIKI].content_md.strip()
        current_css = reddit.sub.stylesheet().stylesheet.strip()

        # Preserve any non-DrBot segments of the existing CSS
        result = re.search(fr"^(.*{re.escape(SidebarSyncer.CSS_START_STR)}).*?({re.escape(SidebarSyncer.CSS_END_STR)}.*)$", current_css, re.DOTALL)
        if result is not None:
            css = result.group(1) + css + result.group(2)
        else:
            css = f"{current_css}\n\n{SidebarSyncer.CSS_START_STR}{css}{SidebarSyncer.CSS_END_STR}"

        # Check if there's any change we want to make to the markdown and/or CSS
        if markdown == current_markdown and css == current_css:
            return

        items = [x for x in ['markdown' if markdown != current_markdown else None, 'CSS' if css != current_css else None] if x is not None]
        log.info(f"Sidebar {' and '.join(items)} changed. Syncing new reddit to old reddit.")

        # Check if we're past the maximum size of the sidebar
        if len(markdown) > 10240:
            log.error(f"Sidebar is too long to be synced to old reddit! ({len(markdown)}/10240 characters.) Check log for full markdown.")
            return

        # Sync markdown if it changed
        if markdown != current_markdown:
            log.debug(f"Syncing markdown:\n\n```\n{markdown}\n```")
            if self.DR.global_settings.dry_run:
                log.info(f"DRY RUN: would have changed the old-reddit sidebar markdown.")
            else:
                reddit.sub.wiki[SidebarSyncer.SIDEBAR_WIKI].edit(content=markdown, reason="Automated sidebar sync by DrBot")

        # Sync CSS if it changed
        if css != current_css:
            log.debug(f"Syncing CSS:\n\n```\n{css}\n```")
            if self.DR.global_settings.dry_run:
                log.info(f"DRY RUN: would have changed the old-reddit sidebar CSS.")
            else:
                try:
                    reddit.sub.stylesheet.update(css, reason="Automated DrBot update (sidebar sync)")
                except RedditAPIException:
                    log.error("Reddit rejected invalid CSS upload. This is either due to a CSS error in DrBot, or your sub's CSS is invalid somehow (which usually happens because of a deleted image).")
                    log.debug(f"Offending CSS:\n\n```\n{css}\n```")

    def convert_sidebar(self) -> tuple[str, str]:
        """Convert the new reddit sidebar into markdown and CSS for the old sidebar.."""

        bar = []

        # Prefix
        if self.DR.settings.prefix != "":
            bar.append(self.DR.settings.prefix)

        # ID card
        bar.append(f"#### {self.DR.global_settings.subreddit}\n\n{reddit.sub.widgets.id_card.description}")  # TBD: special styling

        # Sidebar widgets
        image_i = 1
        drbot_css = ""
        for widget in reddit.sub.widgets.sidebar:
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
                reddit.sub.stylesheet.upload(name=name, image_path=uploadpath)

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
                log.warning(f"Widget type {type(widget).__name__} ({widget.shortName}) not supported by SidebarSyncer. Skipping.")

        # TBD: optionally add automated "Filter posts by subject"

        # Suffix
        if self.DR.settings.suffix != "":
            bar.append(self.DR.settings.suffix)

        drbot_css = drbot_css.strip()

        return "\n\n".join(bar).strip(), drbot_css
