# DrBot: A modular Reddit bot to cure your moderation woes.


DrBot is a modular reddit bot framework for automatically performing moderation tasks. It allows you to command a small army of Botlings to do things like:

- Tracking user rule violations to identify and/or ban repeat offenders
- Giving users a list of the removals that got them banned
- Adding mobile-compatible links to all your modmails
- Telling you when the admins do something on your sub
- Keeping your old-reddit and new-reddit sidebars in sync
- Enforcing special user flair requirements across your sub
- Detecting and warning about cases of self-moderation
- Placing special restrictions on post flair based on the day of the week

You can also build your own Botlings to do anything you want, with automatically managed settings, wiki-synced storage, easy access to Streams of new comments/posts/modmail/other stuff, and more.

Subreddits take a lot of work to run and most could benefit from automation, but each sub has its own set of particular tasks and requirements. DrBot aims to be a one-stop shop for building and customizing the perfect bot for any sub with minimal coding.

A script that runs DrBot might look like this:

- Create a `DrBot()` object.
- Create each Botling you want and run `drbot.register(botling)` for each one.
- Call `drbot.run()` to start the main loop.

## Setup

TBD

## FAQ

#### I can't read my moldog because of all the DrBot entries!

Since DrBot constantly does a bunch of stuff, it tends to pollute the modlog. To view your modlog without DrBot's actions, click the "moderator" filter, choose "select all" in the dropdown, and then unselect DrBot's account. (This is also useful for filtering out AutoModerator.)

&nbsp;

<a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/"><img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-sa/4.0/88x31.png" /></a><br />This work is licensed under a <a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0 International License</a>.