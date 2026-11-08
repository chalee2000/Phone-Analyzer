import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { ApiError, call, subscribe } from "./bridge";
import { useI18n } from "./i18n";
import type { AppInfo, AppState, Kind, Platform, ScannedDevice, StepEvent } from "./types";

export type Tab = "device" | "network" | "timeline" | "comms" | Kind;
export type Theme = "light" | "dark";

export interface StepState {
  status: "waiting" | "running" | "done" | "unavailable" | "error";
  progress: number;
  count?: number;
  reason?: string;
}

export interface Job {
  id: string;
  extractionId: string;
  kinds: Kind[];
  steps: Partial<Record<Kind, StepState>>;
  stage: { message: string; progress: number | null } | null;
  startedAt: number;
  finishedAt?: number;
  status?: "completed" | "cancelled" | "failed";
  message?: string;
}

export type DialogName = "diag" | "extract" | "cases" | "history" | "number" | "picker" | "audit" | "about" | "report";

export interface Dialogs {
  diag: { platform: Platform; notFound: boolean } | null;
  extract: boolean;
  cases: boolean;
  history: boolean;
  number: boolean;
  picker: ScannedDevice[] | null;
  audit: boolean;
  about: boolean;
  /** Report wizard; `formats` preselects outputs (e.g. the ribbon PDF button). */
  report: { formats?: string[] } | null;
}

const EMPTY_STATE: AppState = { device: null, case: null, extraction: null, counts: {}, running: false };
const NO_DIALOGS: Dialogs = { diag: null, extract: false, cases: false, history: false, number: false, picker: null, audit: false, about: false, report: null };

function readPref<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T) || fallback;
  } catch {
    return fallback;
  }
}
function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

