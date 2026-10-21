"""Share links through the salty-rec Cloudflare Worker (worker/). Token lives in Application Support, never in the repo."""
import json
import os
import secrets
import string
import urllib.request
import webbrowser
from pathlib import Path

from . import core

CONFIG = (Path(os.environ.get("APPDATA", Path.home())) / "Salty Rec/config.json" if core.IS_WIN
          else Path.home() / "Library/Application Support/Salty Rec/config.json")
PART = 25 * 1024 * 1024


def config():
    try:
        c = json.loads(CONFIG.read_text())
        if c.get("share_base") and c.get("token"):
            return c
    except Exception:
        pass
    raise RuntimeError(f"Sharing is not set up on {core.MACHINE}. See README › Share links.")


def configured():
    try:
        config()
        return True
    except RuntimeError:
        return False


def _req(method, path, data=None, ctype="application/octet-stream", timeout=300):
    c = config()
    req = urllib.request.Request(c["share_base"] + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {c['token']}", "Content-Type": ctype,
                                          "User-Agent": "SaltyRec/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body else {}


def _share_copy(folder: Path) -> Path:
    """A lighter 1080p copy, so uploads are quick on island internet."""
    src, out = folder / "video.mp4", folder / "share.mp4"
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    core.run([core.FFMPEG, "-y", "-v", "error", "-i", src,
              "-vf", "scale='min(1920,iw)':-2:flags=lanczos,format=yuv420p", "-r", "30",
              *(["-c:v", "h264_videotoolbox"] if core.sys.platform == "darwin" else ["-c:v", "libx264", "-preset", "veryfast"]),
              "-b:v", "4M", "-maxrate", "6M", "-bufsize", "8M",
              "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out])
    return out


def _vtt(folder: Path) -> bytes | None:
    srt = folder / "transcript.srt"
    if not srt.exists():
        return None
    text = srt.read_text().replace("\r", "")
    lines = ["WEBVTT", ""]
    for line in text.split("\n"):
        lines.append(line.replace(",", ".") if "-->" in line else line)
    return "\n".join(lines).encode()


def publish(folder: Path, progress=lambda pct: None) -> str:
    meta = core.read_meta(folder)
    vid = meta.get("share_id") or "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(14))
    video = _share_copy(folder)
    progress(5)
    size = video.stat().st_size
    up = _req("POST", f"/api/v/{vid}/mpu")["uploadId"]
    uid = urllib.request.quote(up, safe="")
    parts, n, sent = [], 1, 0
    with open(video, "rb") as f:
        while chunk := f.read(PART):
            r = _req("PUT", f"/api/v/{vid}/mpu/{uid}/{n}", chunk)
            parts.append({"partNumber": r.get("partNumber", n), "etag": r["etag"]})
            sent += len(chunk)
            progress(5 + int(85 * sent / size))
            n += 1
    _req("POST", f"/api/v/{vid}/mpu/{uid}/complete", json.dumps({"parts": parts}).encode(), "application/json")
    _req("PUT", f"/api/v/{vid}/file/thumb.jpg", (folder / "thumb.jpg").read_bytes(), "image/jpeg")
    vtt = _vtt(folder)
    if vtt:
        _req("PUT", f"/api/v/{vid}/file/captions.vtt", vtt, "text/vtt")
    remote = {"title": meta["title"], "duration": meta.get("duration", 0), "created": meta.get("created"),
              "transcript": core.parse_srt(folder / "transcript.srt")}
    _req("PUT", f"/api/v/{vid}/file/meta.json", json.dumps(remote).encode(), "application/json")
    progress(100)
    url = f"{config()['share_base']}/v/{vid}"
    core.write_meta(folder, share_id=vid, share_url=url, shared_at=(folder / "video.mp4").stat().st_mtime,
                    shared_title=meta["title"], shared_tx=(folder / "transcript.srt").exists())
    (folder / "share.mp4").unlink(missing_ok=True)
    return url


def update_meta(folder: Path):
    """Title or transcript changed but the video did not: refresh the small files only."""
    meta = core.read_meta(folder)
    vid = meta["share_id"]
    vtt = _vtt(folder)
    if vtt:
        _req("PUT", f"/api/v/{vid}/file/captions.vtt", vtt, "text/vtt")
    remote = {"title": meta["title"], "duration": meta.get("duration", 0), "created": meta.get("created"),
              "transcript": core.parse_srt(folder / "transcript.srt")}
    _req("PUT", f"/api/v/{vid}/file/meta.json", json.dumps(remote).encode(), "application/json")
    core.write_meta(folder, shared_title=meta["title"], shared_tx=(folder / "transcript.srt").exists())
    return meta["share_url"]


def unpublish(folder: Path):
    meta = core.read_meta(folder)
    if meta.get("share_id"):
        _req("DELETE", f"/api/v/{meta['share_id']}")
    core.write_meta(folder, share_id=None, share_url=None, shared_at=None)


def stats(folder: Path):
    meta = core.read_meta(folder)
    return _req("GET", f"/api/v/{meta['share_id']}/stats", timeout=15) if meta.get("share_id") else None


def state(folder: Path) -> str:
    """none | live | stale-video | stale-meta"""
    meta = core.read_meta(folder)
    if not meta.get("share_url"):
        return "none"
    if abs((meta.get("shared_at") or 0) - (folder / "video.mp4").stat().st_mtime) > 1:
        return "stale-video"
    if meta.get("shared_title") != meta["title"] or meta.get("shared_tx") != (folder / "transcript.srt").exists():
        return "stale-meta"
    return "live"


def open_in_browser(url):
    webbrowser.open(url)
