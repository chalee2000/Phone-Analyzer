"""One loopback HTTP server for the UI and the case media.

The desktop window loads the built UI from here and the UI loads photos, voice
clips and videos from ``/media/<token>/…`` on the *same origin*. Serving both
from one place avoids every cross-origin rule a WebView may apply to a second
local port (mixed content, ORB, private-network checks).

* ``GET /media/<token>/<case>/extractions/<id>/<path>``: a file under the cases root
* ``GET /*``: the built UI (``frontend/dist``), ``index.html`` for app routes

Binds to 127.0.0.1 only; media URLs carry a random token.
"""

from __future__ import annotations

import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .media_server import resolve_media, send_file

log = logging.getLogger("spni.app_server")


class StaticMediaMixin:
    """GET handling shared by the desktop app server and the development server."""

    dist: Path
    media_token: str
    root_getter: Callable[[], Path]

    def serve_static_or_media(self: BaseHTTPRequestHandler, path: str) -> None:  # type: ignore[misc]
        prefix = "/media/"
        if path.startswith(prefix):
            token, _, rel = path[len(prefix):].partition("/")
            if token != self.media_token:
                log.warning("media request with a wrong token: %s", path[:80])
                self.send_error(403)
                return
            target = resolve_media(Path(self.root_getter()), rel)
            if target is None:
                self.send_error(404)
                return
            try:
                send_file(self, target)
            except OSError as exc:
                log.warning("media send failed %s: %s", target, exc)
            return
        dist = self.dist
        target = dist / "index.html"
        if path not in ("", "/"):
            candidate = (dist / path.lstrip("/")).resolve()
            try:
                candidate.relative_to(dist.resolve())
                if candidate.is_file():
                    target = candidate
            except ValueError:
                pass
        if not target.is_file():
            body = b"UI not built: run npm run build in the frontend folder"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        send_file(self, target)


class AppServer:
    """The desktop window's server: static UI + same-origin media."""

    def __init__(self, dist: Path, root_getter: Callable[[], Path], port: int = 0) -> None:
        token = secrets.token_urlsafe(16)

        class Handler(StaticMediaMixin, BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # silence the per-request log
                pass

            def do_GET(self):  # noqa: N802
                self.serve_static_or_media(urlparse(self.path).path)

        Handler.dist = dist
        Handler.media_token = token
        Handler.root_getter = staticmethod(root_getter)
        self.token = token
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    @property
    def media_base(self) -> str:
        return f"http://127.0.0.1:{self.port}/media/{self.token}"

    def start(self) -> None:
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="app-server").start()

    def stop(self) -> None:
        self.httpd.shutdown()
