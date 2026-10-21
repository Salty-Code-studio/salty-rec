"""Native window tweaks for Windows through ctypes. Same API as macos.py, every call is best effort."""
import ctypes

GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
WDA_EXCLUDEFROMCAPTURE = 0x11
HWND_TOPMOST = -1
SWP_FLAGS = 0x0001 | 0x0002 | 0x0010   # no size, no move, no activate


def _user32():
    return ctypes.windll.user32


def _hwnd(widget):
    try:
        return int(widget.winId())
    except Exception:
        return None


def float_everywhere(widget):
    h = _hwnd(widget)
    if h:
        try:
            _user32().SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)
        except Exception:
            pass


def hide_from_capture(widget):
    """Windows 10 2004 and later leave this window out of every screen capture."""
    h = _hwnd(widget)
    if h:
        try:
            _user32().SetWindowDisplayAffinity(h, WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass


def brand_process():
    """Own taskbar group and icon instead of python's."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SaltyCode.SaltyRec")
    except Exception:
        pass


def ignore_mouse(widget, ignore: bool):
    h = _hwnd(widget)
    if not h:
        return
    try:
        u = _user32()
        style = u.GetWindowLongW(h, GWL_EXSTYLE)
        style = (style | WS_EX_LAYERED | WS_EX_TRANSPARENT) if ignore else (style & ~WS_EX_TRANSPARENT)
        u.SetWindowLongW(h, GWL_EXSTYLE, style)
    except Exception:
        pass


def set_level(widget, level: int):
    float_everywhere(widget)


def list_windows():
    """Visible top-level windows with a title: [{id, app, title, x, y, width, height}] in physical pixels."""
    import ctypes.wintypes as wt
    u, out = _user32(), []
    me = ctypes.windll.kernel32.GetCurrentProcessId()

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def each(hwnd, _):
        if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
            return True
        n = u.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        r = wt.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        if pid.value != me and w >= 200 and h >= 150 and buf.value not in ("Program Manager", "Settings"):
            title = buf.value
            out.append({"id": int(hwnd), "app": title.split(" - ")[-1], "title": title,
                        "x": r.left, "y": r.top, "width": w, "height": h})
        return True

    u.EnumWindows(each, 0)
    return out


def activate(win):
    try:
        _user32().SetForegroundWindow(win["id"])
    except Exception:
        pass
