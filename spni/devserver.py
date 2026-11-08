"""Development server: the same Api over HTTP so the UI can run in a browser.

    python -m spni.devserver --demo          # then: cd frontend && npm run dev

* ``POST /rpc``  body ``{"method": "scan_devices", "args": [...]}``
* ``GET /events`` Server-Sent Events stream of the event bus
* ``GET /*``     the built UI from ``frontend/dist`` (if present)

Binds to 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .api import Api
from .events import EventBus
from .media_server import MediaServer, send_file
from .paths import frontend_dist


def make_server(api: Api, bus: EventBus, port: int) -> ThreadingHTTPServer:
    dist = frontend_dist()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _json(self, status: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/rpc":
                self._json(404, {"ok": False, "error": "not_found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                req = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(400, {"ok": False, "error": "bad_json"})
                return
            name = str(req.get("method", ""))
            fn = getattr(api, name, None) if not name.startswith("_") else None
            if fn is None or not getattr(fn, "_endpoint", False):
                self._json(404, {"ok": False, "error": "unknown_method", "message": name})
                return
            self._json(200, fn(*req.get("args", [])))

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            if path == "/events":
                self._events()
                return
            target = (dist / path.lstrip("/")).resolve() if path != "/" else dist / "index.html"
            try:
                target.relative_to(dist.resolve())
            except ValueError:
                target = dist / "index.html"
            if not target.is_file():
                target = dist / "index.html"
            if not target.is_file():
                self._json(404, {"ok": False, "error": "ui_not_built"})
                return
            send_file(self, target)

        def _events(self) -> None:
            q: queue.Queue = queue.Queue()
            unsubscribe = bus.subscribe(lambda n, p: q.put({"name": n, "payload": p}))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        item = q.get(timeout=15)
                        data = json.dumps(item, ensure_ascii=False, default=str)
                        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                unsubscribe()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Phone Analysis development server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SPNI_DEVSERVER_PORT", 8765)))
    parser.add_argument("--demo", action="store_true", help="show the demo devices")
    parser.add_argument("--cases", type=Path, default=None, help="cases folder")
    args = parser.parse_args()
    bus = EventBus()
    api = Api(bus, args.cases, demo=args.demo or os.environ.get("SPNI_DEMO") == "1")
    media = MediaServer(lambda: api._cases_root)
    media.start()
    api._set_media_base(media.base_url)
    server = make_server(api, bus, args.port)
    print(f"Phone Analysis devserver on http://127.0.0.1:{args.port}  (cases: {api._cases_root})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

