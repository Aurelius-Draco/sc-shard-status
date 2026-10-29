# The known-issues library

`scstatus/library/issues.json` is what the app recognises in Game.log. A copy in `data\issues.json` with a newer
`version` wins over the shipped one, so the library can be updated without a new release.

## A rule

```json
{
  "id": "cargo-no-resource-container",
  "kind": "problem",
  "severity": "high",
  "area": "Cargo",
  "match": {"tag": "CargoSystemUtilities::FindBoxSize",
            "regex": "Item class \\[(?P<item>[^\\]]+)\\] does not have a resource container"},
  "title": "Items can't go through the freight elevator",
  "explain": "The game can't work out a cargo box for {item_name}, ...",
  "fixes": ["..."],
  "ic_title": "Freight elevator: {item_name} has no resource container",
  "builds_seen": ["12913470"],
  "links": [{"title": "Issue Council report", "url": "https://issue-council.robertsspaceindustries.com/..."}]
}
```

- `kind`: `problem` (shown to the player), `noise` (routine, hidden and counted as harmless), `info`.
- `severity`: `high`, `medium` or `low`.
- `match.tag` must equal the `<Tag>` of the log line exactly. `match.regex` is searched in the message after the
  trailing `[Team_...][Area]` tags are removed. Named groups become fields you can use in the text as `{name}`.
  A group called `item` holding an item class also gives `{item_name}`, the in-game name from global.ini.
- `match.level` (optional): `Error`, `Warning` or `Notice`.
- `id` must be unique. A rule with id `disconnect-<code>` takes over the built-in explanation for that disconnect code.
- Never put player handles, account or entity numbers, GUIDs or IP addresses in a rule.

## Writing

Plain direct English. Say what the player will notice, why, and what actually helps. If the honest fix is
"relog", "server hop" or "wait for a patch", say that.

## Testing a rule

```
python status.py --check --file "path\to\Game.log" --minutes 0
python -m pytest -q tests
```
