"""Paths, device discovery and the ffmpeg/whisper jobs that run after a recording."""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

IS_WIN = sys.platform == "win32"
HERE = Path(__file__).parent
# The Windows build ships ffmpeg next to the app (see packaging/); on a Mac it comes from Homebrew.
BUNDLED = Path(getattr(sys, "_MEIPASS", HERE.parent)) / "ffmpeg"


def _tool(name, mac_default):
    exe = name + (".exe" if IS_WIN else "")
    if (BUNDLED / exe).exists():
        return str(BUNDLED / exe)
    return shutil.which(name) or mac_default


FFMPEG = _tool("ffmpeg", "/opt/homebrew/bin/ffmpeg")
FFPROBE = _tool("ffprobe", "/opt/homebrew/bin/ffprobe")
WHISPER = _tool("whisper-cli", "/opt/homebrew/bin/whisper-cli")
MODELS = Path(os.environ.get("SALTYREC_WHISPER_MODELS", Path.home() / ".cache/hyperframes/whisper/models"))
LIBRARY = Path.home() / ("Videos" if IS_WIN else "Movies") / "Salty Rec"
ASSETS = HERE / "assets"
HELPER = HERE / "bin" / "saltyrec-helper"
# Apple's hardware encoder on a Mac, x264 elsewhere
VENC = ["-c:v", "h264_videotoolbox", "-b:v", "10M"] if sys.platform == "darwin" else \
    ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
# Speech engine: whisper.cpp built into the app (pywhispercpp) with a model that ships in the download.
BUNDLED_MODELS = Path(getattr(sys, "_MEIPASS", HERE.parent)) / "models"
FILLERS = {"um", "umm", "uh", "uhm", "uhh", "erm", "er", "ah", "ahh", "eh", "ehm", "euh", "hmm", "mm", "mmm", "uhmm"}
# no console window flashing up for every ffmpeg call on Windows
NO_WINDOW = {"creationflags": 0x08000000} if IS_WIN else {}


def run(args, **kw):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                       **NO_WINDOW, **kw)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout) else "ffmpeg failed")
    return r


# ---------- devices ----------

def helper_devices():
    """Displays and microphones as ScreenCaptureKit sees them (Mac only)."""
    if not HELPER.exists():
        return {"displays": [], "mics": []}
    try:
        r = subprocess.run([str(HELPER), "devices"], capture_output=True, text=True, timeout=10)
        return json.loads(r.stdout)
    except Exception:
        return {"displays": [], "mics": []}


def list_windows():
    """Windows you can record: [{id, app, title, x, y, width, height}] in screen points (pixels on Windows)."""
    if IS_WIN:
        from .windows import list_windows as win_list
        return win_list()
    return helper_devices().get("windows", [])


def window_thumbs():
    """Like list_windows, plus a "thumb" PNG path per window for the visual picker."""
    import tempfile
    out = Path(tempfile.mkdtemp(prefix="saltyrec-thumbs-"))
    if IS_WIN:
        from .windows import list_windows as win_list, window_thumb
        wins = win_list()
        for w in wins:
            t = window_thumb(w, out / f"win-{w['id']}.png")
            if t:
                w["thumb"] = t
        return wins
    if not HELPER.exists():
        return []
    try:
        r = subprocess.run([str(HELPER), "thumbs", "--out", str(out)], capture_output=True, text=True, timeout=20)
        return json.loads(r.stdout)
    except Exception:
        return list_windows()


