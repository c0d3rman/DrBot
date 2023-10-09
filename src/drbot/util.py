from __future__ import annotations
from typing import Any, TypeVar, Callable
import json
import datetime
import re
import schedule


class DateJSONEncoder(json.JSONEncoder):
    """Default encoder used to make sure we can write datetimes to JSON."""

    def default(self, o: Any) -> Any:
        if isinstance(o, (datetime.date, datetime.datetime)):
            return {"$date": o.isoformat()}
        return super().default(o)


class DateJSONDecoder(json.JSONDecoder):
    """Default decoder used to make sure we can read datetimes from JSON."""

    def __init__(self, *args: Any, **kwargs: Any):
        def object_hook(d: dict[str, Any]) -> Any:
            if "$date" in d:
                return datetime.datetime.fromisoformat(d["$date"])
            return d
        super().__init__(object_hook=object_hook, *args, **kwargs)


class Singleton:
    """Makes a class into a singleton.
    To make this work, add the following at the beginning of your __init__ (and make sure to call the super-constructor after):

    ```
    if self._initialized:
        return
    ```"""

    _instance = None
    _initialized = False

    def __new__(cls, *args: Any, **kwargs: Any):
        if not cls._instance:
            cls._instance = super(Singleton, cls).__new__(cls)
        return cls._instance

    def __init__(self, *args: Any, **kwargs: Any):
        self._initialized = True


def escape_markdown(text: str | None):
    """Helper to escape markdown, since apparently no one but python-telegram-bot has standardized one of these and I'm not making that a dependency."""

    if text is None:
        return None
    escape_chars = r"\_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)


T = TypeVar("T")


def get_dupes(L: list[T]) -> set[T]:
    """
    Given a list, get a set of all elements which appear more than once.
    """
    seen: set[T] = set()
    seen2: set[T] = set()
    for item in L:
        seen2.add(item) if item in seen else seen.add(item)
    return seen2


def markdown_comment(comment: str) -> str:
    """Generate a DrBot-style markdown comment.
    This comment must be on its own line with nothing before or after it.
    It's recommended to insert a blank line before and after the comment to separate it from any other lines."""
    comment = comment.replace("\\n", "\\\\n").replace("\n", "\\n")  # Escape newlines
    return f"[//DrBot]: # (" + comment.replace("\\n", "\\\\n").replace("\n", "\\n") + ")"


def get_markdown_comments(md: str) -> list[str]:
    """Get all DrBot-style markdown comments from a markdown string.
    Returns an empty list if there are none."""
    comments = re.findall(r"\[//DrBot\]: # \((.*)\)", md)
    return [re.sub(r"(?<!\\)\\n", "\n", s.replace("\\\\n", "\\n")) for s in comments]  # Unescape newlines


def do_once(function: Callable[..., Any]) -> Callable[..., Any]:
    """Turn a function into a one-time task that you can schedule with the schedule library."""
    def f(*args: Any, **kwargs: Any) -> type:
        function(*args, **kwargs)
        return schedule.CancelJob
    return f
