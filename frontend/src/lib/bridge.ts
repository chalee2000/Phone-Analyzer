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

type Mode = "pywebview" | "http";
let mode: Promise<Mode> | null = null;

const hasApi = () => typeof window.pywebview?.api?.state === "function";

/** Does this page's server answer JSON-RPC? Only the development server does. */
async function rpcAvailable(): Promise<boolean> {
  try {
    const r = await fetch("/rpc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method: "app_info", args: [] }),
    });
    return r.ok && ((await r.json()) as Resp<unknown>)?.ok === true;
  } catch {
    return false;
  }
}

/**
 * pywebview injects its API after the page has loaded, sometimes seconds later
 * (slow machines, a reload). The desktop app's page server has no /rpc, so only
 * switch to HTTP when the server really answers it; otherwise keep waiting.
 */
function detect(): Promise<Mode> {
  if (!mode) {
    mode = new Promise<Mode>((resolve) => {
      let done = false;
      let poll = 0;
      const finish = (how: Mode) => {
        if (done) return;
        done = true;
        window.clearInterval(poll);
        document.documentElement.dataset.bridge = how;
        resolve(how);
      };
      if (hasApi()) return finish("pywebview");
      window.addEventListener("pywebviewready", () => finish("pywebview"), { once: true });
      poll = window.setInterval(() => hasApi() && finish("pywebview"), 200);
      window.setTimeout(() => {
        if (!done) void rpcAvailable().then((yes) => yes && finish("http"));
      }, 900);
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
