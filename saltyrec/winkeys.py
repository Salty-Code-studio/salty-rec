"""Global shortcuts on Windows: RegisterHotKey on a small thread with its own message loop."""
import ctypes
import ctypes.wintypes as wt
import threading

from PySide6.QtCore import QObject, Signal

MOD_ALT, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x4, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
KEYS = {1: ("record", ord("R")), 2: ("pause", ord("P")), 3: ("draw", ord("D")), 4: ("cancel", ord("X"))}


class WinHotkeys(QObject):
    pressed = Signal(str)

    def __init__(self, handler):
        super().__init__()
        self.pressed.connect(handler)          # queued onto the Qt thread
        self._tid = None
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        u = ctypes.windll.user32
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        for hid, (_, vk) in KEYS.items():
            u.RegisterHotKey(None, hid, MOD_ALT | MOD_SHIFT | MOD_NOREPEAT, vk)
        msg = wt.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in KEYS:
                self.pressed.emit(KEYS[msg.wParam][0])
        for hid in KEYS:
            u.UnregisterHotKey(None, hid)

    def stop(self):
        if self._tid:
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
