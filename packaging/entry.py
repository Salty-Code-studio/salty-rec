# Frozen entry point. Imports the app directly: PyInstaller does not bundle saltyrec/__main__.py for runpy.
import sys

if "--selftest" in sys.argv:
    from saltyrec.selftest import main
else:
    from saltyrec.app import main
main()
