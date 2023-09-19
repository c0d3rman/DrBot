# DrBot Architecture Guide

DrBot consists of a central system that manages a collection of Botlings. Each Botling must have a unique `name` (which by default is set to its class name). The main DrBot handles scheduling, user interaction, storage, authentication, settings, and so on. Each Botling that registers with it is provided with the following:

- **Reddit access:** by importing the `reddit` singleton, the Botling can perform operations on reddit (via PRAW) without having to deal with authentication. (TBD: this also provides a centralized dry run mode, and Pushshift/Pullpush access.)
- **Storage:** once registered, a Botling gains access to its `.storage` property, which it can use as a normal `dict`. DrBot handles persistent storage and syncing/loading data from the reddit wiki.
- **Logging:** by importing the `log` singleton, the Botling can easily log information and errors. DrBot handles storing logs to files, modmailing about errors, etc.
- **Settings:** the Botling can declare a `default_settings` dictionary to create some settings that can be used to configure it. It can also override the `validate_settings` method to validate those settings. Once registered, it gains access to its `.settings` property which it can use to access those settings. (TBD: DrBot handles syncing the non-secret settings to the wiki.)
- **Error Handling:** (TBD: Each Botling is handled separately, so that if one crashes it does not impact the others.)
- **Scheduling**: (TBD)
- **Handlers**: (TBD)
- **Utils**: Botlings can import various useful utils from `util`, e.g. functions for dealing with markdown or templates.