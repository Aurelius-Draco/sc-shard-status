"""Your game settings, saved.

Star Citizen keeps each copy's settings (LIVE, PTU, Tech Preview) in
    <copy>\\user\\client\\0\\Profiles\\default\\attributes.xml     <Attr name="FOV" value="70.5"/>
and custom key binds in actionmaps.xml in the same folder. A patch, a test server or a reinstall sometimes loses
them. This saves LIVE's two files in the app's data folder, compares every copy with the save, and puts the save back
into a copy (only while the game is closed, after backing up what's there to Documents\\Verse Shards\\Settings backups).

A setting missing from attributes.xml means the game uses its default for it. Defaults are only shown where they're
known for certain (checked against a fresh PTU copy on 8 Nov 2026, build 4.10.3); the rest still count when copies
are compared, but are never listed as "changed from the default".

Nothing here leaves the PC.
"""

import datetime as dt
import json
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# -- the copies -----------------------------------------------------------------------------------------------------

COPIES = [("LIVE", "LIVE"), ("PTU", "PTU"), ("TECH-PREVIEW", "Tech Preview")]
EXTRA = [("EPTU", "EPTU"), ("HOTFIX", "Hotfix")]          # shown only when the folder is there
PROFILE = ("user", "client", "0", "Profiles", "default")

# Never compared or put back: which ship is picked in each Arena Commander mode, the saved presets the game manages
# itself, the microphone and camera picked on this PC, retired settings
SKIP = re.compile(r"^(selectedShipURN.*|Preset\d+|FoIPCameraSelection|PreferredAudioInputDeviceHash|.*_DEPRECATED)$")

GROUPS = ["Graphics", "Controls and flight", "Camera and comfort", "Audio", "Interface", "Other"]
SPEC = {1: "Low", 2: "Medium", 3: "High", 4: "Very high"}
WINDOW = {0: "Windowed", 1: "Fullscreen", 2: "Borderless"}


def _spec_name(k):
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", k.split("_", 1)[1]).lower()
    return {"shadow maps": "Shadows", "shadow screen space": "Screen space shadows",
            "planet volumetric clouds": "Planet clouds", "planet terrain virtual textures": "Planet terrain textures",
            "object view distance": "Object view distance", "gas cloud": "Gas clouds",
            "video comms": "Video comms quality"}.get(words, words[:1].upper() + words[1:])


