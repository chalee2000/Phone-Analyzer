"""Loopback HTTP server that streams case media (photos, audio) to the UI.

Bound to 127.0.0.1 on a random port; every URL carries a random token, and
only files inside the cases root can be served.
"""

from __future__ import annotations

import logging
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

log = logging.getLogger("spni.media")

# Explicit types: on Windows `mimetypes` reads the registry, which other software
# can change (".js" as text/plain stops the UI from loading at all).
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".map": "application/json",
    ".svg": "image/svg+xml", ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    ".bmp": "image/bmp", ".heic": "image/heic", ".heif": "image/heif", ".dng": "image/x-adobe-dng",
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".3gp": "video/3gpp", ".webm": "video/webm",
    ".m4a": "audio/mp4", ".aac": "audio/aac", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".opus": "audio/ogg", ".amr": "audio/amr", ".3ga": "audio/3gpp", ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8",
}


def content_type(path: Path) -> str:
    ext = path.suffix.lower()
    return CONTENT_TYPES.get(ext) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def resolve_media(root: Path, rel_url: str) -> Path | None:
    """Map ``<case>/<extraction>/<path>`` to a file under ``root`` (no traversal)."""
    rel = unquote(rel_url)
    try:
        candidate = (root / rel).resolve()
        candidate.relative_to(root.resolve())
    except (ValueError, OSError) as exc:
        log.warning("media refused %r under %s: %s", rel, root, exc)
        return None
    if not candidate.is_file():
        log.warning("media not found %s", candidate)
        return None
    return candidate


def send_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    size = path.stat().st_size
    ctype = content_type(path)
    start, end = 0, size - 1
    rng = handler.headers.get("Range")
    status = 200
    if rng and rng.startswith("bytes="):
        try:
            a, b = rng[6:].split("-", 1)
            start = int(a) if a else max(0, size - int(b))
            end = int(b) if a and b else size - 1
            status = 206
        except ValueError:
            start, end = 0, size - 1
    start, end = max(0, start), min(end, size - 1)
    length = max(0, end - start + 1)
    handler.send_response(status)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(length))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Cache-Control", "private, max-age=3600")
    handler.send_header("Access-Control-Allow-Origin", "*")
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.end_headers()
    with open(path, "rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            chunk = fh.read(min(1 << 16, remaining))
            if not chunk:
                break
            try:
                handler.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return
            remaining -= len(chunk)


class MediaServer:
    def __init__(self, root_getter) -> None:
        self.root_getter = root_getter  # callable → current cases root
        self.token = secrets.token_urlsafe(16)
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_GET(self):  # noqa: N802
                parts = urlparse(self.path).path.lstrip("/").split("/", 1)
                if len(parts) != 2 or parts[0] != server.token:
                    self.send_error(403)
                    return
                path = resolve_media(Path(server.root_getter()), parts[1])
                if not path:
                    self.send_error(404)
                    return
                send_file(self, path)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/{self.token}"

    def start(self) -> None:
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="media-server").start()

    def stop(self) -> None:
        self.httpd.shutdown()
