from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .storage import load_run, save_run


def _json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _serve_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    if not path.is_file():
        _json_response(handler, {"error": "file not found"}, 404)
        return
    total_size = path.stat().st_size
    start = 0
    end = total_size - 1
    range_header = handler.headers.get("Range")
    if range_header and range_header.startswith("bytes="):
        requested = range_header.removeprefix("bytes=").split("-", 1)
        start = int(requested[0] or 0)
        if len(requested) > 1 and requested[1]:
            end = int(requested[1])
        end = min(end, total_size - 1)
        if start > end:
            handler.send_error(416)
            return
        handler.send_response(206)
        handler.send_header("Content-Range", f"bytes {start}-{end}/{total_size}")
    else:
        handler.send_response(200)
    handler.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(end - start + 1))
    handler.end_headers()
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)


def _html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Video Highlight Review</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f4f5f7; color: #1e293b; }
    header { position: sticky; top: 0; z-index: 1; padding: 16px 20px; background: #111827; color: white; }
    header h1 { margin: 0 0 6px; font-size: 19px; }
    header p { margin: 0; opacity: .8; font-size: 13px; }
    main { max-width: 1080px; margin: 0 auto; padding: 20px; }
    .toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; }
    .toolbar button, .card button { border: 0; border-radius: 5px; padding: 8px 12px; cursor: pointer; font-weight: 600; }
    .toolbar button { background: #2563eb; color: white; }
    .toolbar button.secondary { background: #e2e8f0; color: #334155; }
    .card { background: white; border: 1px solid #dbe1ea; border-radius: 7px; padding: 14px; margin-bottom: 14px; box-shadow: 0 1px 2px #0f172a0d; }
    .card.accepted { border-color: #22c55e; }
    .card.rejected { opacity: .55; }
    .meta { display: flex; gap: 12px; flex-wrap: wrap; font-size: 13px; color: #64748b; margin-bottom: 10px; }
    .card video { display: block; width: min(100%, 720px); max-height: 420px; background: #0f172a; border-radius: 5px; }
    .fields { display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0; }
    .fields label { display: flex; gap: 5px; align-items: center; font-size: 13px; }
    .fields input { width: 92px; padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px; }
    .reason { color: #475569; font-size: 13px; margin: 8px 0; }
    .actions { display: flex; gap: 8px; }
    .accept { background: #16a34a; color: white; }
    .reject { background: #dc2626; color: white; }
    .save { background: #475569; color: white; }
    #status { color: #475569; font-size: 13px; }
  </style>
</head>
<body>
  <header><h1>Video Highlight Review</h1><p id="summary">Loading run...</p></header>
  <main>
    <div class="toolbar">
      <button id="accept-all">Accept all visible</button>
      <button class="secondary" id="reload">Reload</button>
      <span id="status"></span>
    </div>
    <section id="candidates"></section>
  </main>
  <script>
    let run;
    const byId = (id) => document.getElementById(id);
    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function sampleFor(candidate) {
      const window = (run.windows || []).find((item) => (candidate.source_window_ids || []).includes(item.window_id));
      return window && window.sample_ids && window.sample_ids[0];
    }
    function render() {
      const candidates = run.candidates || [];
      byId('summary').textContent = `${run.prompt || 'No Prompt'} · ${candidates.length} candidates · ${run.provider || 'not analyzed'}`;
      byId('candidates').innerHTML = candidates.map((candidate, index) => {
        const asset = run.assets.find((item) => item.asset_id === candidate.asset_id);
        const sample = sampleFor(candidate);
        return `<article class="card ${esc(candidate.status)}" data-id="${esc(candidate.candidate_id)}">
          <div class="meta"><strong>#${index + 1}</strong><span>${esc(asset ? asset.path.split('/').pop() : candidate.asset_id)}</span><span>${esc(candidate.score)}</span><span>${esc((candidate.tags || []).join(', '))}</span></div>
          <video controls preload="metadata" src="/media?asset=${encodeURIComponent(candidate.asset_id)}" data-start="${candidate.start}"></video>
          ${sample ? `<img alt="sample" hidden src="/frame?sample=${encodeURIComponent(sample)}">` : ''}
          <div class="fields">
            <label>Start <input class="start" type="number" step="0.001" value="${candidate.start}"></label>
            <label>End <input class="end" type="number" step="0.001" value="${candidate.end}"></label>
          </div>
          <p class="reason">${esc(candidate.reason)}</p>
          <div class="actions"><button class="accept">Accept</button><button class="reject">Reject</button><button class="save">Save time</button></div>
        </article>`;
      }).join('') || '<p>No candidates yet. Run analyze first.</p>';
      document.querySelectorAll('video[data-start]').forEach((video) => video.addEventListener('loadedmetadata', () => video.currentTime = Number(video.dataset.start)));
      document.querySelectorAll('.card').forEach(bindCard);
    }
    async function update(card, patch) {
      const response = await fetch('/api/candidate', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({candidate_id: card.dataset.id, ...patch}) });
      if (!response.ok) throw new Error(await response.text());
      run = await (await fetch('/api/run')).json();
      render();
      byId('status').textContent = 'Saved';
    }
    function bindCard(card) {
      card.querySelector('.accept').onclick = () => update(card, {status: 'accepted'}).catch(showError);
      card.querySelector('.reject').onclick = () => update(card, {status: 'rejected'}).catch(showError);
      card.querySelector('.save').onclick = () => update(card, {start: Number(card.querySelector('.start').value), end: Number(card.querySelector('.end').value)}).catch(showError);
    }
    function showError(error) { byId('status').textContent = error.message; }
    async function load() { run = await (await fetch('/api/run')).json(); render(); }
    byId('reload').onclick = load;
    byId('accept-all').onclick = async () => { for (const card of [...document.querySelectorAll('.card')]) await update(card, {status: 'accepted'}); };
    load().catch(showError);
  </script>
</body>
</html>"""


class ReviewHandler(BaseHTTPRequestHandler):
    run_dir: Path

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        run = load_run(self.run_dir)
        if parsed.path == "/api/run":
            _json_response(self, run)
            return
        if parsed.path == "/media":
            asset_id = query.get("asset", [""])[0]
            asset = next((item for item in run["assets"] if item["asset_id"] == asset_id), None)
            if not asset:
                _json_response(self, {"error": "unknown asset"}, 404)
                return
            _serve_file(self, Path(asset["path"]))
            return
        if parsed.path == "/frame":
            sample_id = query.get("sample", [""])[0]
            sample = next((item for item in run["samples"] if item["sample_id"] == sample_id), None)
            if not sample:
                _json_response(self, {"error": "unknown sample"}, 404)
                return
            _serve_file(self, Path(sample["path"]))
            return
        if parsed.path in {"/", "/index.html"}:
            body = _html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/candidate":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size).decode("utf-8"))
        run = load_run(self.run_dir)
        candidate = next(
            (item for item in run["candidates"] if item["candidate_id"] == payload.get("candidate_id")),
            None,
        )
        if candidate is None:
            _json_response(self, {"error": "unknown candidate"}, 404)
            return
        if "status" in payload:
            if payload["status"] not in {"pending", "accepted", "rejected"}:
                _json_response(self, {"error": "invalid status"}, 400)
                return
            candidate["status"] = payload["status"]
        if "start" in payload or "end" in payload:
            start = float(payload.get("start", candidate["start"]))
            end = float(payload.get("end", candidate["end"]))
            asset = next(item for item in run["assets"] if item["asset_id"] == candidate["asset_id"])
            if not 0 <= start < end <= asset["duration"]:
                _json_response(self, {"error": "invalid time range"}, 400)
                return
            candidate["start"] = round(start, 3)
            candidate["end"] = round(end, 3)
        save_run(self.run_dir, run)
        _json_response(self, {"ok": True, "candidate": candidate})

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def serve_review(run_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    handler = type("BoundReviewHandler", (ReviewHandler,), {"run_dir": run_dir.resolve()})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Review UI: http://{host}:{server.server_port}/")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