def list_devices():
    """Returns (screens, cameras, mics) as lists of (avfoundation index, name).
    On Windows: no screens (Qt lists those), cameras and mics as (dshow name, name)."""
    if IS_WIN:
        return _dshow_devices()
    out = subprocess.run([FFMPEG, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                         capture_output=True, text=True).stderr
    video, audio, cur = [], [], None
    for line in out.splitlines():
        if "video devices" in line:
            cur = video
        elif "audio devices" in line:
            cur = audio
        else:
            m = re.search(r"\] \[(\d+)\] (.+)$", line)
            if m and cur is not None:
                cur.append((int(m.group(1)), m.group(2).strip()))
    screens = [d for d in video if d[1].startswith("Capture screen")]
    cams = [d for d in video if not d[1].startswith("Capture screen")]
    return screens, cams, audio


def _dshow_devices():
    try:
        out = subprocess.run([FFMPEG, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                             capture_output=True, text=True, errors="ignore", stdin=subprocess.DEVNULL, **NO_WINDOW).stderr
    except Exception:
        return [], [], []
    cams, mics = [], []
    for line in out.splitlines():
        m = re.search(r'"([^"]+)" \((video|audio)\)', line)
        if m:
            (cams if m.group(2) == "video" else mics).append((m.group(1), m.group(1)))
    return [], cams, mics


# ---------- OS helpers ----------

TRASH = "Recycle Bin" if IS_WIN else "Trash"
FILE_MANAGER = "Explorer" if IS_WIN else "Finder"
MACHINE = "this PC" if IS_WIN else "this Mac"
MOD = "Alt+Shift+" if IS_WIN else "⌥⇧"


def reveal(path: Path):
    """Shows the file selected in Finder or Explorer."""
    if IS_WIN:
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        subprocess.run(["open", "-R", str(path)])


# ---------- library ----------

def new_workdir():
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    d = LIBRARY / stamp
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_meta(folder: Path):
    try:
        return json.loads((folder / "meta.json").read_text())
    except Exception:
        return {"title": folder.name, "created": folder.name, "duration": 0, "title_auto": True}


def write_meta(folder: Path, **changes):
    meta = read_meta(folder)
    meta.update(changes)
    (folder / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def recordings():
    if not LIBRARY.exists():
        return []
    items = [d for d in LIBRARY.iterdir() if d.is_dir() and (d / "video.mp4").exists()]
    return sorted(items, key=lambda d: d.name, reverse=True)


def duration(path: Path) -> float:
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], stdin=subprocess.DEVNULL, **NO_WINDOW,
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def audio_streams(path: Path) -> int:
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, stdin=subprocess.DEVNULL, **NO_WINDOW)
    return len(r.stdout.split())


def has_audio(path: Path) -> bool:
    return audio_streams(path) > 0


def thumbnail(folder: Path):
    v = folder / "video.mp4"
    at = min(1.0, duration(v) / 2)
    run([FFMPEG, "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", v, "-frames:v", "1",
         "-vf", "scale=480:-2", folder / "thumb.jpg"])


# ---------- post-processing ----------

def _normalize(seg: dict, with_audio: bool, folder: Path) -> Path:
    """Every segment leaves with the same layout (video, then one stereo AAC track) and a zero start,
    so the join never mixes track orders. A separately written mic track is folded in here."""
    src, mic = seg["path"], seg.get("mic")
    out = folder / (src.stem + ".norm.mp4")
    args = [FFMPEG, "-y", "-v", "error", "-i", src]
    if not with_audio:
        run(args + ["-map", "0:v:0", "-c:v", "copy", out])
        return out
    inputs = 1
    labels = [f"[0:a:{i}]" for i in range(audio_streams(src))]   # computer sound and mic tracks
    if mic and Path(mic).exists():
        args += ["-itsoffset", f"{seg.get('offset', 0.0):.3f}", "-i", mic]
        labels.append(f"[{inputs}:a:0]")
        inputs += 1
    if not labels:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        labels.append(f"[{inputs}:a:0]")
    if len(labels) > 1:
        graph = "".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=first,aresample=48000[a]"
    else:
        graph = labels[0] + "aresample=48000,apad[a]"
    run(args + ["-filter_complex", graph, "-map", "0:v:0", "-map", "[a]", "-shortest",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ac", "2", out])
    return out


def finalize(folder: Path, segments):
    """Joins pause segments into one fast-start MP4. Segments are dicts from Recorder."""
    segments = [s if isinstance(s, dict) else {"path": Path(s)} for s in segments]
    usable = [s for s in segments if s["path"].exists() and s["path"].stat().st_size > 2048]
    if not usable:
        raise RuntimeError("Nothing was recorded. Check Screen Recording permission in System Settings.")
    with_audio = any(has_audio(s["path"]) or (s.get("mic") and Path(s["mic"]).exists()) for s in usable)
    files = [_normalize(s, with_audio, folder) for s in usable]
    out = folder / "video.mp4"
    if len(files) == 1:
        run([FFMPEG, "-y", "-v", "error", "-i", files[0], "-map", "0", "-c", "copy", "-movflags", "+faststart", out])
    else:
        lst = folder / "segments.txt"
        lst.write_text("".join(f"file '{f.name}'\n" for f in files))
        run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
             "-map", "0", "-c", "copy", "-movflags", "+faststart", out])
        lst.unlink()
    for f in list(folder.glob("seg*")):
        f.unlink(missing_ok=True)
    for f in ("ffmpeg.log", "capture.log"):
        (folder / f).unlink(missing_ok=True)
    thumbnail(folder)
    created = datetime.now()
    write_meta(folder, title=f"Recording {created.strftime('%b %-d, %H:%M')}", title_auto=True,
               created=created.isoformat(timespec="seconds"), duration=duration(out))
    return folder


def _model():
    """A bigger model already on this machine wins; otherwise the one bundled with the app."""
    for name in ("ggml-large-v3-turbo.bin", "ggml-large-v3.bin", "ggml-medium.bin", "ggml-small.bin"):
        if (MODELS / name).exists():
            return MODELS / name
    found = sorted(BUNDLED_MODELS.glob("ggml-*.bin")) if BUNDLED_MODELS.exists() else []
    if found:
        return found[0]
    raise RuntimeError("No speech model found. Run the setup step in the README to fetch it.")


_ENGINE = {}


def _words(wav: Path):
    """[(start, end, word)] in seconds, from whisper.cpp running inside this process."""
    from pywhispercpp.model import Model
    path = str(_model())
    if path not in _ENGINE:
        _ENGINE.clear()
        _ENGINE[path] = Model(path, print_progress=False, print_realtime=False, redirect_whispercpp_logs_to=None)
    # the prompt nudges Whisper to write down ums and uhs instead of tidying them away
    segs = _ENGINE[path].transcribe(str(wav), language="", token_timestamps=True, max_len=1, split_on_word=True,
                                    initial_prompt="Umm, uh, so, like, ehm, you know.")
    return [(s.t0 / 100, s.t1 / 100, s.text.strip()) for s in segs if s.text.strip()]


def _ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _lines(words):
    """Groups words into caption lines: a sentence end, a pause, about 42 characters or 4 seconds."""
    lines, cur = [], []
    for w in words:
        if cur and (len(" ".join(x[2] for x in cur + [w])) > 42 or w[1] - cur[0][0] > 4 or w[0] - cur[-1][1] > 0.8):
            lines.append(cur)
            cur = []
        cur.append(w)
        if w[2][-1:] in ".!?":
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return [(l[0][0], l[-1][1], " ".join(x[2] for x in l)) for l in lines]


def transcribe(folder: Path):
    v = folder / "video.mp4"
    if not has_audio(v):
        raise RuntimeError("This recording has no sound to transcribe.")
    wav = folder / "audio.wav"
    run([FFMPEG, "-y", "-v", "error", "-i", v, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav])
    try:
        words = _words(wav)
    finally:
        wav.unlink(missing_ok=True)
    (folder / "words.json").write_text(json.dumps(words))
    lines = _lines(words)
    (folder / "transcript.srt").write_text(
        "".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(lines, 1)))
    text = " ".join(t for _, _, t in lines).strip()
    (folder / "transcript.txt").write_text(text + "\n")
    meta = read_meta(folder)
    if meta.get("title_auto") and text:
        words = re.sub(r"\s+", " ", text).split(" ")
        first = re.split(r"(?<=[.!?])\s", " ".join(words[:14]))[0]
        title = " ".join(first.split(" ")[:8]).strip(" .,!?")
        if title:
            write_meta(folder, title=title[0].upper() + title[1:])
    return text


