from __future__ import annotations
import praw
from praw.models import ModAction, Comment
from datetime import datetime, timezone
from drbot import settings, log, reddit
from drbot.agents import Agent
from drbot.handlers import Handler


class SelfModerationHandler(Handler[ModAction]):
    """Scans the modlog for instances of moderators moderating their own comments,
    comments on their posts, or comments in the reply tree below their own comments."""

    def setup(self, agent: Agent[ModAction]) -> None:
        super().setup(agent)
        self.cache = {}

    def start_run(self) -> None:
        log.debug("Invalidating cache.")
        self.cache = {}

    def handle(self, item: ModAction) -> None:
        self_moderation = False
        meta_flair = "b17c1006-ef48-11e1-826b-12313b0ce1e2"  # TBD make general

        if item.action == "removecomment":
            if item._mod == "AutoModerator":
                return
            post = reddit().comment(item.target_fullname).submission
            try:  # Don't check meta threads, guarding for no flair
                if post.link_flair_template_id == meta_flair:
                    log.debug(f"Ignoring self-moderation in {item.id} because it's a meta thread.")
                    return
            except AttributeError:
                pass
            if self.is_self_moderated(item._mod, item.target_fullname):
                self_moderation = True
        elif item.action in ["approvecomment", "approvelink"]:
            if item._mod == item.target_author:
                thing = reddit().get_thing(item.target_fullname)
                if type(thing) is Comment:
                    thing = thing.submission
                try:  # Don't check meta threads, guarding for no flair
                    if thing.link_flair_template_id == meta_flair:
                        log.debug(f"Ignoring self-moderation in {item.id} because it's a meta thread.")
                        return
                except AttributeError:
                    pass
                self_moderation = True

        if self_moderation:
            log.warning(f"Self-moderation detected by u/{item._mod} in {item.target_fullname} on {datetime.fromtimestamp(item.created_utc, timezone.utc)}")
            if settings.self_moderation_modmail:
                reddit().send_modmail(subject=f"Self-moderation by u/{item._mod}",
                                      body=f"On {datetime.fromtimestamp(item.created_utc, timezone.utc)}, u/{item._mod} {'removed' if item.action == 'removecomment' else 'approved'} [this {'comment' if item.target_fullname.startswith('t1_') else 'post'}](https://reddit.com{item.target_permalink}) despite being involved upstream of it.")

    def is_self_moderated(self, mod: str, fullname: str, skip_first: bool = True):
        """Scans a given object and its parents for any instances of the given mod as an author."""

        if fullname in self.cache:
            return self.cache[fullname]

        # Wrapper function for return handling
        def inner_scan():
            ancestor = reddit().get_thing(fullname)
            # Check the comment and all its ancestors (if it's a comment)
            refresh_counter = 0
            while type(ancestor) is Comment:
                if ancestor.author == mod:
                    return True
                if refresh_counter % 9 == 0:  # This refresh mechanism is for minimizing requests, see https://praw.readthedocs.io/en/latest/code_overview/models/comment.html#praw.models.Comment.parent
                    try:
                        ancestor.refresh()
                    except praw.exceptions.ClientException:
                        log.warning(f"Missing comment {ancestor.fullname}. Technically this might cause self-moderation to be missed, but it's very unlikely and probably safe to ignore.")
                refresh_counter += 1
                ancestor = ancestor.parent()
            # Final check: the post
            return ancestor.author == mod

        self.cache[fullname] = inner_scan()
        return self.cache[fullname]
