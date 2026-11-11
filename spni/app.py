"""Desktop entry point: a frameless pywebview window hosting the React UI."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import APP_NAME, __version__, logs
from .api import Api
from .app_server import AppServer
from .events import EventBus, js_dispatch
from .paths import frontend_dist


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} v{__version__}")
    parser.add_argument("--demo", action="store_true", help="show demo devices (training / testing)")
    parser.add_argument("--dev", action="store_true", help="load the UI from the Vite dev server")
    parser.add_argument("--debug", action="store_true", help="enable the web inspector")
    parser.add_argument("--cases", type=Path, default=None, help="cases folder")
    args = parser.parse_args()

    import webview

    logs.setup()
    bus = EventBus()
    api = Api(bus, args.cases, demo=args.demo or os.environ.get("SPNI_DEMO") == "1")
    # The UI and the case media come from one local server (same origin), so
    # the WebView never has to load images from a second port.
    server = AppServer(frontend_dist(), lambda: api._cases_root)
    server.start()
    api._set_media_base(server.media_base)

    if args.dev:
        url = os.environ.get("SPNI_UI_URL", "http://localhost:5173")
    else:
        if not (frontend_dist() / "index.html").is_file():
            sys.exit("UI not built: run `npm run build` in the frontend folder first.")
        url = server.url

    window = webview.create_window(
        f"{APP_NAME} v{__version__}",
        url=url,
        js_api=api,
        width=1500,
        height=940,
        min_size=(1280, 760),
        frameless=True,
        easy_drag=False,
        background_color="#0B1530",
        text_select=True,
    )
    api._attach_window(window)

    def forward(name: str, payload: dict) -> None:
        try:
            window.evaluate_js(js_dispatch(name, payload))
        except Exception:
            pass

    bus.subscribe(forward)
    storage = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME / "webview"
    # Test hook for CI (scripts/ui_check.py): drive the real WebView2 window over CDP.
    if os.environ.get("SPNI_REMOTE_DEBUGGING_PORT"):
        webview.settings["REMOTE_DEBUGGING_PORT"] = int(os.environ["SPNI_REMOTE_DEBUGGING_PORT"])
    webview.start(debug=args.debug, private_mode=False, storage_path=str(storage))
    server.stop()


if __name__ == "__main__":
    main()