# name -> (plain name, group, kind, default). default None = not known for certain.
# kind: onoff (0/1), pct (0..1 shown as a percent), num, spec (1-4), window
T = {
    "FOV": ("Field of view", "Camera and comfort", "num", 55),
    "GForceHeadBobScale": ("G-force head bob", "Camera and comfort", "pct", 1),
    "GForceBoostZoomScale": ("G-force boost zoom", "Camera and comfort", "pct", 1),
    "ShakeScale": ("Camera shake", "Camera and comfort", "pct", 1),
    "AudioShakeStrength": ("Shake from sound", "Camera and comfort", "pct", None),
    "AutoZoomOnSelectedTarget": ("Zoom on selected target", "Camera and comfort", "onoff", None),
    "AutoZoomOnSelectedTargetStrength": ("Zoom on selected target, strength", "Camera and comfort", "pct", 1),
    "LookAheadAdsEnablesPadlock": ("Padlock when aiming down sights", "Camera and comfort", "onoff", None),
    "LookAheadEnabledTurret": ("Look ahead in turrets", "Camera and comfort", "onoff", None),
    "HoldToggleZoom": ("Zoom: hold or toggle", "Camera and comfort", "num", None),
    "AudioMasterVolume": ("Master volume", "Audio", "pct", 1),
    "AudioMusicVolume": ("Music volume", "Audio", "pct", 1),
    "AudioSfxVolume": ("SFX volume", "Audio", "pct", 1),
    "AudioSpeechVolume": ("Speech volume", "Audio", "pct", 1),
    "AudioShipComputerSpeechVolume": ("Ship computer voice", "Audio", "pct", 1),
    "AudioSimulationAnnouncerVolume": ("Arena Commander announcer", "Audio", "pct", 1),
    "VideoVolume": ("Video volume", "Audio", "pct", 1),
    "AudioShipComputerVerbosityPreset": ("Ship computer chattiness", "Audio", "num", None),
    "AudioDynamicRangePreset": ("Dynamic range", "Audio", "num", None),
    "EnableRaceCommentary": ("Race commentary", "Audio", "onoff", None),
    "SysSpec": ("Graphics quality", "Graphics", "spec", None),
    "FilmGrain": ("Film grain", "Graphics", "onoff", 1),
    "ChromaticAberration": ("Chromatic aberration", "Graphics", "onoff", 1),
    "MotionBlur": ("Motion blur", "Graphics", "num", None),
    "Upscaling": ("Upscaling", "Graphics", "num", None),
    "WindowMode": ("Window mode", "Graphics", "window", None),
    "Width": ("Screen width", "Graphics", "num", None),
    "Height": ("Screen height", "Graphics", "num", None),
    "Resolution": ("Resolution setting", "Graphics", "num", None),
    "AspectModifier": ("Aspect ratio", "Graphics", "num", None),
    "OverscanBorderX": ("Overscan, sides", "Graphics", "num", None),
    "OverscanBorderY": ("Overscan, top and bottom", "Graphics", "num", None),
    "AutoDetect": ("Auto detect graphics", "Graphics", "onoff", None),
    "MouseSensitivity": ("Mouse sensitivity", "Controls and flight", "num", None),
    "ADSMouseSensitivity": ("Aiming down sights sensitivity", "Controls and flight", "num", 1),
    "ZoomSensitivityMultiplier": ("Zoom sensitivity", "Controls and flight", "num", None),
    "IFCS_Setting_SpeedLimiterOn": ("Speed limiter", "Controls and flight", "onoff", None),
    "SpeedThrottleDefaultFixedSpeed": ("Throttle fixed speed", "Controls and flight", "num", None),
    "SprintToggle": ("Sprint: hold or toggle", "Controls and flight", "num", None),
    "PilotEspStrength": ("ESP strength (pilot)", "Controls and flight", "pct", 1),
    "TurretsEspStrength": ("ESP strength (turrets)", "Controls and flight", "pct", 1),
    "TurretsEspDampening": ("ESP dampening (turrets)", "Controls and flight", "pct", None),
    "VehicleWeaponRecoilScale": ("Ship weapon recoil", "Controls and flight", "pct", None),
    "Weapon_Setting_Gimbals_Locked_Pilot": ("Gimbals locked", "Controls and flight", "onoff", None),
    "Weapon_Setting_FallbackConvergenceDistance": ("Fallback convergence distance", "Controls and flight", "num", None),
    "Weapon_Setting_Magnified_UI": ("Magnified weapon HUD", "Interface", "onoff", None),
    "Weapon_Setting_Precision_Lines": ("Precision lines", "Interface", "onoff", None),
    "FlightCoreDisabledSensitivityRotation": ("Rotation sensitivity, flight core off", "Controls and flight", "num", None),
    "FlightCoreDisabledSensitivityTranslation": ("Strafe sensitivity, flight core off", "Controls and flight", "num", None),
    "SalvageAimNudgeSensitivity": ("Salvage aim nudge sensitivity", "Controls and flight", "num", None),
    "VJoyCombinedDeadZone": ("Virtual joystick dead zone", "Controls and flight", "num", None),
    "VJoyMgvCombinedDeadZone": ("Virtual joystick dead zone (ground vehicles)", "Controls and flight", "num", None),
    "VJoyTurretCombinedDeadZone": ("Virtual joystick dead zone (turrets)", "Controls and flight", "num", None),
    "ShowHints": ("Hints", "Interface", "onoff", None),
    "ControlHintsEnabled": ("Control hints", "Interface", "onoff", None),
    "CrosshairOpacity": ("Crosshair opacity", "Interface", "pct", 1),
    "ShowEmissionsText": ("Emissions text", "Interface", "onoff", None),
    "ShipEntryLabelsEnabled": ("Ship entry labels", "Interface", "onoff", None),
    "QRCode": ("QR code on the info overlay", "Interface", "onoff", None),
    "FlightController_Setting_AdvancedHudLabelsEnabled": ("Advanced HUD labels", "Interface", "onoff", None),
    "FlightController_Setting_AdvancedHudNavEnabled": ("Advanced HUD navigation", "Interface", "onoff", None),
    "FlightController_Setting_AdvancedHudScmEnabled": ("Advanced HUD, SCM", "Interface", "onoff", None),
    "FlightController_Setting_LightAmplificationEnabled": ("Light amplification", "Interface", "onoff", None),
}
# Each quality setting under the graphics preset follows the preset until it's changed (fresh PTU: SysSpec 4 and
# every one of these 4, except texture detail and filtering, which top out at 3)
SPEC_FOLLOWS_PRESET = {"SysSpec_Fog", "SysSpec_GasCloud", "SysSpec_ObjectDetail", "SysSpec_ObjectViewDistance",
                       "SysSpec_Particles", "SysSpec_PlanetTerrainVirtualTextures", "SysSpec_PlanetVolumetricClouds",
                       "SysSpec_PostProcessing", "SysSpec_Shading", "SysSpec_ShadowMaps", "SysSpec_ShadowScreenSpace",
                       "SysSpec_TextureGround", "SysSpec_TextureQuality", "SysSpec_VideoComms", "SysSpec_WaterCaustics",
                       "SysSpec_WaterSim"}

