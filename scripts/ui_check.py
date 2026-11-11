"""End-to-end check of the packaged Windows app in its real WebView2 window (CI).

    python scripts/ui_check.py "dist/Phone Analysis/Phone Analysis.exe" ui-check

Starts the .exe in demo mode with WebView2's remote debugging port and talks
to the app's page target over the DevTools protocol (a plain websocket; tools
such as Playwright do not list WebView2 pages). Runs a demo Android extraction
through the app's own API, opens the Photos tab and checks that the pictures
really render. Writes a screenshot, the result and the app log to the output
folder; exits non-zero when pictures do not load.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PORT = 9333


def targets() -> list[dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
            return json.loads(r.read())
    except (OSError, ValueError):
        return []


class Page:
    """Minimal DevTools client for one page target."""

    def __init__(self, ws_url: str) -> None:
        import websocket  # websocket-client

        self.ws = websocket.create_connection(ws_url, timeout=180, suppress_origin=True)
        self.seq = 0

    def call(self, method: str, **params) -> dict:
        self.seq += 1
        self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.seq:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval(self, expr: str):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS error: {r['exceptionDetails'].get('text')} {r['exceptionDetails'].get('exception', {}).get('description', '')}")
        return r.get("result", {}).get("value")

    def wait(self, expr: str, timeout: float) -> None:
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.eval(expr):
                    return
            except RuntimeError:
                pass
            time.sleep(1)
        raise TimeoutError(f"timed out waiting for {expr}")


READY = "!!(window.pywebview && window.pywebview.api && window.pywebview.api.connect)"


def main() -> int:
    exe, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    cases = Path(tempfile.mkdtemp(prefix="pa-cases-"))
    env = dict(os.environ, SPNI_REMOTE_DEBUGGING_PORT=str(PORT), SPNI_DEMO_SPEED="0")
    proc = subprocess.Popen([str(exe), "--demo", "--cases", str(cases)], env=env)
    result: dict = {"ok": False}
    try:
        target = None
        for _ in range(150):
            found = [t for t in targets() if t.get("type") == "page" and str(t.get("url", "")).startswith("http://127.0.0.1")]
            if found:
                target = found[0]
                break
            time.sleep(1)
        result["targets"] = [{"type": t.get("type"), "url": t.get("url"), "title": t.get("title")} for t in targets()]
        if target is None:
            raise RuntimeError("the app window never loaded its page")
        page = Page(target["webSocketDebuggerUrl"])
        page.call("Runtime.enable")
        page.wait(READY, 90)
        brief = "(r => ({ok: r && r.ok, error: r && r.error, message: r && r.message}))"
        result["connect"] = page.eval(f"window.pywebview.api.connect('demo:android').then({brief})")
        result["start"] = page.eval(f"window.pywebview.api.start_extraction({{kinds: ['photos', 'contacts']}}).then({brief})")
        state = None
        for _ in range(240):
            state = page.eval("window.pywebview.api.state()")
            if not (state or {}).get("data", {}).get("running"):
                break
            time.sleep(1)
        data = (state or {}).get("data") or {}
        result["state"] = {
            "running": data.get("running"),
            "counts": data.get("counts"),
            "extraction": (data.get("extraction") or {}).get("status"),
            "unavailable": (data.get("extraction") or {}).get("unavailable"),
        }
        page.call("Page.reload")
        time.sleep(3)
        page.wait(READY, 90)
        time.sleep(2)
        page.wait("!!document.querySelector('[data-testid=tab-photos]')", 30)
        page.eval("document.querySelector('[data-testid=tab-photos]').click()")
        # Wait for the grid's pictures (or for the tab to settle on an empty / unavailable page).
        for _ in range(45):
            if page.eval("document.querySelectorAll('[data-testid=photo-grid] img, [data-testid=photo-broken]').length"):
                break
            time.sleep(1)
        # Bring every lazy picture into view so each one is actually requested.
        page.eval("""(async () => {
            const g = document.querySelector('[data-testid=photo-grid]');
            if (!g) return;
            for (let y = 0; y <= g.scrollHeight; y += 400) { g.scrollTop = y; await new Promise(r => setTimeout(r, 150)); }
            g.scrollTop = 0;
        })()""")
        time.sleep(3)
        grid = page.eval("""(() => {
            const imgs = [...document.querySelectorAll('[data-testid=photo-grid] img')];
            const main = document.querySelector('main') || document.body;
            return {total: imgs.length, loaded: imgs.filter(i => i.complete && i.naturalWidth > 0).length,
                    broken: document.querySelectorAll('[data-testid=photo-broken]').length, src: imgs[0] ? imgs[0].src : '',
                    tiles: document.querySelectorAll('[data-testid=photo-grid] button').length,
                    tab: (document.querySelector('[role=tab][aria-selected=true]') || {}).textContent || '',
                    text: (main.innerText || '').slice(0, 300)};
        })()""")
        if grid["src"]:
            grid["fetch"] = page.eval(
                "(async () => { try { const r = await fetch(%s); return [r.status, r.headers.get('content-type')]; }"
                " catch (e) { return ['error', String(e)]; } })()" % json.dumps(grid["src"]))
        grid["page_url"] = target["url"]
        grid["media_base"] = page.eval("(async () => (await window.pywebview.api.app_info()).data.media_base)()")
        shot = page.call("Page.captureScreenshot", format="png")
        (out / "photos.png").write_bytes(base64.b64decode(shot["data"]))
        result.update(grid)
        result["ok"] = grid["total"] > 0 and grid["broken"] == 0 and grid["loaded"] > 0
    except Exception as exc:  # report, then fail the step
        result["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        log = Path(os.environ.get("APPDATA", Path.home())) / "Phone Analysis" / "logs" / "app.log"
        if log.is_file():
            shutil.copy2(log, out / "app.log")
            result["app_log_tail"] = log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
        result["exit_code"] = proc.poll()
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
