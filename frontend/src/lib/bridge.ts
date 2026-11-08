/**
 * Talks to the Python backend.
 *
 * Desktop app: pywebview injects `window.pywebview.api` and pushes events as
 * `spni` CustomEvents. Browser (development / tests): JSON-RPC over `/rpc`
 * and Server-Sent Events from `/events` (see spni/devserver.py).
 */

type Resp<T> = { ok: true; data: T } | { ok: false; error: string; message: string };

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message || code);
    this.code = code;
  }
}

declare global {
  interface Window {
    pywebview?: { api: Record<string, (...args: unknown[]) => Promise<unknown>> };
  }
}

let mode: Promise<"pywebview" | "http"> | null = null;

function detect(): Promise<"pywebview" | "http"> {
  if (!mode) {
    mode = new Promise((resolve) => {
      if (window.pywebview?.api) return resolve("pywebview");
      const timer = window.setTimeout(() => resolve("http"), 900);
      window.addEventListener(
        "pywebviewready",
        () => {
          window.clearTimeout(timer);
          resolve("pywebview");
        },
        { once: true },
      );
    });
  }
  return mode;
}

export async function call<T = unknown>(method: string, ...args: unknown[]): Promise<T> {
  const how = await detect();
  let res: Resp<T>;
  if (how === "pywebview") {
    res = (await window.pywebview!.api[method](...args)) as Resp<T>;
  } else {
    const r = await fetch("/rpc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method, args }),
    });
    res = (await r.json()) as Resp<T>;
  }
  if (!res || !res.ok) {
    const err = res as { error?: string; message?: string };
    throw new ApiError(err?.error ?? "internal", err?.message ?? "");
  }
  return res.data;
}

export type EventHandler = (name: string, payload: any) => void; // eslint-disable-line @typescript-eslint/no-explicit-any

export function subscribe(handler: EventHandler): () => void {
  const onCustom = (e: Event) => {
    const detail = (e as CustomEvent).detail as { name: string; payload: unknown };
    handler(detail.name, detail.payload);
  };
  window.addEventListener("spni", onCustom);
  let source: EventSource | null = null;
  let closed = false;
  detect().then((how) => {
    if (how !== "http" || closed) return;
    source = new EventSource("/events");
    source.onmessage = (msg) => {
      try {
        const { name, payload } = JSON.parse(msg.data);
        handler(name, payload);
      } catch {
        /* ignore malformed */
      }
    };
  });
  return () => {
    closed = true;
    window.removeEventListener("spni", onCustom);
    source?.close();
  };
}

export async function isDesktop(): Promise<boolean> {
  return (await detect()) === "pywebview";
}