_LOOK = {"Forward": "forward", "YawPitch": "pitch and yaw", "Roll": "roll", "VJoy": "virtual joystick",
         "VelocityVector": "velocity vector", "TargetSoft": "soft target", "HorizonAlignment": "horizon",
         "HorizonLookAt": "horizon look at", "JumpPointSpline": "jump points", "QuantumBoostTarget": "quantum boost"}


def info(k):
    """(plain name, group, kind, default) for an attribute; unknown ones go under Other with their own name."""
    if k in T:
        return T[k]
    if k.startswith("SysSpec_"):
        return (_spec_name(k), "Graphics", "spec", None)
    m = re.match(r"^LookAheadStrength(Mgv|Turret)?(\w+)$", k)
    if m:
        where = {"Mgv": " (ground vehicles)", "Turret": " (turrets)"}.get(m.group(1) or "", "")
        return (f"Look ahead, {_LOOK.get(m.group(2), m.group(2).lower())}{where}", "Camera and comfort", "pct", 1)
    if k.startswith("LookAhead"):
        return (re.sub(r"(?<=[a-z])(?=[A-Z])", " ", k).capitalize(), "Camera and comfort", "onoff", None)
    if re.match(r"^(HeadTracking|Headtracking|Tobii|Hmd)", k):
        return (re.sub(r"(?<=[a-z])(?=[A-Z])", " ", k).replace("_", " "), "Camera and comfort", "num", None)
    return (k, "Other", "num", None)


def default_of(k, attrs):
    """The default for one setting in this file, or None when it isn't known for certain."""
    if k in SPEC_FOLLOWS_PRESET:
        p = _num(attrs.get("SysSpec"))
        return p if p in SPEC else None
    return info(k)[3]


def _num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def show(k, v):
    """A value the way a player reads it ("On", "33%", "Very high", "70.5")."""
    if v is None:
        return "Game default"
    kind = info(k)[2]
    n = _num(v)
    if n is None:
        return str(v)
    if kind == "onoff" and n in (0, 1):
        return "On" if n else "Off"
    if kind == "pct":
        return f"{round(n * 100)}%"
    if kind == "spec" and n in SPEC:
        return SPEC[n]
    if kind == "window" and n in WINDOW:
        return WINDOW[n]
    return f"{round(n, 2):g}" if isinstance(n, float) else str(n)


