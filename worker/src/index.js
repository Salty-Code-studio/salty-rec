// Salty Rec share links: private R2 storage, one unguessable link per video.
const ID = /^[A-Za-z0-9_-]{10,40}$/;
const FILES = new Set(["video.mp4", "thumb.jpg", "captions.vtt", "meta.json"]);
const BOTS = /bot|whatsapp|facebookexternalhit|slack|telegram|twitter|linkedin|discord|preview|crawler|spider/i;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const p = url.pathname.split("/").filter(Boolean);
    try {
      if (p[0] === "api") {
        if (!authorized(request, env)) return json({ error: "unauthorized" }, 401);
        return await api(request, env, p.slice(1));
      }
      if (p[0] === "v" && ID.test(p[1] || "")) return await viewer(request, env, p[1], url);
      if (p[0] === "f" && ID.test(p[1] || "") && FILES.has(p[2])) return await serve(request, env, `${p[1]}/${p[2]}`);
      if (p.length === 0) return new Response("Salty Rec", { headers: { "content-type": "text/plain" } });
      return new Response("Not found", { status: 404 });
    } catch (e) {
      return json({ error: String(e && e.message || e) }, 500);
    }
  },
};

function authorized(request, env) {
  const got = request.headers.get("authorization") || "";
  const want = `Bearer ${env.UPLOAD_TOKEN || ""}`;
  if (!env.UPLOAD_TOKEN || got.length !== want.length) return false;
  let diff = 0;
  for (let i = 0; i < got.length; i++) diff |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return diff === 0;
}

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });

async function api(request, env, p) {
  // /api/v/:id/...
  if (p[0] !== "v" || !ID.test(p[1] || "")) return json({ error: "bad path" }, 400);
  const id = p[1], m = request.method, key = `${id}/video.mp4`;
  if (m === "POST" && p[2] === "mpu" && !p[3]) {
    const up = await env.VIDEOS.createMultipartUpload(key, { httpMetadata: { contentType: "video/mp4" } });
    return json({ uploadId: up.uploadId });
  }
  if (m === "PUT" && p[2] === "mpu" && p[3] && p[4]) {
    const up = env.VIDEOS.resumeMultipartUpload(key, decodeURIComponent(p[3]));
    const part = await up.uploadPart(parseInt(p[4], 10), await request.arrayBuffer());
    return json(part);
  }
  if (m === "POST" && p[2] === "mpu" && p[3] && p[4] === "complete") {
    const up = env.VIDEOS.resumeMultipartUpload(key, decodeURIComponent(p[3]));
    const { parts } = await request.json();
    await up.complete(parts);
    return json({ ok: true });
  }
  if (m === "PUT" && p[2] === "file" && FILES.has(p[3]) && p[3] !== "video.mp4") {
    const types = { "thumb.jpg": "image/jpeg", "captions.vtt": "text/vtt", "meta.json": "application/json" };
    await env.VIDEOS.put(`${id}/${p[3]}`, await request.arrayBuffer(), { httpMetadata: { contentType: types[p[3]] } });
    return json({ ok: true });
  }
  if (m === "GET" && p[2] === "stats") {
    const v = await env.VIDEOS.get(`${id}/views.json`);
    return json(v ? await v.json() : { views: 0, last: null });
  }
  if (m === "DELETE" && !p[2]) {
    const list = await env.VIDEOS.list({ prefix: `${id}/` });
    if (list.objects.length) await env.VIDEOS.delete(list.objects.map((o) => o.key));
    return json({ ok: true, deleted: list.objects.length });
  }
  return json({ error: "unknown route" }, 404);
}

