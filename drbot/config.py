from dynaconf import Dynaconf, Validator
from dynaconf.validator import OrValidator
from dynaconf.utils.boxing import DynaBox
import sys
import os.path


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


SETTINGS_PATH = os.path.join(os.path.dirname(__file__), '../data/settings.toml')

if not os.path.isfile(SETTINGS_PATH):
    print("There's no settings file. Run first_time_setup.py")
    sys.exit(1)

settings = Dynaconf(
    envvar_prefix="DRBOT",
    settings_files=[SETTINGS_PATH],
    validate_on_update="all",
    validators=[
        OrValidator(
            Validator('refresh_token', ne="", is_type_of=str),
            Validator('client_id', 'client_secret', 'username', 'password', ne="", is_type_of=str),
            messages={"combined": "You must authenticate DRBOT. Run first_time_setup.py"}
        ),
        Validator('subreddit',
                  ne="", is_type_of=str, messages={"operations": "You must set '{name}' in data/settings.toml"}),
        Validator('log_file', 'praw_log_file', 'wiki_page', 'local_backup_file',
                  is_type_of=str, messages={"operations": "Invalid '{name}' in data/settings.toml"}),
        Validator('point_threshold',
                  gt=0, is_type_of=int, messages={"operations": "{name} ({value}) must be at least 1 in data/settings.toml"}),
        Validator('point_config',
                  is_type_of=list, condition=validate_points_config, messages={"condition": "Invalid {name} in data/settings.toml"}),
        Validator('expiration_months', 'modmail_truncate_len',
                  gte=0, is_type_of=int, messages={"operations": "{name} ({value}) must be a whole number (or 0 to turn it off) in data/settings.toml"}),
        Validator('autoban_mode',
                  is_in=[1, 2, 3], messages={"operations": """{name} ({value}) in data/settings.toml must be one of the following:
1: notify the mods
2: autoban and notify the mods
3: autoban silently"""}),
        Validator('console_log_level', 'file_log_level',
                  is_in=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"], messages={"operations": """{name} ({value}) in data/settings.toml must be one of the following:
CRITICAL, ERROR, WARNING, INFO, DEBUG"""}),
        Validator('dry_run', 'exclude_mods', 'custom_point_mod_notes', 'self_moderation_modmail', 'admin_modmail', 'first_time_retroactive_modlog',
                  is_type_of=bool, messages={"operations": "{name} ({value}) in data/settings.toml must be one of: true, false"}),
    ]
)

try:
    settings.validators.validate()
except Exception as e:
    print(e)
    sys.exit(1)