def same(a, b):
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None:
        return abs(na - nb) < 1e-3
    return (a or "") == (b or "")


# -- files ----------------------------------------------------------------------------------------------------------

def profile_dir(copy_dir):
    """The copy's Profiles\\default folder, matching folder names in any case (the game uses both user and USER).
    Prefers the one that has attributes.xml. None if there isn't one."""
    found = []

    def walk(base, parts):
        if not parts:
            found.append(base)
            return
        try:
            kids = [c for c in base.iterdir() if c.is_dir() and c.name.lower() == parts[0].lower()]
        except OSError:
            return
        for c in kids:
            walk(c, parts[1:])
    walk(Path(copy_dir), PROFILE)
    for d in found:
        if (d / "attributes.xml").is_file():
            return d
    return None


def read_attrs(path):
    """{name: value} from an attributes.xml, plus its Version. ({}, None) if it can't be read."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {}, None
    return {a.get("name"): a.get("value", "") for a in root.iter("Attr") if a.get("name")}, root.get("Version")


def write_attrs(path, attrs, version):
    q = lambda s: (str(s).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;"))
    lines = [f'<Attributes Version="{q(version or "35")}">'] + [f' <Attr name="{q(k)}" value="{q(attrs[k])}"/>'
                                                                 for k in sorted(attrs)] + ["</Attributes>", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def read_binds(path):
    """{(action map, action): "input, input"} for every custom key bind in an actionmaps.xml."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {}
    out = {}
    for am in root.iter("actionmap"):
        for ac in am.iter("action"):
            ins = [r.get("input", "") for r in ac.iter("rebind") if r.get("input") is not None]
            if ins:
                out[(am.get("name", ""), ac.get("name", ""))] = ", ".join(ins)
    return out


_KEYS = {"lalt": "Left Alt", "ralt": "Right Alt", "lctrl": "Left Ctrl", "rctrl": "Right Ctrl", "lshift": "Left Shift",
         "rshift": "Right Shift", "comma": "Comma", "semicolon": "Semicolon", "period": "Full stop", "insert": "Insert",
         "delete": "Delete", "space": "Space", "enter": "Enter", "backspace": "Backspace", "tab": "Tab",
         "pgup": "Page Up", "pgdn": "Page Down", "home": "Home", "end": "End", "up": "Up", "down": "Down",
         "left": "Left", "right": "Right", "minus": "Minus", "equals": "Equals", "apostrophe": "Apostrophe",
         "slash": "Slash", "backslash": "Backslash", "lbracket": "[", "rbracket": "]", "grave": "`",
         "mouse1": "Left mouse", "mouse2": "Right mouse", "mouse3": "Middle mouse", "mwheel_up": "Wheel up",
         "mwheel_down": "Wheel down", " ": "Unbound"}


def key_name(inp):
    """kb1_lalt+c -> Left Alt+C; js1_button3 -> Joystick 1 button 3; an empty input is a bind cleared on purpose."""
    out = []
    for one in str(inp).split(", "):
        dev, _, k = one.partition("_")
        if not k.strip():
            out.append("Unbound")
            continue
        parts = []
        for p in k.split("+"):
            if p in _KEYS:
                parts.append(_KEYS[p])
            elif re.fullmatch(r"mouse\d+", p):
                parts.append(f"Mouse button {p[5:]}")
            elif re.fullmatch(r"button\d+", p):
                parts.append(f"button {p[6:]}")
            elif re.fullmatch(r"np_(\w+)", p):
                parts.append("Numpad " + p[3:])
            elif re.fullmatch(r"f\d+|[a-z0-9]", p):
                parts.append(p.upper())
            else:
                parts.append(p.replace("_", " "))
        name = "+".join(parts)
        if dev.startswith("js"):
            name = f"Joystick {dev[2:]} {name}"
        elif dev.startswith("gp"):
            name = f"Gamepad {name}"
        out.append(name)
    return ", ".join(out)


