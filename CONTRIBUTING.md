# Contributing

Thanks for helping. Verse Shards for PC is a one-person project, so every bug report, idea and test run counts.

## Bugs and ideas

- Use the [issue forms](https://github.com/Aurelius-Draco/sc-shard-status/issues/new/choose): **Something isn't working** for bugs, **Idea** for anything that would make the app more useful. Ideas are always welcome.
- Problems in Star Citizen itself go on the [Issue Council](https://issue-council.robertsspaceindustries.com). Known ones and their workarounds are on [verseshards.com/issues](https://verseshards.com/issues).
- A log message the app should recognise? See [docs/library.md](docs/library.md), or use **Send for review** in the app.
- Security or privacy problems: please report them privately, see [SECURITY.md](SECURITY.md).

## Testers wanted

Got a 1440p, 4K or ultrawide screen? The overlay reader needs readings from as many screen setups as it can get. See [verseshards.com/help](https://verseshards.com/help).

## Running it from source

Python 3.12 or 3.13:

```
pip install -r requirements.txt pytest
python -m pytest -q tests
python status.py
```

The tests also run on every push.

## House rules for code and copy

- Plain, direct Australian English (colour, organise, licence). Say what it means for the player in game.
- No em dashes. Use a comma or a full stop.
- Made-up handles only in tests, fixtures, demos and screenshots. Never a real player's handle, and never real names, account numbers, session ids or IP addresses from a Game.log.
- Crop the in-game QR code and chat out of every screenshot.
- The app only reads the screen (the game's own overlay), Game.log and the game's text file. It never touches the game's memory or network traffic, and never sends mouse or keyboard input. Changes that would break that won't be merged.
- Nothing leaves the player's PC unless they've turned sharing on, and the app shows them what it sends.
- Keep the app working with the site both before and after a site update.

Not affiliated with or endorsed by Cloud Imperium Games.