async function serve(request, env, key) {
  const range = request.headers.get("range");
  const obj = await env.VIDEOS.get(key, range ? { range: request.headers } : undefined);
  if (!obj) return new Response("Not found", { status: 404 });
  const h = new Headers();
  obj.writeHttpMetadata(h);
  h.set("etag", obj.httpEtag);
  h.set("accept-ranges", "bytes");
  h.set("cache-control", key.endsWith("meta.json") ? "no-store" : "public, max-age=3600");
  h.set("x-robots-tag", "noindex");
  if (key.endsWith("video.mp4") && new URL(request.url).searchParams.has("download")) {
    h.set("content-disposition", 'attachment; filename="video.mp4"');
  }
  if (range && obj.range) {
    let { offset, length, suffix } = obj.range;
    if (suffix !== undefined) { offset = obj.size - suffix; length = suffix; }
    if (offset === undefined) offset = 0;
    if (length === undefined) length = obj.size - offset;
    h.set("content-range", `bytes ${offset}-${offset + length - 1}/${obj.size}`);
    h.set("content-length", String(length));
    return new Response(obj.body, { status: 206, headers: h });
  }
  h.set("content-length", String(obj.size));
  return new Response(obj.body, { headers: h });
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clock = (t) => { t = Math.floor(t); const m = Math.floor(t / 60), s = t % 60; return `${m}:${String(s).padStart(2, "0")}`; };

async function viewer(request, env, id, url) {
  const metaObj = await env.VIDEOS.get(`${id}/meta.json`);
  const video = await env.VIDEOS.head(`${id}/video.mp4`);
  if (!metaObj || !video) {
    return new Response(page("Video not found", `<main class="gone"><p class="mark">~&lt;</p><h1>This video is gone.</h1><p>The link was turned off or never existed.</p></main>`, ""), {
      status: 404, headers: { "content-type": "text/html; charset=utf-8", "x-robots-tag": "noindex" } });
  }
  const meta = await metaObj.json();
  const ua = request.headers.get("user-agent") || "";
  if (!BOTS.test(ua)) {
    const v = await env.VIDEOS.get(`${id}/views.json`);
    const stats = v ? await v.json() : { views: 0 };
    stats.views = (stats.views || 0) + 1;
    stats.last = new Date().toISOString();
    await env.VIDEOS.put(`${id}/views.json`, JSON.stringify(stats), { httpMetadata: { contentType: "application/json" } });
  }
  const base = `${url.origin}/f/${id}`;
  const hasCaps = !!(await env.VIDEOS.head(`${id}/captions.vtt`));
  const lines = (meta.transcript || []).map(([t, text]) =>
    `<button class="line" data-t="${t}"><span>${clock(t)}</span>${esc(text)}</button>`).join("");
  const when = meta.created ? new Date(meta.created) : null;
  const date = when && !isNaN(when) ? when.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }) : "";
  const head = `
    <meta property="og:type" content="video.other">
    <meta property="og:title" content="${esc(meta.title)}">
    <meta property="og:description" content="${esc(clock(meta.duration || 0))} video from Salty Code">
    <meta property="og:image" content="${base}/thumb.jpg">
    <meta property="og:video" content="${base}/video.mp4">
    <meta property="og:video:type" content="video/mp4">
    <meta name="twitter:card" content="summary_large_image">`;
  const body = `
    <header><a class="brand" href="https://saltycodestudio.com"><b>~&lt;</b>saltycodestudio</a></header>
    <main>
      <div class="stage">
        <video id="v" controls playsinline preload="metadata" poster="${base}/thumb.jpg">
          <source src="${base}/video.mp4" type="video/mp4">
          ${hasCaps ? `<track kind="captions" src="${base}/captions.vtt" label="Captions" default>` : ""}
        </video>
      </div>
      <div class="info">
        <div>
          <h1>${esc(meta.title)}</h1>
          <p class="meta">${esc(clock(meta.duration || 0))}${date ? ` · ${esc(date)}` : ""}</p>
        </div>
        <div class="actions">
          <div class="speed" role="group" aria-label="Playback speed">
            ${[1, 1.25, 1.5, 2].map((r) => `<button data-r="${r}"${r === 1 ? ' aria-pressed="true"' : ""}>${r}x</button>`).join("")}
          </div>
          <a class="dl" href="${base}/video.mp4?download">Download</a>
        </div>
      </div>
      ${lines ? `<section class="tx"><p class="label">Transcript</p><div class="lines">${lines}</div></section>` : ""}
    </main>
    <footer>Recorded with Salty Rec by <a href="https://saltycodestudio.com">Salty Code Studio</a></footer>
    <script>
      const v = document.getElementById('v');
      document.querySelectorAll('.line').forEach(b => b.onclick = () => { v.currentTime = +b.dataset.t; v.play(); });
      document.querySelectorAll('.speed button').forEach(b => b.onclick = () => {
        v.playbackRate = +b.dataset.r;
        document.querySelectorAll('.speed button').forEach(x => x.setAttribute('aria-pressed', x === b));
      });
      const lines = [...document.querySelectorAll('.line')];
      v.addEventListener('timeupdate', () => {
        let cur = null;
        for (const l of lines) if (+l.dataset.t <= v.currentTime) cur = l;
        lines.forEach(l => l.classList.toggle('on', l === cur));
      });
    </script>`;
  return new Response(page(meta.title, body, head), {
    headers: { "content-type": "text/html; charset=utf-8", "x-robots-tag": "noindex", "cache-control": "no-store" } });
}

