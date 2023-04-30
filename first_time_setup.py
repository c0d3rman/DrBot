import socket
import random
import questionary
import tomlkit
import re
import sys
import praw
import webbrowser
import os.path


SETTINGS_PATH = "data/settings.toml"
DEFAULT_SETTINGS_PATH = "src/default_settings.toml"
DRBOT_CLIENT_ID_PATH = "src/drbot_client_id.txt"


def reddit_login():
    """Log in to reddit and get a refresh token to use in the future.
    Adapted from https://praw.readthedocs.io/en/latest/tutorials/refresh_token.html#obtaining-refresh-tokens"""

    def receive_connection():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("localhost", 8080))
        server.listen(1)
        client = server.accept()[0]
        server.close()
        return client

    def send_message(client, message):
        body = f"<html><body><p>{message}</p></body></html>"
        client.send(f"""HTTP/1.1 200 OK
Content-Type: text/html; encoding=utf8
Content-Length: {len(body)}

{body}""".encode("utf-8"))
        client.close()

    # The scopes DRBOT needs - see https://praw.readthedocs.io/en/latest/tutorials/refresh_token.html#reddit-oauth2-scopes
    scopes = [
        "identity",  # Basic - know the username of the account we log into.
        "modcontributors",  # For banning users.
        "modlog",  # For reading the modlog.
        "modmail",  # For sending modmail to mods.
        "modself",  # Unused - for accepting mod invites.
        "modwiki",  # For making DRBOT's wiki pages mod-only.
        "read",  # For reading posts/comments.
        "structuredstyles",  # For reading the sidebar in SidebarSyncAgent.
        "wikiedit",  # For editing the DRBOT data stored in the wiki.
        "wikiread"  # For editing the DRBOT data stored in the wiki.
    ]

    # Get ID
    with open(DRBOT_CLIENT_ID_PATH, "r") as f:
        drbot_client_id = f.read()

    # Set up local agent
    reddit = praw.Reddit(
        client_id=drbot_client_id,
        client_secret=None,
        redirect_uri="http://localhost:8080/",
        user_agent="DRBOT")

    # Get authentication URL and open it for the user
    state = str(random.randint(0, 65000))
    url = reddit.auth.url(duration="permanent", scopes=scopes, state=state)
    print(f"Your browser should take you to the reddit login page, or click this link: {url}")
    webbrowser.open(url, new=0, autoraise=True)

    # Receive the callback from Reddit with the refresh token
    client = receive_connection()
    data = client.recv(1024).decode("utf-8")
    param_tokens = data.split(" ", 2)[1].split("?", 1)[1].split("&")
    params = {key: value for (key, value) in [token.split("=") for token in param_tokens]}

    # Confirm the state matches
    if state != params["state"]:
        message = f"State mismatch. Expected: {state} Received: {params['state']}"
        send_message(client, message)
        raise Exception(message)
    elif "error" in params:
        send_message(client, params["error"])
        raise Exception(params["error"])

    # Get the refresh token
    refresh_token = reddit.auth.authorize(params["code"])
    send_message(client, f"Success! You can close this tab now.<br/><br/>If you need it, refresh token: {refresh_token}")

    return refresh_token


def validate_manual_login(client_id, client_secret, username, password):
    """Check that a manual login is valid by trying to authenticate."""

    try:
        if not praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=f"DRBOT",
            check_for_async=False  # If this isn't here PRAW complains
        ).user.me() is None:
            return True
    except:
        pass
    return "Failed to log in."


def main():
    answers = {}

    print("""Welcome to DRBOT.
This script will help you set up the required settings to make DRBOT work for your sub.
""")

    if os.path.isfile(SETTINGS_PATH):
        choices = ["Keep it (and exit)", "Modify it", "Discard it"]
        decision = questionary.select(
            f"There's already a settings file in {SETTINGS_PATH}. What do you want to do with it?",
            choices=choices, default=choices[0]).unsafe_ask()
        if decision == choices[0]:
            raise KeyboardInterrupt
        elif decision == choices[1]:
            answers["_modify_existing_file"] = True

    answers["subreddit"] = questionary.text(
        "What subreddit is this for? r/",
        validate=lambda s: bool(re.match(r"^[A-Za-z0-9_]{3,21}$", s))).unsafe_ask()

    print("""DRBOT needs an account with mod permissions on your sub.
It's strongly recommended to create a new account instead of using a real human's account.""")

    choices = ["Through Reddit (safest)", "Manually"]
    if questionary.select("How would you like to login?", choices=choices, default=choices[0]).unsafe_ask() == choices[0]:
        answers["refresh_token"] = reddit_login()
    else:
        input("""
This method is less safe as it involves storing the account password in plaintext,
so don't use it unless you have a good reason.
Log in to the bot's mod account, then go to:
https://www.reddit.com/prefs/apps/
You'll need to create a new application.
Choose 'script' as the option and put http://localhost:8080/ as the redirect URI.
Press ENTER to continue...
""")

        answers["client_id"] = questionary.text("What is the ID right under 'personal use script'?").unsafe_ask()
        answers["client_secret"] = questionary.password("What is the string next to 'secret'?").unsafe_ask()
        answers["username"] = questionary.text(
            "Username? u/",
            validate=lambda s: bool(re.match(r"^[A-Za-z0-9_-]{1,20}$", s))).unsafe_ask()
        answers["password"] = questionary.password(
            "Password?",
            validate=lambda p: validate_manual_login(answers["client_id"], answers["client_secret"], answers["username"], p),
            validate_while_typing=False).unsafe_ask()


    return answers


if __name__ == "__main__":
    try:
        answers = main()
    except KeyboardInterrupt:
        print("Cancelling setup. No changes have been made. Goodbye")
        sys.exit(1)
    print("All done! Saving settings...")

    baseSettingsPath = DEFAULT_SETTINGS_PATH
    if "_modify_existing_file" in answers:
        baseSettingsPath = SETTINGS_PATH
        del answers["_modify_existing_file"]
    with open(baseSettingsPath, "r") as f:
        settings = tomlkit.parse(f.read())
    settings.update(answers)
    with open(SETTINGS_PATH, "w") as f:
        f.write(tomlkit.dumps(settings))

    print("If you want to change advanced settings, do so directly in data/settings.toml")
    print("You're ready to use DRBOT. Goodbye!")
