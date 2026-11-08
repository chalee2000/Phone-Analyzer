"""Tiny publish/subscribe bus used to push progress to the UI.

The desktop app subscribes a sink that forwards events into the webview with
``evaluate_js``; the development server subscribes one queue per browser tab
and streams them as Server-Sent Events.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable

Sink = Callable[[str, dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._sinks: list[Sink] = []
        self._lock = threading.Lock()

    def subscribe(self, sink: Sink) -> Callable[[], None]:
        with self._lock:
            self._sinks.append(sink)

        def unsubscribe() -> None:
            with self._lock:
                if sink in self._sinks:
                    self._sinks.remove(sink)

        return unsubscribe

    def emit(self, name: str, payload: dict[str, Any] | None = None) -> None:
        payload = payload or {}
        with self._lock:
            sinks = list(self._sinks)
        for sink in sinks:
            try:
                sink(name, payload)
            except Exception:  # a broken sink must never stop an extraction
                pass


def js_dispatch(name: str, payload: dict[str, Any]) -> str:
    """JavaScript that dispatches the event inside the page."""
    data = json.dumps({"name": name, "payload": payload}, ensure_ascii=False, default=str)
    return f"window.dispatchEvent(new CustomEvent('spni', {{ detail: {data} }}))"