function page(title, body, head) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>${esc(title)}</title>${head}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=Inter:wght@400;500&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
:root{--sand:#F2EBDD;--teal:#0E3A40;--coral:#FF6F59;--sky:#4FA8C9;--ink:#1C2B2E;--line:rgba(14,58,64,.14);--muted:rgba(28,43,46,.62);--card:#FBF7EF}
*{box-sizing:border-box}
html,body{overflow-x:hidden}
body{margin:0;background:var(--sand);color:var(--ink);font:15px/1.55 Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
header,main,footer{max-width:1080px;margin:0 auto;padding:0 16px}
header{padding-top:22px;padding-bottom:18px}
.brand{font:600 18px 'Space Grotesk',sans-serif;color:var(--teal);text-decoration:none}
.brand b{color:var(--coral);margin-right:6px}
.stage{background:var(--ink);border-radius:16px;overflow:hidden;box-shadow:0 1px 2px rgba(14,58,64,.06),0 18px 48px rgba(14,58,64,.14)}
video{display:block;width:100%;max-height:78vh;background:var(--ink)}
.info{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;padding:20px 0 8px}
h1{font:600 clamp(22px,3vw,30px)/1.15 'Space Grotesk',sans-serif;color:var(--teal);margin:0 0 4px;letter-spacing:-.015em}
.meta{margin:0;color:var(--muted);font:500 12px 'JetBrains Mono',monospace;letter-spacing:.04em}
.actions{display:flex;gap:10px;align-items:center}
.speed{display:flex;gap:3px;background:rgba(14,58,64,.07);padding:3px;border-radius:10px}
.speed button{border:0;background:transparent;padding:7px 10px;border-radius:7px;font:500 12px 'JetBrains Mono',monospace;color:var(--muted);cursor:pointer;min-height:34px}
.speed button[aria-pressed=true]{background:#fff;color:var(--teal)}
.dl{background:var(--teal);color:var(--sand);text-decoration:none;padding:9px 18px;border-radius:999px;font:600 14px 'Space Grotesk',sans-serif;min-height:40px;display:inline-flex;align-items:center}
.tx{margin:18px 0 0;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
.label{margin:0 0 10px;font:500 11px 'JetBrains Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.lines{max-height:320px;overflow:auto}
.line{min-width:0;overflow-wrap:anywhere;display:flex;gap:14px;width:100%;text-align:left;border:0;background:transparent;padding:7px 8px;border-radius:8px;font:inherit;color:inherit;cursor:pointer}
.line span{font:500 12px 'JetBrains Mono',monospace;color:var(--sky);padding-top:2px;min-width:40px}
.line:hover{background:rgba(14,58,64,.05)}
.line.on{background:#fff}
footer{padding-top:32px;padding-bottom:40px;color:var(--muted);font-size:13px}
footer a{color:var(--teal)}
.gone{text-align:center;padding-top:18vh}.gone .mark{font:600 40px 'Space Grotesk';color:var(--coral);margin:0}
.gone h1{margin:8px 0}
</style></head><body>${body}</body></html>`;
}
