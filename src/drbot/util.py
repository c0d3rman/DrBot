from __future__ import annotations
from typing import Any
import json
import datetime


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
