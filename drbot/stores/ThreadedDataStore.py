from __future__ import annotations
from _collections_abc import dict_items, dict_keys, dict_values
from collections.abc import Iterator
from threading import RLock
from typing import Any
from drbot.stores import DataStore


class ThreadedDataStore(DataStore):
    def __init__(self) -> None:
        self.locks = {}
        self.metalock = RLock()
        super().__init__()

    def get_lock(self, key: Any):
        with self.metalock:
            if not key in self.locks:
                self.locks[key] = RLock()
            return self.locks[key]

    def __getitem__(self, key: Any) -> Any:
        with self.get_lock(key):
            return super().__getitem__(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        with self.get_lock(key):
            super().__setitem__(key, value)

    def __delitem__(self, key: Any) -> None:
        with self.get_lock(key):  # You can't delete the lock - if someone else is waiting on it, they're going to expect it to be there when you release it
            super().__delitem__(key)

    def __contains__(self, key: object) -> bool:
        with self.metalock:
            if not self.locks.__contains__(key):
                return False
            with self.get_lock(key):
                return super().__contains__(key)

    def __len__(self) -> int:
        with self.metalock:
            return super().__len__()

    def __repr__(self) -> str:
        with self.metalock:
            return super().__repr__()

    def __iter__(self) -> Iterator:
        it = super().__iter__()
        with self.metalock:
            while True:
                try:
                    value = next(it)
                except StopIteration:
                    return
                yield value

    def keys(self) -> dict_keys:
        with self.metalock:
            return list(super().keys())  # Return a copy to avoid shenanigans

    def values(self) -> dict_values:
        with self.metalock:
            return list(super().values())  # Return a copy to avoid shenanigans

    def items(self) -> dict_items:
        with self.metalock:
            return list(super().items())  # Return a copy to avoid shenanigans