def action_name(action):
    a = re.sub(r"^(v|pc|ui|mobiglas|foip|vehicle|player)_", "", action)
    a = a.replace("_", " ").strip()
    return a[:1].upper() + a[1:]


def documents_dir():
    """The player's Documents folder (wherever Windows has it, OneDrive included)."""
    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except Exception:
            pass
    return Path.home() / "Documents"


def _game_running():
    from .config import running_game_dir
    return running_game_dir() is not None


# -- the feature ----------------------------------------------------------------------------------------------------

class GameSettings:
    def __init__(self, data_dir, game_dir, running=None, documents=None):
        self.folder = Path(data_dir) / "Game settings"
        self.game_dir = Path(game_dir)
        self.running = running or _game_running
        self.documents = documents or documents_dir
        self._cache = {}

    # which copies there are
    def copies(self):
        """[(key, display name, folder)]: LIVE, PTU and Tech Preview always (a missing one is "never launched"),
        EPTU and Hotfix when their folders are there."""
        gd = self.game_dir
        root = gd.parent if gd.name.upper() in {k for k, _ in COPIES + EXTRA} else None
        out = []
        for key, name in COPIES + EXTRA:
            if root is None:
                d = gd if key == "LIVE" else None
            else:
                d = next((c for c in _children(root) if c.name.upper() == key), None)
            if d is None and (key, name) in EXTRA:
                continue
            out.append((key, name, d))
        return out

    def _copy(self, key):
        for k, name, d in self.copies():
            if k == key.upper() or name.lower() == key.lower():
                return k, name, d
        raise ValueError(f"There's no {key} copy of the game here.")

    def _files(self, d):
        p = profile_dir(d) if d else None
        return (p / "attributes.xml", p / "actionmaps.xml") if p else (None, None)

    # the save
    def saved(self):
        try:
            return json.loads((self.folder / "saved.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _saved_sets(self):
        attrs, ver = read_attrs(self.folder / "attributes.xml")
        return attrs, ver, read_binds(self.folder / "actionmaps.xml")

    def save(self, replace=False):
        """Save LIVE's settings and key binds. Replacing an older save needs replace=True; the old one is kept once,
        in Game settings\\previous."""
        old = self.saved()
        if old and not replace:
            raise ValueError("You already have a save. Say yes to replacing it.")
        _, _, d = self._copy("LIVE")
        attrs_f, binds_f = self._files(d)
        if not attrs_f:
            raise ValueError("LIVE has no settings yet. Launch it once, set it up, then save.")
        self.folder.mkdir(parents=True, exist_ok=True)
        if old:
            prev = self.folder / "previous"
            shutil.rmtree(prev, ignore_errors=True)
            prev.mkdir()
            for n in ("attributes.xml", "actionmaps.xml", "saved.json"):
                if (self.folder / n).exists():
                    shutil.copy2(self.folder / n, prev / n)
        shutil.copy2(attrs_f, self.folder / "attributes.xml")
        if binds_f.is_file():
            shutil.copy2(binds_f, self.folder / "actionmaps.xml")
        elif (self.folder / "actionmaps.xml").exists():
            (self.folder / "actionmaps.xml").unlink()
        attrs, _ = read_attrs(self.folder / "attributes.xml")
        meta = {"t": time.time(), "from": "LIVE", "changed": len(changed_list(attrs)),
                "binds": len(read_binds(self.folder / "actionmaps.xml"))}
        (self.folder / "saved.json").write_text(json.dumps(meta), encoding="utf-8")
        self._cache.clear()
        return meta

    # comparing
    def compare(self, key):
        """How one copy differs from the save: [{name, group, saved, now}], or None if it can't be compared."""
        _, _, d = self._copy(key)
        attrs_f, binds_f = self._files(d)
        if not attrs_f or not self.saved():
            return None
        sig = (key, _mt(attrs_f), _mt(binds_f), _mt(self.folder / "saved.json"))
        if self._cache.get(key, (None,))[0] == sig:
            return self._cache[key][1]
        s_attrs, _, s_binds = self._saved_sets()
        c_attrs, _ = read_attrs(attrs_f)
        c_binds = read_binds(binds_f) if binds_f.is_file() else {}
        diff = []
        for k in sorted(set(s_attrs) | set(c_attrs)):
            if SKIP.match(k):
                continue
            sv, cv = s_attrs.get(k), c_attrs.get(k)
            # a setting missing on one side is at the game's default there
            sv_eff = sv if sv is not None else default_of(k, s_attrs)
            cv_eff = cv if cv is not None else default_of(k, c_attrs)
            if sv is None and sv_eff is None:
                continue                      # not in the save and its default isn't known: nothing to put back
            if sv_eff is not None and cv_eff is not None and same(sv_eff, cv_eff):
                continue
            name, group, _, _ = info(k)
            diff.append({"key": k, "name": name, "group": group, "saved": show(k, sv_eff), "now": show(k, cv_eff)})
        diff = fold(diff, "saved", "now")
        for (am, ac) in sorted(set(s_binds) | set(c_binds)):
            if s_binds.get((am, ac)) != c_binds.get((am, ac)):
                diff.append({"key": f"bind:{am}/{ac}", "name": action_name(ac), "group": "Key binds",
                             "saved": key_name(s_binds[(am, ac)]) if (am, ac) in s_binds else "Game default",
                             "now": key_name(c_binds[(am, ac)]) if (am, ac) in c_binds else "Game default"})
        self._cache[key] = (sig, diff)
        return diff

    def state(self):
        """Everything the Set up card shows."""
        saved = self.saved()
        copies = []
        for key, name, d in self.copies():
            attrs_f, _ = self._files(d)
            launched = bool(attrs_f)
            diff = self.compare(key) if launched and saved else None
            st = "never" if not launched else "unsaved" if not saved else "differs" if diff else "match"
            copies.append({"key": key, "name": name, "launched": launched, "state": st,
                           "differs": len(diff or []), "diff": diff or []})
        if saved:
            attrs, _, binds = self._saved_sets()
        else:
            live = self._files(self._copy("LIVE")[2])
            attrs = read_attrs(live[0])[0] if live[0] else {}
            binds = read_binds(live[1]) if live[1] and live[1].is_file() else {}
        groups = {}
        for row in changed_list(attrs):
            groups.setdefault(row["group"], []).append({k: row[k] for k in ("name", "value", "default")})
        return {"saved": saved, "game_running": bool(self.running()),
                "copies": copies,
                "changed": [{"group": g, "settings": groups[g]} for g in GROUPS if g in groups],
                "binds": {"count": len(binds), "list": [{"action": action_name(ac), "key": key_name(v)}
                                                         for (am, ac), v in sorted(binds.items())]},
                "backups_dir": str(self.documents() / "Verse Shards" / "Settings backups")}

    # putting them back
    def restore(self, key):
        """Put the save into one copy. Refused while the game runs. What's there now is backed up first, then the saved
        values are set; the copy's other settings stay as they are. Key binds are replaced with the saved ones."""
        if self.running():
            raise ValueError("Star Citizen is running. Close it first, then put your settings back.")
        if not self.saved():
            raise ValueError("Nothing is saved yet.")
        k, name, d = self._copy(key)
        if d is None:
            raise ValueError(f"{name} isn't installed on this PC.")
        attrs_f, binds_f = self._files(d)
        if not attrs_f:
            raise ValueError(f"{name} has never been launched, so it has no settings to put them into yet. Launch it "
                             "once, close it, then try again.")
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H%M")
        backup = self.documents() / "Verse Shards" / "Settings backups" / f"{name} {stamp}"
        n = 2
        while backup.exists():
            backup = backup.with_name(f"{name} {stamp} ({n})")
            n += 1
        backup.mkdir(parents=True)
        shutil.copy2(attrs_f, backup / "attributes.xml")
        if binds_f.is_file():
            shutil.copy2(binds_f, backup / "actionmaps.xml")
        s_attrs, s_ver, _ = self._saved_sets()
        c_attrs, c_ver = read_attrs(attrs_f)
        merged = dict(c_attrs)
        for a, v in s_attrs.items():
            if not SKIP.match(a):
                merged[a] = v
        write_attrs(attrs_f, merged, c_ver or s_ver)
        if (self.folder / "actionmaps.xml").is_file():
            shutil.copy2(self.folder / "actionmaps.xml", binds_f)
        self._cache.clear()
        return {"copy": name, "backup": str(backup),
                "message": f"{name} is back the way you saved it. What was there is in {backup}."}

    # the flag on Now
    def flag(self, playing_dir, launch_key, dismissed):
        """{copy, differs, examples} when the copy being played isn't set up the saved way, else None. Shown once per
        launch: dismissed is the launch key "Not now" was pressed on."""
        if not self.saved() or launch_key is None or str(launch_key) == str(dismissed):
            return None
        pd = Path(playing_dir).resolve() if playing_dir else None
        for key, name, d in self.copies():
            if d is not None and pd is not None and Path(d).resolve() == pd:
                diff = self.compare(key) or []
                if not diff:
                    return None
                return {"copy": name, "key": key, "differs": len(diff), "launch": str(launch_key),
                        "examples": [x["name"] for x in diff if x["group"] != "Key binds"][:2]}
        return None


def _look_variant(k):
    """LookAheadStrength* settings come in sets (piloting, turrets, ground vehicles); a set is one row for people."""
    m = re.match(r"^LookAheadStrength(Mgv|Turret)?\w+$", k)
    if not m:
        return None
    return {"Mgv": "Look ahead (ground vehicles)", "Turret": "Look ahead (turrets)"}.get(m.group(1) or "", "Look ahead")


def fold(rows, a="value", b="default"):
    """Rows for one look-ahead set become one: "Off" when every changed strength in it is 0%, else "N changed"."""
    out, sets = [], {}
    for r in rows:
        v = _look_variant(r.get("key", ""))
        if v is None:
            out.append(r)
            continue
        if v not in sets:
            sets[v] = dict(r, name=v, n=0, off=True, all_default=True)
            out.append(sets[v])
        x = sets[v]
        x["n"] += 1
        x["off"] = x["off"] and r[a] == "0%"
        x["all_default"] = x["all_default"] and r[b] in ("100%", "Game default")
    for x in sets.values():
        n, off, d = x.pop("n"), x.pop("off"), x.pop("all_default")
        x[a] = "Off" if off else f"{n} changed" if n > 1 else x[a]
        x[b] = "On" if d and (off or n > 1) else x[b]
        x["key"] = "lookahead:" + x["name"]
    return out


def changed_list(attrs):
    """Settings in a file that differ from a default known for certain, in the brief's groups."""
    out = []
    for k in sorted(attrs, key=lambda x: info(x)[0].lower()):
        if SKIP.match(k):
            continue
        d = default_of(k, attrs)
        if d is None or same(attrs[k], d):
            continue
        name, group, _, _ = info(k)
        out.append({"key": k, "name": name, "group": group, "value": show(k, attrs[k]), "default": show(k, d)})
    return fold(out)


def _children(p):
    try:
        return [c for c in Path(p).iterdir() if c.is_dir()]
    except OSError:
        return []


def _mt(p):
    try:
        return p.stat().st_mtime_ns if p else None
    except OSError:
        return None
