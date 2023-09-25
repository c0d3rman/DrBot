from __future__ import annotations
from datetime import datetime, timezone
from praw.models import ModAction, Comment, Submission
from praw.exceptions import ClientException
from ..log import log
from ..reddit import reddit
from ..Botling import Botling


class SelfModerationWatcher(Botling):
    """WARNING: very slow.
    Scans the modlog for self-moderation, i.e. when a moderator
    - Approves their own comment/post
    - Moderates a comment on their own post
    - Moderates a comment in the reply tree below their own comment
    Does not include mods removing their own posts/comments."""

    default_settings = {
        "exempt_flairs": [],  # You can allow self-moderation in posts with specific flairs, e.g. meta posts. Use the flair ID.
        "exempt_authors": ["AutoModerator"],  # This Botling won't care about moderating anything posted/commented by these authors. You can add DrBot's username here.
        "exempt_mods": ["AutoModerator"],  # Mods that are allowed to self-moderate. You can add DrBot's username here.
        "modmail": True,  # When we find a case of self-moderation, should we send a modmail about it? (Otherwise we just log)
    }

    def setup(self) -> None:
        self.cache: dict[str, bool] = {}
        self.DR.streams.modlog.subscribe(self, self.handle, self.start_run)

    def start_run(self) -> None:
        log.debug("Invalidating cache.")
        self.cache = {}

    def handle(self, item: ModAction) -> None:
        # Check for exempt mods
        if item._mod in self.DR.settings.exempt_mods:
            return

        # Check for relevant mod action type
        if item.action not in ["approvecomment", "removecomment", "approvelink"]:
            return

        # Check for exempt authors
        if item.target_author in self.DR.settings.exempt_authors:
            log.debug(f"Ignoring self-moderation of {item.target_fullname} (mod action {item.id}) because the author u/{item.target_author} is exempt.")
            return

        # Check for exempt flair, guarding for no flair
        moderated_item = reddit.DR.get_thing(item.target_fullname)
        relevant_post = moderated_item if isinstance(moderated_item, Submission) else moderated_item.submission
        try:
            if relevant_post.link_flair_template_id in self.DR.settings.exempt_flairs:
                log.debug(f"Ignoring self-moderation of {item.target_fullname} (mod action {item.id}) because it has exempt flair.")
                return
        except AttributeError:
            pass

        # Do the actual self-moderation check
        if self.is_self_moderated(item._mod, item.target_fullname):
            log.info(f"Self-moderation detected by u/{item._mod} in {item.target_fullname} on {datetime.fromtimestamp(item.created_utc, timezone.utc)}.")
            if self.DR.settings.modmail:
                reddit.DR.send_modmail(subject=f"Self-moderation by u/{item._mod}",
                                       body=f"On {datetime.fromtimestamp(item.created_utc, timezone.utc)}, u/{item._mod} {'removed' if item.action.startswith('remove') else 'approved'} [this {'post' if isinstance(moderated_item, Submission) else 'comment'}](https://reddit.com{item.target_permalink}) despite being involved upstream of it.")

    def is_self_moderated(self, mod: str, fullname: str) -> bool:
        """Scans a given reddit object and its parents for any instances of the given mod as an author."""

        if fullname in self.cache:
            return self.cache[fullname]

        # Wrapper function for return handling
        def inner_scan() -> bool:
            ancestor: Comment | Submission = reddit.DR.get_thing(fullname)
            # Check the comment and all its ancestors (if it's a comment)
            refresh_counter = 0
            while isinstance(ancestor, Comment):
                if ancestor.author == mod:
                    return True
                if refresh_counter % 9 == 0:  # This refresh mechanism is for minimizing requests, see https://praw.readthedocs.io/en/latest/code_overview/models/comment.html#praw.models.Comment.parent
                    try:
                        ancestor.refresh()
                    except ClientException:
                        log.warning(f"Missing item {ancestor.fullname}. Technically this might cause self-moderation to be missed, but it's very unlikely and probably safe to ignore.")
                refresh_counter += 1
                ancestor = ancestor.parent()
            # Final check: the post
            return ancestor.author == mod

        self.cache[fullname] = inner_scan()
        return self.cache[fullname]

    def validate_settings(self) -> None:
        for key in ["exempt_flairs", "exempt_authors", "exempt_mods"]:
            assert isinstance(self.DR.settings[key], list) and all(isinstance(v, str) for v in self.DR.settings[key]), f"{key} must be a list of strings"
        assert isinstance(self.DR.settings.modmail, bool), "modmail must be a bool"