def _backup(folder: Path):
    orig = folder / "original.mp4"
    if not orig.exists():
        shutil.copy2(folder / "video.mp4", orig)


def _encode(args_in, filter_args, folder: Path):
    tmp = folder / "edit.mp4"
    run([FFMPEG, "-y", "-v", "error", *args_in, *filter_args,
         *VENC, "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", tmp])
    tmp.replace(folder / "video.mp4")
    for f in ("transcript.srt", "transcript.txt", "words.json"):
        (folder / f).unlink(missing_ok=True)
    thumbnail(folder)
    write_meta(folder, duration=duration(folder / "video.mp4"))


def _cut(folder: Path, keep):
    """Re-encodes video.mp4 keeping only the (start, end) ranges in keep."""
    src = folder / "video.mp4"
    _backup(folder)
    parts = []
    for i, (s, e) in enumerate(keep):
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}];"
                     f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}];")
    graph = "".join(parts) + "".join(f"[v{i}][a{i}]" for i in range(len(keep))) + \
        f"concat=n={len(keep)}:v=1:a=1[v][a]"
    _encode(["-i", src], ["-filter_complex", graph, "-map", "[v]", "-map", "[a]"], folder)


def remove_fillers(folder: Path, pad=0.04):
    """Cuts every um and uh, using the word timings from the transcript. Returns how many were cut."""
    wj = folder / "words.json"
    if not wj.exists():
        transcribe(folder)
    words = json.loads(wj.read_text())
    total = duration(folder / "video.mp4")
    cuts = [(max(0.0, a - pad), min(total, b + pad)) for a, b, w in words
            if re.sub(r"[^\w]", "", w.lower()) in FILLERS and b > a]
    if not cuts:
        return 0
    keep, cursor = [], 0.0
    for a, b in cuts:
        if a > cursor + 0.05:
            keep.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < total - 0.05:
        keep.append((cursor, total))
    _cut(folder, keep)
    return len(cuts)


