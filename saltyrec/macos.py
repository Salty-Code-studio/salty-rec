"""Native window tweaks through PyObjC. Every call is best effort."""


def _nswindow(widget):
    try:
        import objc
        view = objc.objc_object(c_void_p=int(widget.winId()))
        return view.window()
    except Exception:
        return None


def float_everywhere(widget):
    """Stay on top on every Space, over full-screen apps, and when Salty Rec is not the active app."""
    w = _nswindow(widget)
    if w is None:
        return
    try:
        w.setHidesOnDeactivate_(False)
        w.setLevel_(25)                          # NSStatusWindowLevel
        w.setCollectionBehavior_(1 | 16 | 256)   # all Spaces, stationary, full-screen auxiliary
    except Exception:
        pass


def hide_from_capture(widget):
    """Keeps our own controls out of the recording."""
    w = _nswindow(widget)
    if w is not None:
        try:
            w.setSharingType_(0)                 # NSWindowSharingNone
        except Exception:
            pass


def brand_process():
    """Menu bar name 'Salty Rec' instead of 'Python'. Call before QApplication exists."""
    try:
        from Foundation import NSBundle
        info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = "Salty Rec"
    except Exception:
        pass


def ignore_mouse(widget, ignore: bool):
    """Click-through without re-showing the window."""
    w = _nswindow(widget)
    if w is not None:
        try:
            w.setIgnoresMouseEvents_(bool(ignore))
        except Exception:
            pass


def set_level(widget, level: int):
    w = _nswindow(widget)
    if w is not None:
        try:
            w.setLevel_(level)
        except Exception:
            pass
