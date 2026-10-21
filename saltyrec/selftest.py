"""Headless check used by CI and handy for support: ffmpeg runs, a short screen capture works,
and the bundled speech engine transcribes. Writes a JSON report next to the app (or to argv path)."""
import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

from . import core


def _check(name, fn, report):
    try:
        report[name] = {"ok": True, "detail": fn()}
    except Exception as e:
        report[name] = {"ok": False, "detail": f"{e}", "trace": traceback.format_exc()[-800:]}


def main():
    out = Path(sys.argv[sys.argv.index("--selftest") + 1]) if len(sys.argv) > sys.argv.index("--selftest") + 1 \
        else Path(tempfile.gettempdir()) / "saltyrec-selftest.json"
    report = {"platform": sys.platform, "ffmpeg_path": core.FFMPEG}
    tmp = Path(tempfile.mkdtemp())

    def ffmpeg():
        r = subprocess.run([core.FFMPEG, "-version"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=60, **core.NO_WINDOW)
        return r.stdout.splitlines()[0]

    def capture():
        src = (["-f", "gdigrab", "-framerate", "15", "-i", "desktop"] if core.IS_WIN
               else ["-f", "lavfi", "-i", "testsrc=size=640x360:rate=15"])
        core.run([core.FFMPEG, "-y", "-v", "error", "-nostdin", *src, "-t", "2",
                  "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                  tmp / "cap.mp4"])
        return f"{core.duration(tmp / 'cap.mp4'):.2f}s"

    def speech():
        folder = tmp / "rec"
        folder.mkdir()
        tone = "sine=frequency=440:duration=3"
        core.run([core.FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=3",
                  "-f", "lavfi", "-i", tone, "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                  folder / "video.mp4"])
        core.transcribe(folder)
        return f"model {core._model().name}, srt {(folder / 'transcript.srt').exists()}"

    def ui_imports():
        from . import app, library, overlays, recorder  # noqa: F401
        return "ok"

    for name, fn in (("ffmpeg", ffmpeg), ("ui", ui_imports), ("capture", capture), ("speech", speech)):
        report["running"] = name                    # written as we go, so a hang shows where it stopped
        out.write_text(json.dumps(report, indent=2))
        _check(name, fn, report)
    report.pop("running", None)
    report["ok"] = all(v["ok"] for v in report.values() if isinstance(v, dict))
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
