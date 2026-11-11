"""End-to-end check of the packaged Windows app in its real WebView2 window (CI).

    python scripts/ui_check.py "dist/Phone Analysis/Phone Analysis.exe" ui-check

Starts the .exe in demo mode with WebView2's remote debugging port, connects
Playwright over CDP (no browser download needed), runs a demo Android
extraction through the app's own API, opens the Photos tab and checks that the
pictures really render. Writes a screenshot, the result and the app log to the
output folder; exits non-zero when pictures do not load.
"""

from __future__ import annotations

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


def wait_for_cdp(timeout: float) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2):
                return
        except OSError:
            time.sleep(1)
    raise TimeoutError("WebView2 did not open its debugging port")


def main() -> int:
    exe, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    cases = Path(tempfile.mkdtemp(prefix="pa-cases-"))
    env = dict(os.environ, SPNI_REMOTE_DEBUGGING_PORT=str(PORT), SPNI_DEMO_SPEED="0")
    proc = subprocess.Popen([str(exe), "--demo", "--cases", str(cases)], env=env)
    result: dict = {"ok": False}
    try:
        wait_for_cdp(120)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
            page = None
            for _ in range(60):
                pages = [pg for ctx in browser.contexts for pg in ctx.pages if pg.url.startswith("http://127.0.0.1")]
                if pages:
                    page = pages[0]
                    break
                time.sleep(1)
            if page is None:
                raise RuntimeError("the app window never loaded its page")
            errors: list[str] = []
            page.on("console", lambda m: m.type == "error" and errors.append(m.text))
            page.on("pageerror", lambda e: errors.append(str(e)))
            ready = "() => !!(window.pywebview && window.pywebview.api && window.pywebview.api.connect)"
            page.wait_for_function(ready, timeout=90_000)
            page.evaluate("async () => { await window.pywebview.api.connect('demo:android');"
                          " return await window.pywebview.api.start_extraction({kinds: ['photos', 'contacts']}); }")
            for _ in range(240):
                if not page.evaluate("async () => (await window.pywebview.api.state()).data.running"):
                    break
                time.sleep(1)
            page.reload()
            page.wait_for_function(ready, timeout=90_000)
            page.wait_for_timeout(2500)
            page.click("[data-testid=tab-photos]")
            page.wait_for_timeout(5000)
            grid = page.evaluate("""() => {
                const imgs = [...document.querySelectorAll('[data-testid=photo-grid] img')];
                return {total: imgs.length, loaded: imgs.filter(i => i.complete && i.naturalWidth > 0).length,
                        broken: document.querySelectorAll('[data-testid=photo-broken]').length, src: imgs[0] ? imgs[0].src : ''};
            }""")
            if grid["src"]:
                grid["fetch"] = page.evaluate(
                    "async (u) => { try { const r = await fetch(u); return [r.status, r.headers.get('content-type')]; }"
                    " catch (e) { return ['error', String(e)]; } }", grid["src"])
            grid["page_url"] = page.url
            grid["media_base"] = page.evaluate("async () => (await window.pywebview.api.app_info()).data.media_base")
            page.screenshot(path=str(out / "photos.png"))
            result = {"ok": grid["total"] > 0 and grid["broken"] == 0 and grid["loaded"] > 0, **grid, "errors": errors}
    except Exception as exc:  # report, then fail the step
        result["exception"] = f"{type(exc).__name__}: {exc}"
    finally:
        log = Path(os.environ.get("APPDATA", Path.home())) / "Phone Analysis" / "logs" / "app.log"
        if log.is_file():
            shutil.copy2(log, out / "app.log")
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        proc.wait(timeout=30)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