function useStoreValue() {
  const { t } = useI18n();
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [state, setState] = useState<AppState>(EMPTY_STATE);
  const [platform, setPlatformState] = useState<Platform>(() => readPref<Platform>("spni.platform", "android"));
  const [theme, setThemeState] = useState<Theme>(() => readPref<Theme>("spni.theme", "light"));
  const [tab, setTab] = useState<Tab>("device");
  const [records, setRecords] = useState<Partial<Record<Kind, unknown[]>>>({});
  const [job, setJob] = useState<Job | null>(null);
  const [dialogs, setDialogs] = useState<Dialogs>(NO_DIALOGS);
  const [detected, setDetected] = useState<ScannedDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [statusText, setStatusText] = useState<string>("");
  const [loaded, setLoaded] = useState(false);
  const loading = useRef<Set<Kind>>(new Set());

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const setTheme = useCallback((th: Theme) => {
    setThemeState(th);
    writePref("spni.theme", th);
  }, []);
  const setPlatform = useCallback((p: Platform) => {
    setPlatformState(p);
    writePref("spni.platform", p);
  }, []);

  const errorText = useCallback(
    (e: unknown) => {
      if (e instanceof ApiError) {
        const key = `err.${e.code}`;
        const text = t(key);
        return text === key ? `${t("err.generic")}: ${e.message}` : text;
      }
      return `${t("err.generic")}: ${String(e)}`;
    },
    [t],
  );

  const refresh = useCallback(async () => {
    const s = await call<AppState>("state");
    setState(s);
    return s;
  }, []);

  const openDialog = useCallback(<K extends DialogName>(name: K, value?: Dialogs[K]) => {
    setDialogs((d) => ({ ...d, [name]: value ?? true }));
  }, []);
  const closeDialog = useCallback((name: DialogName) => {
    setDialogs((d) => ({ ...d, [name]: name === "diag" || name === "picker" || name === "report" ? null : false }));
  }, []);

  const resetRecords = useCallback(() => {
    loading.current.clear();
    setRecords({});
  }, []);

  const loadRecords = useCallback(async (kind: Kind, force = false) => {
    if (!force && loading.current.has(kind)) return;
    loading.current.add(kind);
    try {
      const rows = await call<unknown[]>("get_records", kind);
      setRecords((r) => ({ ...r, [kind]: rows }));
    } catch {
      loading.current.delete(kind);
    }
  }, []);

  const connect = useCallback(
    async (id: string) => {
      try {
        const dev = await call<AppState["device"]>("connect", id);
        resetRecords();
        setTab("device");
        await refresh();
        const name = dev?.info.market_name || dev?.info.model || id;
        toast.success(t("toast.connected", { device: name }));
        if (dev?.info.platform) setPlatform(dev.info.platform);
        return true;
      } catch (e) {
        toast.error(errorText(e));
        return false;
      }
    },
    [refresh, resetRecords, t, errorText, setPlatform],
  );

  const scan = useCallback(
    async (opts: { silent?: boolean } = {}) => {
      if (!opts.silent) setScanning(true);
      try {
        const res = await call<{ devices: ScannedDevice[] }>("scan_devices", platform);
        const devices = res.devices.filter((d) => d.platform === platform);
        setDetected(devices);
        if (opts.silent) return devices;
        const ready = devices.filter((d) => d.state === "ready");
        const real = ready.filter((d) => !d.demo);
        if (real.length === 1 || (real.length === 0 && ready.length === 1)) {
          await connect((real[0] ?? ready[0]).id);
        } else if (ready.length > 1) {
          openDialog("picker", ready);
        } else if (devices.length) {
          toast.warning(t("toast.notReady", { state: t(`state.${devices[0].state}`) }));
          openDialog("diag", { platform, notFound: false });
        } else {
          openDialog("diag", { platform, notFound: true });
        }
        return devices;
      } catch (e) {
        if (!opts.silent) toast.error(errorText(e));
        return [];
      } finally {
        if (!opts.silent) setScanning(false);
      }
    },
    [platform, connect, openDialog, t, errorText],
  );

  const disconnect = useCallback(async () => {
    await call("disconnect");
    resetRecords();
    setTab("device");
    await refresh();
    toast(t("toast.disconnected"));
  }, [refresh, resetRecords, t]);

  const closeExtraction = useCallback(async () => {
    await call("close_extraction");
    resetRecords();
    setTab("device");
    await refresh();
  }, [refresh, resetRecords]);

  const startExtraction = useCallback(
    async (options: Record<string, unknown>) => {
      try {
        const res = await call<{ job: string; extraction_id: string; kinds: Kind[] }>("start_extraction", options);
        const steps: Partial<Record<Kind, StepState>> = {};
        res.kinds.forEach((k) => (steps[k] = { status: "waiting", progress: 0 }));
        setJob({ id: res.job, extractionId: res.extraction_id, kinds: res.kinds, steps, stage: null, startedAt: Date.now() });
        resetRecords();
        await refresh();
      } catch (e) {
        toast.error(errorText(e));
      }
    },
    [refresh, resetRecords, errorText],
  );

  const cancelExtraction = useCallback(() => call("cancel_extraction"), []);

  const exportReport = useCallback(
    async (fmt: "excel" | "pdf" | "word", lang: string) => {
      if (!state.extraction) {
        toast.warning(t("export.nothing"));
        return;
      }
      const label = fmt === "excel" ? "Excel" : fmt === "pdf" ? "PDF" : "Word";
      const id = toast.loading(t("export.working", { fmt: label }));
      try {
        const res = await call<{ path: string; name: string }>("export_report", fmt, { lang });
        toast.success(t("export.done", { name: res.name }), {
          id,
          action: { label: t("export.open"), onClick: () => void call("reveal", res.path) },
          duration: 8000,
        });
      } catch (e) {
        toast.error(errorText(e), { id });
      }
    },
    [state.extraction, t, errorText],
  );

  const exportNetwork = useCallback(
    async (fmt: "anx" | "xlsx" | "graphml", options?: Record<string, unknown>, positions?: Record<string, unknown>) => {
      const id = toast.loading(t("export.working", { fmt: fmt === "anx" ? "i2" : fmt.toUpperCase() }));
      try {
        const res = await call<{ path: string; name: string }>("export_network", fmt, options ?? {}, positions ?? null);
        toast.success(t("export.done", { name: res.name }), {
          id,
          action: { label: t("export.open"), onClick: () => void call("reveal", res.path) },
          duration: 8000,
        });
      } catch (e) {
        toast.error(errorText(e), { id });
      }
    },
    [t, errorText],
  );

  // Backend events → state
  useEffect(() => {
    return subscribe((name, payload) => {
      if (name === "extraction.step") {
        const p = payload as StepEvent;
        setJob((j) => {
          if (!j || j.id !== p.job) return j;
          const prev = j.steps[p.kind] ?? { status: "waiting", progress: 0 };
          const next: StepState = {
            status: p.status === "running" ? "running" : p.status,
            progress: p.progress ?? prev.progress,
            count: p.count ?? prev.count,
            reason: p.reason ?? prev.reason,
          };
          return { ...j, steps: { ...j.steps, [p.kind]: next } };
        });
      } else if (name === "extraction.stage") {
        setJob((j) => (j && j.id === payload.job ? { ...j, stage: { message: payload.message, progress: payload.progress ?? null } } : j));
      } else if (name === "extraction.done") {
        setJob((j) =>
          j && j.id === payload.job ? { ...j, finishedAt: Date.now(), status: payload.status, message: payload.message, stage: null } : j,
        );
        resetRecords();
        void refresh();
      } else if (name === "case.opened") {
        void refresh();
      }
    });
  }, [refresh, resetRecords]);

  useEffect(() => {
    (async () => {
      try {
        setInfo(await call<AppInfo>("app_info"));
        await refresh();
      } catch (e) {
        toast.error(errorText(e));
      } finally {
        setLoaded(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const deviceName = state.device ? state.device.info.market_name || state.device.info.model : "";

  return {
    loaded,
    info,
    setInfo,
    state,
    refresh,
    platform,
    setPlatform,
    theme,
    setTheme,
    tab,
    setTab,
    records,
    loadRecords,
    resetRecords,
    job,
    setJob,
    dialogs,
    openDialog,
    closeDialog,
    detected,
    scanning,
    scan,
    connect,
    disconnect,
    closeExtraction,
    startExtraction,
    cancelExtraction,
    exportReport,
    exportNetwork,
    errorText,
    deviceName,
    statusText,
    setStatusText,
  };
}

export type Store = ReturnType<typeof useStoreValue>;
const StoreContext = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const value = useStoreValue();
  const memo = useMemo(() => value, [value]);
  return <StoreContext.Provider value={memo}>{children}</StoreContext.Provider>;
}

export function useStore(): Store {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("StoreProvider missing");
  return ctx;
}

export function useRecords<T>(kind: Kind): T[] | undefined {
  const { records, loadRecords, state } = useStore();
  useEffect(() => {
    if (state.extraction && !records[kind]) void loadRecords(kind);
  }, [kind, records, loadRecords, state.extraction]);
  return records[kind] as T[] | undefined;
}
