import praw
from datetime import datetime
from .config import settings
from .log import log
from .util import get_thing, send_modmail
from .Handler import Handler
from .PointMap import PointMap


class SelfModerationHandler(Handler):
    """Scans the modlog for instances of moderators moderating their own comments,
    comments on their posts, or comments in the reply tree below their own comments."""

    def init(self, data_store: dict, reddit: praw.Reddit):
        super().init(data_store, reddit)
        self.cache = {}

    def start_run(self):
        log.debug("Invalidating cache.")
        self.cache = {}

    def handle(self, mod_action):
        if mod_action.action == "removecomment":
            log.debug(f"Scanning {mod_action.id}.")
            if mod_action._mod == mod_action.target_author or self.is_self_moderated(mod_action._mod, mod_action.target_fullname):
                log.warning(f"Self-moderation detected by u/{mod_action._mod} in {mod_action.target_fullname} on {datetime.fromtimestamp(mod_action.created_utc)}")
                if settings.self_moderation_modmail:
                    send_modmail(self.reddit, subject=f"Self-moderation by u/{mod_action._mod}",
                                 body=f"On {datetime.fromtimestamp(mod_action.created_utc)}, u/{mod_action._mod} took action {mod_action.action} on [this submission](https://reddit.com{mod_action.target_permalink}) despite being involved upstream of it.")

    def is_self_moderated(self, mod: str, fullname: str):
        """Scans a given object and its parents for any instances of the given mod as an author."""

        if fullname in self.cache:
            return self.cache[fullname]

        # Wrapper function for return handling
        def inner_scan():
            ancestor = get_thing(self.reddit, fullname)
            # Check the comment and all its ancestors (if it's a comment)
            refresh_counter = 0
            while type(ancestor) is praw.reddit.models.Comment:
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
