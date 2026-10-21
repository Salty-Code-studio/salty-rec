import sys

if "--selftest" in sys.argv:
    from .selftest import main
else:
    from .app import main
main()