def trim(folder: Path, start: float, end: float):
    if end - start < 0.5:
        raise RuntimeError("Pick an end point after the start point.")
    _backup(folder)
    src = folder / "video.mp4"
    _encode(["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src], [], folder)


def remove_silences(folder: Path, threshold_db=-35, min_gap=0.7, pad=0.15):
    src = folder / "video.mp4"
    if not has_audio(src):
        raise RuntimeError("No sound in this recording, so there are no silences to find.")
    total = duration(src)
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(src), "-af",
                        f"silencedetect=noise={threshold_db}dB:d={min_gap}", "-f", "null", "-"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, **NO_WINDOW)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    if len(ends) < len(starts):
        ends.append(total)
    keep, cursor = [], 0.0
    for s, e in zip(starts, ends):
        s2, e2 = max(0.0, s + pad), max(0.0, e - pad)
        if s2 > cursor + 0.05:
            keep.append((cursor, s2))
        cursor = max(cursor, e2)
    if cursor < total - 0.05:
        keep.append((cursor, total))
    cut = total - sum(e - s for s, e in keep)
    if not starts or cut < 0.5:
        return 0.0
    _cut(folder, keep)
    return cut


def restore_original(folder: Path):
    orig = folder / "original.mp4"
    if not orig.exists():
        raise RuntimeError("This recording has no edits to undo.")
    orig.replace(folder / "video.mp4")
    for f in ("transcript.srt", "transcript.txt", "words.json"):
        (folder / f).unlink(missing_ok=True)
    thumbnail(folder)
    write_meta(folder, duration=duration(folder / "video.mp4"))


def export_with_captions(folder: Path) -> Path:
    srt = folder / "transcript.srt"
    if not srt.exists():
        transcribe(folder)
    title = re.sub(r"[^\w\- ]+", "", read_meta(folder)["title"]).strip() or "recording"
    out = folder / f"{title} (captions).mp4"
    run([FFMPEG, "-y", "-v", "error", "-i", folder / "video.mp4", "-i", srt,
         "-map", "0", "-map", "1", "-c", "copy", "-c:s", "mov_text",
         "-metadata:s:s:0", "language=und", "-disposition:s:0", "default", "-movflags", "+faststart", out])
    return out


def parse_srt(path: Path):
    """[(start_seconds, text)] for the transcript panel."""
    if not path.exists():
        return []
    rows = []
    for block in re.split(r"\n\s*\n", path.read_text().strip()):
        lines = block.strip().splitlines()
        if len(lines) >= 3:
            m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", lines[1])
            if m:
                h, mi, s, ms = map(int, m.groups())
                rows.append((h * 3600 + mi * 60 + s + ms / 1000, " ".join(lines[2:]).strip()))
    return rows
