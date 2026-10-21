"""Picks the native window tweaks for this OS. Linux and others get harmless no-ops."""
import sys

if sys.platform == "darwin":
    from .macos import brand_process, float_everywhere, hide_from_capture, ignore_mouse, set_level
elif sys.platform == "win32":
    from .windows import brand_process, float_everywhere, hide_from_capture, ignore_mouse, set_level
else:
    def brand_process(): pass
    def float_everywhere(widget): pass
    def hide_from_capture(widget): pass
    def ignore_mouse(widget, ignore): pass
    def set_level(widget, level): pass

IS_MAC, IS_WIN = sys.platform == "darwin", sys.platform == "win32"
