"""The desktop window's server: built UI and case media on one origin."""

import io
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

import pytest
from PIL import Image

from spni.app_server import AppServer
from spni.media_server import content_type


def get(url: str) -> tuple[int, str, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), b""


@pytest.fixture
def server(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>ui</title>", encoding="utf-8")
    (dist / "assets" / "app-123.js").write_text("export const x = 1;", encoding="utf-8")
    root = tmp_path / "Phone Analysis Cases"
    thumb = root / "20261111_งานด่วน_ab12" / "extractions" / "20261111-133400_9b01" / "thumbs" / "รูป 1.jpg"
    thumb.parent.mkdir(parents=True)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, "JPEG")
    thumb.write_bytes(buf.getvalue())
    (tmp_path / "secret.txt").write_text("outside the cases root", encoding="utf-8")
    srv = AppServer(dist, lambda: root)
    srv.start()
    yield srv, thumb, buf.getvalue()
    srv.stop()


def test_content_types_do_not_depend_on_the_registry():
    assert content_type(Path("a.JPG")) == "image/jpeg"
    assert content_type(Path("app.js")).startswith("text/javascript")
    assert content_type(Path("x.heic")) == "image/heic"
    assert content_type(Path("v.mp4")) == "video/mp4"
    assert content_type(Path("a.m4a")) == "audio/mp4"
    assert content_type(Path("blob")) == "application/octet-stream"


def test_ui_and_media_from_one_origin(server):
    srv, thumb, data = server
    status, ctype, body = get(srv.url)
    assert status == 200 and ctype.startswith("text/html") and b"<title>ui</title>" in body
    status, ctype, _ = get(srv.url + "assets/app-123.js")
    assert status == 200 and ctype.startswith("text/javascript")
    assert get(srv.url + "network")[2].startswith(b"<!doctype html>")  # app routes get index.html
    assert srv.media_base.startswith(srv.url.rstrip("/"))  # same origin
    rel = "/".join(quote(p) for p in ("20261111_งานด่วน_ab12", "extractions", "20261111-133400_9b01", "thumbs", "รูป 1.jpg"))
    status, ctype, body = get(f"{srv.media_base}/{rel}")
    assert status == 200 and ctype == "image/jpeg" and body == data


def test_media_is_confined_to_the_cases_root(server):
    srv, _, _ = server
    assert get(f"{srv.media_base}/..%2Fsecret.txt")[0] == 404
    assert get(f"{srv.media_base}/missing.jpg")[0] == 404
    assert get(f"{srv.url}media/wrong-token/x.jpg")[0] == 403
