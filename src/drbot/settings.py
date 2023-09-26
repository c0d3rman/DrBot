from __future__ import annotations
from typing import Any
import os
import copy
import json
import tomlkit
from tomlkit.items import Item
from dynaconf import Validator, LazySettings
from dynaconf.validator import OrValidator
from .util import Singleton

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .Regi import Regi


class DotDict(dict[Any, Any]):
    """A read-only dictionary that allows dot notation access.
    Also handles unwrapping of tomlkit items."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        for dict_arg in args:
            for k, v in dict_arg.items():
                if isinstance(v, dict) and not isinstance(v, DotDict):
                    v = DotDict(v)
                super().__setitem__(k, v)
        for k, v in kwargs.items():
            if isinstance(v, dict) and not isinstance(v, DotDict):
                v = DotDict(v)
            super().__setitem__(k, v)

    def __setitem__(self, key: Any, value: Any) -> None:
        raise AttributeError(f"This dictionary is read only. You cannot edit the key '{key}'.")

    def __delitem__(self, key: Any) -> None:
        raise AttributeError(f"This dictionary is read only. You cannot edit the key '{key}'.")

    def __getattr__(self, key: Any) -> Any:
        # Unwrap tomlkit items, since they sometimes cause issues when passed to PRAW
        if isinstance(self.__getitem__(key), Item):
            return self.__getitem__(key).unwrap()
        return self.__getitem__(key)

    def __setattr__(self, key: Any, value: Any) -> None:
        self.__setitem__(key, value)

    def __delattr__(self, key: Any) -> None:
        self.__delitem__(key)


class SettingsManager(Singleton):
    """DrBot's settings manager."""

    SETTINGS_DIR = 'settings'
    SETTINGS_FILENAME = 'settings.toml'
    SECRETS_FILENAME = 'secrets.toml'
    DEFAULTS_FILEPATH = 'root_defaults.json'

    with open(os.path.join(os.path.dirname(__file__), DEFAULTS_FILEPATH), "r") as f:
        default_settings: dict[str, Any] = json.load(f)

    def __init__(self) -> None:
        """Instantiate the settings manager.
        Create the settings directory if it doesn't exist and load root settings."""
        if self._initialized:
            return
        super().__init__()
        os.makedirs(self.SETTINGS_DIR, exist_ok=True)
        self.settings = self.process_settings(self)
        try:
            self.validate_settings()
        except Exception as e:
            raise ValueError(f"DrBot found invalid global settings: {repr(e)}") from None

    def separate_settings(self, settings: dict[str, Any], _path: list[str] = []) -> tuple[dict[str, Any], dict[str, Any]]:
        """Divide a nested settings dict into regular settings and secret settings (subtrees that start with _).
        The inverse operation of merge_settings.
        _path is an internal parameter for recursion and should not be used."""
        regular: dict[str, Any] = {}
        secrets: dict[str, Any] = {}
        for k, v in settings.items():
            path = _path + [str(k)]
            if not isinstance(k, str):
                raise ValueError(f"The key '{'→'.join(path)}' is not a string.")
            if isinstance(v, dict):
                # If the key starts with _, this entire subtree is secret
                if k.startswith('_'):
                    secrets[k] = v
                # If it's a non-secret string key, we recurse
                else:
                    r, s = self.separate_settings(v)
                    if r:
                        regular[k] = r
                    if s:
                        secrets[k] = s
            else:
                # A _secret key should end up in secrets
                if k.startswith('_'):
                    secrets[k] = v
                # Anything else (including non-string data keys) should end up in regular
                else:
                    regular[k] = v
        return regular, secrets

    def verify_settings(self, settings: dict[Any, Any], secret: bool, _path: list[str] = []) -> None:
        """Make sure that a settings dict is legal.
        For regular settings, that means no _secret keys at all (except potentially in data).
        For secret settings, that means all paths must have at least one _secret key.
        _path is an internal parameter for recursion and should not be used."""
        for k, v in settings.items():
            path = _path + [str(k)]
            if not isinstance(k, str):
                raise ValueError(f"The key '{'→'.join(path)}' is not a string.")
            # If we find a secret key, error for regular or don't search this path further for secret
            if k.startswith('_'):
                if not secret:
                    raise ValueError(f"The key '{'→'.join(path)}' starts with _ even though it is in the non-secret settings.")
            # If we find a subdict with a non-secret string key, recurse
            elif isinstance(v, dict):
                self.verify_settings(v, secret=secret, _path=path)
            # If we find a non-secret leaf and we're in secret, that means we followed an illegal non-secret path to get here
            elif secret:
                raise ValueError(f"The key '{'→'.join(path)}' has no _secret key in its path, meaning it should be a normal key, not a secret one.")

    def merge_settings(self, regular: dict[str, Any], secrets: dict[str, Any]) -> dict[str, Any]:
        """Combine two nested settings dicts (regular settings + secret settings) into a single dict.
        The inverse operation of separate_settings.
        Assumes the dicts are legal as defined by verify_settings."""
        settings = {**regular}
        for k, v in secrets.items():
            if k in regular:
                if isinstance(v, dict) and isinstance(regular[k], dict):
                    settings[k] = self.merge_settings(regular[k], v)
                else:
                    raise ValueError(f"Duplicate key '{k}' present in both regular and secret settings.")
            else:
                settings[k] = v
        return settings

    def populate_settings(self, settings: dict[str, Any], default_settings: dict[str, Any], discard: bool = False) -> dict[str, Any]:
        """Pull in any relevant keys from the settings dict while initializing any missing keys with their default values.
        If "discard" is true, discards any irrelevant keys from settings (ones not present in default_settings)."""
        output: dict[str, Any] = {} if discard else copy.deepcopy(settings)
        for k, v in default_settings.items():
            if isinstance(v, dict):
                output[k] = self.populate_settings(settings.get(k, {}), v)
            else:
                output[k] = settings.get(k, v)
        return output

    def process_settings(self, target: Regi | SettingsManager) -> DotDict:
        """
        Handle settings loading for a botling or the SettingsManager manager itself.
        Read settings from disk or initialize them using the defaults if they are not present.
        Returns the loaded settings.
        """
        # Get the target directory
        settings_dir = self.SETTINGS_DIR
        if not isinstance(target, SettingsManager):
            settings_dir = os.path.join(settings_dir, target.name)

        # Get the target filepaths
        settings_path = os.path.join(settings_dir, self.SETTINGS_FILENAME)
        secrets_path = os.path.join(settings_dir, self.SECRETS_FILENAME)

        # Read settings (if they exist)
        settings = self.read_file(settings_path)
        secrets = self.read_file(secrets_path)

        # Initialize defaults wherever necessary
        default_settings, default_secrets = self.separate_settings(target.default_settings)
        settings = self.populate_settings(settings, default_settings)
        secrets = self.populate_settings(secrets, default_secrets)

        # Make sure regular settings are regular and secret settings are secret
        self.verify_settings(settings, secret=False)
        self.verify_settings(secrets, secret=True)

        # Merge the settings and provide them to the target
        settings_dict = DotDict(self.merge_settings(settings, secrets))

        # Write the settings back to disk (saving newly-initialized defaults and removing discarded keys)
        # We skip writing empty files
        if settings or secrets:
            os.makedirs(settings_dir, exist_ok=True)
        if settings:
            self.write_file(settings_path, settings)
        if secrets:
            self.write_file(secrets_path, secrets)

        # Return the resulting DotDict back to the caller
        return settings_dict

    def validate_settings(self) -> None:
        """
        Validates the root settings to make sure the user set them correctly.
        """

        settings = LazySettings()
        settings.update(self.settings)  # type: ignore
        settings.validators.register(
            # Required strings
            Validator('subreddit', 'reddit_auth.drbot_client_id', 'logging.log_path', 'config.data_folder_path', 'storage.wiki_page', 'storage.wiki_data_subpage',
                      must_exist=True, is_type_of=str, ne="",
                      messages={"operations": "You must set '{name}' to a string."}),
            # Optional strings
            Validator('logging.praw_log_path', 'storage.local_backup_path',
                      must_exist=True, is_type_of=str,
                      messages={"operations": "'{name}' must be a string, not '{value}'."}),
            # Bools
            Validator('dry_run', 'logging.modmail_errors',
                      must_exist=True, is_type_of=bool,
                      messages={"operations": "'{name}' must be true or false"}),
            # Log levels
            Validator('logging.console_log_level', 'logging.file_log_level',
                      must_exist=True, is_type_of=str, is_in=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                      messages={"operations": "{name} ({value}) must be one of the following: CRITICAL, ERROR, WARNING, INFO, DEBUG"}),
            # Auth
            OrValidator(
                Validator('reddit_auth._refresh_token', is_type_of=str, ne=""),
                Validator('reddit_auth.manual._username', 'reddit_auth.manual._password', 'reddit_auth.manual._client_secret', is_type_of=str, ne=""),
                messages={"combined": "You must authenticate DrBot with either a refresh token or username + password + client_secret."}
            ),
        )  # type: ignore
        settings.validators.validate()

    def read_file(self, filepath: str) -> dict[str, Any]:
        """
        Read settings from a TOML file. If the file does not exist, this returns an empty dict.
        """
        if not os.path.isfile(filepath):
            return {}
        with open(filepath, 'r') as f:
            return tomlkit.load(f)

    def write_file(self, filepath: str, settings: dict[str, Any]) -> None:
        """
            Write settings to a TOML file.
            """
        with open(filepath, 'w') as f:
            tomlkit.dump(settings, f)


settings = SettingsManager().settings

# Create the data path if it doesn't already exists, since other files will assume it does
os.makedirs(os.path.dirname(settings.config.data_folder_path), exist_ok=True)
