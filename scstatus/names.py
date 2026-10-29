"""Item names from the game's own text file (global.ini).

The log uses internal class names (Drink_bottle_smoothie_01_a); contracts and the
game's screens use display names (Berry Blend Smoothie). This maps one to the
other. Works with the standard game text or a language pack such as StarStrings.
Only the copy on your PC is read; CIG's files are never shipped with this tool.
"""

from pathlib import Path


class Names:
    def __init__(self, game_dir, language="english"):
        self.by_class = {}
        path = Path(game_dir or ".") / "Data" / "Localization" / language / "global.ini"
        if not path.exists():
            return
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                if not line.lower().startswith("item_name"):
                    continue
                key, _, val = line.rstrip("\n").partition("=")
                key = key.split(",")[0]
                low = key.lower()
                if low.endswith("_short") or "_desc" in low:
                    continue
                cls = key[len("item_name"):].lstrip("_").lower()
                val = val.strip()
                if cls and val and len(val) < 80:
                    self.by_class.setdefault(cls, val)

    def display(self, cls):
        """Display name for an item class, or a tidied class name when unknown."""
        if not cls:
            return ""
        return self.by_class.get(cls.lower()) or self.by_class.get(cls.lower().removesuffix("_scitem")) or cls

    def __len__(self):
        return len(self.by_class)
