# DrBot - a points-to-ban Reddit moderation bot


DrBot is a reddit bot that automatically monitors a subreddit and tracks removals. Each removal of a user's submission gives that user a certain number of points, and once their points hit some threshold, the bot takes action, either by notifying the mods or automatically banning the user.

A script that runs DrBot might look like this:

- Create a `DrBot()` object.
- Create each Botling you want and run `drbot.register(botling)` for each one.
- Call `drbot.run()` to start the main loop.

## Setup

1. Clone this repo and cd inside.
2. `pip install -r requirements.txt`
3. Run first-time setup: `python first_time_setup.py`. This will also create a settings file for you.
4. Change any other settings you want in `data/settings.toml`.
5. Run the bot: `python main.py`

## Caveats

Re-approving and then re-deleting a comment deletes the removal reason on reddit's side, so if you do this, be aware that DRBOT will treat the removal as having no reason as well.

&nbsp;

<a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/"><img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-sa/4.0/88x31.png" /></a><br />This work is licensed under a <a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0 International License</a>.