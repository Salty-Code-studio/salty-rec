# PyInstaller recipe for the Windows build. Run from the repo root:  pyinstaller packaging/saltyrec.spec
# Expects ffmpeg.exe + ffprobe.exe in packaging/ffmpeg and a ggml model in models/ (the CI workflow fetches both).
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).parent
datas = [(str(ROOT / "saltyrec/assets"), "saltyrec/assets"),
         (str(ROOT / "models"), "models"),
         (str(ROOT / "packaging/ffmpeg"), "ffmpeg")]
binaries, hidden = [], ["saltyrec.app", "saltyrec.selftest", "saltyrec.winkeys", "saltyrec.windows", "saltyrec.loopback"]
for pkg in ("pywhispercpp", "_pywhispercpp"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception:
        pass
datas += collect_data_files("soundcard")

a = Analysis([str(ROOT / "packaging/entry.py")], pathex=[str(ROOT)], binaries=binaries, datas=datas,
             hiddenimports=hidden, excludes=["tkinter"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SaltyRec", console=False,
          icon=str(ROOT / "packaging/icon.ico"))
# same app with a console: errors print instead of hiding in a pop-up. Used by CI and for support.
check = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SaltyRecCheck", console=True,
            icon=str(ROOT / "packaging/icon.ico"))
coll = COLLECT(exe, check, a.binaries, a.datas, name="SaltyRec")
