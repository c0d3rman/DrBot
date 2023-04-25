
from dynaconf import Dynaconf, Validator
from dynaconf.utils.boxing import DynaBox


def validate_points_config(l):
    for i, c in enumerate(l):
        i += 1  # Convert from 0-indexed to 1-indexed
        if not type(c) is DynaBox:
            print(f"Broken removal reason #{i}: {c}")
            return False
        if not ("id" in c and type(c["id"]) is str):
            print(f"Missing or invalid 'id' for removal reason #{i}")
            return False
        if not ("points" in c and type(c["points"]) is int and c["points"] >= 0):
            print(f"Missing or invalid 'points' for removal reason #{i} ({c['id']}) - must be a whole number >= 0")
            return False
        if "expires" in c and not (type(c["expires"]) is int and c["expires"] >= 0):
            print(f"Invalid 'expires' for removal reason #{i} ({c['id']}) - must be a whole number of months >= 0")
            return False
        for k in c:
            if not k in ["id", "points", "expires"]:
                print(f"Unknown key '{k}' in removal reason #{i} ({c['id']})")
                return False
    return True


settings = Dynaconf(
    envvar_prefix="DRBOT",
    settings_files=['config/settings.toml', 'config/advanced.toml'],
    validate_on_update="all",
    validators=[
        # settings.toml
        Validator('subreddit', 'username', 'password',
                  ne="", is_type_of=str, messages={"operations": "You must set a {name} in config/settings.toml"}),
        Validator('client_id', 'client_secret',
                  ne="", is_type_of=str, messages={"operations": "You must set a {name} in config/settings.toml. You can create it at https://www.reddit.com/prefs/apps/"}),
        Validator('point_threshold',
                  gt=0, is_type_of=int, messages={"operations": "{name} ({value}) in config/settings.toml must be at least 1."}),
        Validator('expiration_months',
                  gte=0, is_type_of=int, messages={"operations": "{name} ({value}) in config/settings.toml must be a whole number (or 0 to turn it off)."}),
        Validator('autoban_mode',
                  is_in=[1, 2, 3], messages={"operations": """{name} ({value}) in config/settings.toml must be one of the following:
1: notify the mods
2: autoban and notify the mods
3: autoban silently"""}),
        Validator('point_config',
                  is_type_of=list, condition=validate_points_config, messages={"condition": "Invalid {name} in config/settings.toml"}),

        # advanced.toml
        Validator('log_file', 'wiki_page', 'local_backup_file', 'praw_log_file',
                  is_type_of=str, messages={"operations": "Invalid setting for {name} in config/advanced.toml"}),
        Validator('console_log_level', 'file_log_level',
                  is_in=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"], messages={"operations": "{name} ({value}) in config/advanced.toml must be one of the following: CRITICAL, ERROR, WARNING, INFO, DEBUG"}),
        Validator('modmail_truncate_len',
                  gte=0, is_type_of=int, messages={"operations": "{name} ({value}) in config/advanced.toml must be a positive number (or 0 to turn it off)."}),
        Validator('dry_run', 'exclude_mods', 'safe_mode',
                  is_type_of=bool, messages={"operations": "{name} ({value}) in config/advanced.toml must be one of: true, false"}),
    ]
)

try:
    settings.validators.validate()
except Exception as e:
    print(e)
