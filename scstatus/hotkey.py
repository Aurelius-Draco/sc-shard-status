"""An optional single hotkey for "Mark this moment", through Windows' own RegisterHotKey.

The app never watches the keyboard: Windows tells it when this one combination is pressed, and nothing else.
Off unless you pick a combination on the Set up tab.
"""

import threading

from .config import say

# Choices offered on the Set up tab: label -> (modifiers, virtual key)
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
CHOICES = {
    "ctrl+alt+m": (MOD_CONTROL | MOD_ALT, 0x4D),
    "ctrl+shift+m": (MOD_CONTROL | MOD_SHIFT, 0x4D),
    "ctrl+alt+f9": (MOD_CONTROL | MOD_ALT, 0x78),
    "ctrl+alt+f10": (MOD_CONTROL | MOD_ALT, 0x79),
}
LABELS = {"ctrl+alt+m": "Ctrl+Alt+M", "ctrl+shift+m": "Ctrl+Shift+M", "ctrl+alt+f9": "Ctrl+Alt+F9",
          "ctrl+alt+f10": "Ctrl+Alt+F10"}
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012


class Hotkey:
    def __init__(self, on_press):
        self.on_press = on_press
        self.combo = None
        self.status = "off"
        self._thread = None
        self._tid = None

    def set(self, combo):
        """Switch to a combination from CHOICES, or None for off."""
        self.stop()
        self.combo = combo if combo in CHOICES else None
        if not self.combo:
            self.status = "off"
            return self.status
        import os
        if os.name != "nt":
            self.status = "only on Windows"
            return self.status
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self.combo, ready), daemon=True)
        self._thread.start()
        ready.wait(2)
        return self.status

    def stop(self):
        if self._thread and self._tid:
            try:
                import ctypes
                ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            except Exception:
                pass
            self._thread.join(2)
        self._thread = self._tid = None

    def _run(self, combo, ready):
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self._tid = kernel32.GetCurrentThreadId()
        mods, vk = CHOICES[combo]
        if not user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk):
            self.status = f"{LABELS[combo]} is already used by another program; pick another"
            say(f"Hotkey {LABELS[combo]} couldn't be registered (in use elsewhere).")
            ready.set()
            return
        self.status = f"on: {LABELS[combo]}"
        ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.on_press()
                    except Exception as e:
                        say(f"Mark this moment failed: {e}")
        finally:
            user32.UnregisterHotKey(None, 1)
