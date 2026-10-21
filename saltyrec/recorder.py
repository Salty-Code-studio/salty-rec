"""Capture engines.

Screen modes: the Swift ScreenCaptureKit helper keeps one warm stream for the whole session and writes
each segment on command, so start, pause and resume are instant. It records screen, mic and computer sound.
Camera-only: ffmpeg avfoundation, one process per segment.
Windows: ffmpeg gdigrab (screen) or dshow (camera) per segment, mic through dshow, computer sound through
a WASAPI loopback WAV that finalize() mixes in.
"""
import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QObject, QProcess, QTimer, Signal

from .core import FFMPEG, HELPER, IS_WIN, NO_WINDOW

HIDE_PREFIX = "salty-rec-hide"


class Recorder(QObject):
    state_changed = Signal(str)   # idle | recording | paused
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.state = "idle"
        self.segments: list[dict] = []
        self.workdir: Path | None = None
        self.opts = {}
        self._done_ms = 0
        self._clock = QElapsedTimer()
        self._running = False             # the clock only runs once frames are really being written
        # helper engine
        self.helper: QProcess | None = None
        self._ready = False
        self._pending: str | None = None
        self._buf = ""
        # ffmpeg engine
        self.proc = None
        self._cam_size = True
        self._log = None
        self._loop = None
        self._watch = QTimer(self, interval=500, timeout=self._check_ffmpeg)

    def configure(self, **opts):
        """mode, display, mic_uid, system, cam, mic_index"""
        self.opts = opts

    @property
    def mode(self):
        return self.opts.get("mode", "both")

    @property
    def native(self):
        return self.mode != "cam" and not IS_WIN

    # ---- lifecycle ----
    def prepare(self):
        """Warm up capture while the countdown runs."""
        if self.native and self.helper is None:
            self._launch_helper()

    def start(self, workdir: Path):
        self.workdir, self.segments, self._done_ms, self._cam_size = workdir, [], 0, True
        self._set("recording")
        self._new_segment()

    def pause(self):
        if self.state != "recording":
            return
        self._stop_clock()
        if self.native:
            self._send("pause")
        else:
            self._end_ffmpeg()
        self._set("paused")

    def resume(self):
        if self.state == "paused":
            self._set("recording")
            self._new_segment()

    def stop(self) -> list[dict]:
        self._stop_clock()
        if self.native:
            self._shutdown_helper()
        elif self.state == "recording":
            self._end_ffmpeg()
        self._set("idle")
        return list(self.segments)

    def cancel(self):
        self.stop()
        if self.workdir:
            shutil.rmtree(self.workdir, ignore_errors=True)

    def abort_prepare(self):
        if self.state == "idle":
            self._shutdown_helper()

    def elapsed_ms(self) -> int:
        return self._done_ms + (self._clock.elapsed() if self._running else 0)

    def _start_clock(self):
        if not self._running and self.state == "recording":
            self._clock.start()
            self._running = True

    def _stop_clock(self):
        if self._running:
            self._done_ms += self._clock.elapsed()
            self._running = False

    def _new_segment(self):
        n = len(self.segments)
        seg = self.workdir / (f"seg{n:03d}.mp4" if self.native else f"seg{n:03d}.mkv")
        if self.native:
            self.prepare()
            if self._ready:
                self._send(f"resume {seg}")
            else:
                self._pending = str(seg)
        else:
            self._spawn_ffmpeg(seg)
            self._start_clock()

    # ---- helper engine ----
    def _launch_helper(self):
        o = self.opts
        self._ready, self._pending, self._buf = False, None, ""
        proc = self.helper = QProcess(self)
        proc.readyReadStandardOutput.connect(lambda: self._helper_out(proc))
        proc.finished.connect(self._helper_exit)
        self.helper.start(str(HELPER), [
            "record", "--display", str(o.get("display") or 0), "--mic", o.get("mic_uid") or "none",
            "--system", "1" if o.get("system") else "0", "--hide-title", HIDE_PREFIX, "--parent", str(os.getpid())])

    def _send(self, line):
        if self.helper and self.helper.state() == QProcess.Running:
            self.helper.write((line + "\n").encode())

    def _helper_out(self, proc):
        self._buf += bytes(proc.readAllStandardOutput()).decode(errors="ignore")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._handle(line.strip())

    def _handle(self, line):
        if line.startswith("ready"):
            self._ready = True
            if self._pending:
                self._send(f"resume {self._pending}")
                self._pending = None
        elif line.startswith("started "):
            self._start_clock()
        elif line.startswith("segment "):
            _, offset, path = line.split(" ", 2)
            mic = Path(path + ".mic.m4a")
            self.segments.append({"path": Path(path), "mic": mic if mic.exists() else None,
                                  "offset": 0.0 if offset == "none" else float(offset)})

    def _shutdown_helper(self):
        h = self.helper
        if h is None:
            return
        self.helper = None
        h.finished.disconnect(self._helper_exit)
        if h.state() == QProcess.Running:
            h.write(b"q\n")
            h.closeWriteChannel()
            h.waitForFinished(15000)
        self._buf += bytes(h.readAllStandardOutput()).decode(errors="ignore")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._handle(line.strip())
        self._ready = False
        if h.state() != QProcess.NotRunning:
            h.kill()

    def _helper_exit(self, code, _status):
        proc = self.sender() if isinstance(self.sender(), QProcess) else self.helper
        err = bytes(proc.readAllStandardError()).decode(errors="ignore").strip() if proc else ""
        self.helper = None
        self._ready = False
        if self.state != "idle":
            self._stop_clock()
            self._set("paused")
        self.failed.emit(err.splitlines()[-1] if err else f"Screen capture stopped (code {code}).")

    # ---- ffmpeg engine (camera only) ----
    def _ffmpeg_args(self, seg: Path):
        if IS_WIN:
            return self._win_args(seg)
        mic = self.opts.get("mic_index")
        a = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "avfoundation",
             "-thread_queue_size", "4096", "-framerate", "30", "-pixel_format", "nv12"]
        if self._cam_size:
            a += ["-video_size", "1280x720"]
        a += ["-i", f"{self.opts.get('cam')}:{'none' if mic is None else mic}",
              "-vf", "format=yuv420p", "-r", "30", "-c:v", "h264_videotoolbox", "-b:v", "6M", "-g", "60"]
        a += ["-an"] if mic is None else ["-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
        return [str(x) for x in a] + [str(seg)]

    def _win_args(self, seg: Path):
        o = self.opts
        mic = o.get("mic_uid")
        a = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-thread_queue_size", "1024"]
        if self.mode == "cam":
            dev = f"video={o.get('cam')}" + (f":audio={mic}" if mic else "")
            a += ["-f", "dshow", "-rtbufsize", "256M"]
            if self._cam_size:
                a += ["-video_size", "1280x720"]
            a += ["-framerate", "30", "-i", dev]
        else:
            a += ["-f", "gdigrab", "-framerate", "30", "-draw_mouse", "1"]
            rect = o.get("display_rect")
            if rect:
                x, y, w, h = rect
                a += ["-offset_x", x, "-offset_y", y, "-video_size", f"{w}x{h}"]
            a += ["-i", "desktop"]
            if mic:
                a += ["-f", "dshow", "-thread_queue_size", "1024", "-i", f"audio={mic}"]
        a += ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-r", "30",
              "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-g", "60"]
        a += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000"] if mic else ["-an"]
        return [str(x) for x in a] + [str(seg)]

    def _spawn_ffmpeg(self, seg: Path):
        self._log = open(self.workdir / "capture.log", "ab")
        self.proc = subprocess.Popen(self._ffmpeg_args(seg), stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=self._log, **NO_WINDOW)
        side = None
        if IS_WIN and self.mode != "cam" and self.opts.get("system"):
            from .loopback import Loopback
            side = seg.with_suffix(".system.wav")
            self._loop = Loopback(side)
            self._loop.start()
        self.segments.append({"path": seg, "mic": side, "offset": 0.0})
        self._watch.start()

    def _stop_loopback(self):
        if self._loop:
            self._loop.stop()
            self._loop = None

    def _end_ffmpeg(self):
        self._watch.stop()
        p, self.proc = self.proc, None
        if p is None:
            return
        self._stop_loopback()
        try:
            p.communicate(input=b"q", timeout=10)
        except subprocess.TimeoutExpired:
            p.terminate()
            p.wait(timeout=3)
        self._log.close()

    def _check_ffmpeg(self):
        if self.proc is None or self.proc.poll() is None:
            return
        self._watch.stop()
        self.proc = None
        self._log.close()
        self._stop_loopback()
        if self.mode == "cam" and self._cam_size and self._clock.elapsed() < 3000:
            self._cam_size = False          # camera refused 1280x720, retry at its default size
            seg = self.segments.pop()["path"]
            self._spawn_ffmpeg(seg)
            return
        tail = ""
        try:
            tail = (self.workdir / "capture.log").read_text(errors="ignore").strip().splitlines()[-1]
        except Exception:
            pass
        self._stop_clock()
        self._set("paused")
        self.failed.emit(tail or "Recording stopped unexpectedly.")

    def _set(self, s):
        self.state = s
        self.state_changed.emit(s)
