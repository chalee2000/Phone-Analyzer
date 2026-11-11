import clsx from "clsx";
import {
  AlertTriangle,
  CalendarRange,
  CircleCheckBig,
  FileArchive,
  FolderOpen,
  Image as ImageIcon,
  Info,
  Lock,
  MessageCircle,
  MessagesSquare,
  Sparkles,
  Upload,
  UserRound,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Badge, Button, Modal, ProgressBar, Spinner } from "../components/ui";
import { fileToBase64 } from "../lib/analysis";
import { call, subscribe } from "../lib/bridge";
import { fmtDate, fmtSize } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";

interface Preview {
  owner: string;
  candidates: { name: string; threads: number; messages: number }[];
  threads: number;
  e2ee_threads: number;
  requests: number;
  messages: number;
  media: number;
  first: number | null;
  last: number | null;
  sources: { name: string; size: number | null; path: string }[];
  warnings: string[];
  skipped?: string[];
}

interface Result {
  extraction_id: string;
  case_id: string;
  owner: string;
  threads: number;
  counts: { chats?: number; photos?: number };
  missing_media: number;
}

/** Messenger's blue-to-violet mark, drawn with a lucide icon. */
export function MessengerMark({ className = "size-11", icon = "size-5" }: { className?: string; icon?: string }) {
  return (
    <span className={clsx("grid shrink-0 place-items-center rounded-2xl text-white shadow-[0_8px_20px_-8px_rgba(124,58,237,0.7)]", className)} style={{ background: "linear-gradient(135deg,#00b2ff 0%,#6a5cff 55%,#c13cff 100%)" }}>
      <MessageCircle className={icon} strokeWidth={2.4} />
    </span>
  );
}

function Stat({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-3">
      <div className="flex items-center gap-1.5 text-[12px] font-semibold text-muted [&>svg]:size-3.5">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-display text-[20px] leading-tight font-semibold text-ink">{value}</div>
    </div>
  );
}

/** LINE's green mark for the LINE-export source. */
function LineMark({ className = "size-11", icon = "size-5" }: { className?: string; icon?: string }) {
  return (
    <span className={clsx("grid shrink-0 place-items-center rounded-2xl bg-[#06c755] text-white shadow-[0_8px_20px_-8px_rgba(6,199,85,0.7)]", className)}>
      <MessageCircle className={icon} strokeWidth={2.4} />
    </span>
  );
}

type Source = "messenger" | "line";

export function MessengerImportDialog() {
  const { t } = useI18n();
  const { dialogs, closeDialog, errorText, refresh, resetRecords, setTab } = useStore();
  const open = dialogs.messenger;
  const [phase, setPhase] = useState<"pick" | "preview" | "working" | "done">("pick");
  const [paths, setPaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [pv, setPv] = useState<Preview | null>(null);
  const [owner, setOwner] = useState("");
  const [progress, setProgress] = useState({ step: "read", progress: 0 });
  const [result, setResult] = useState<Result | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [source, setSource] = useState<Source>("messenger");
  const line = source === "line";
  const rpc = (name: string) => `${source}_${name}`;

  useEffect(() => {
    if (!open) return;
    setSource(open === "line" ? "line" : "messenger");
    setPhase("pick");
    setPaths([]);
    setPv(null);
    setResult(null);
  }, [open]);

  const close = () => phase !== "working" && closeDialog("messenger");

  const load = async (list: string[]) => {
    if (!list.length) return;
    setLoading(true);
    try {
      const p = await call<Preview>(rpc("preview"), list);
      setPaths(list);
      setPv(p);
      setOwner(p.owner);
      setPhase("preview");
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setLoading(false);
    }
  };

  const pick = async () => {
    if (!window.pywebview?.api) {
      fileRef.current?.click(); // browser / dev server
      return;
    }
    try {
      const list = await call<string[] | null>("choose_files", source);
      if (list?.length) await load(list);
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setLoading(true);
    try {
      const list: string[] = [];
      for (const f of Array.from(files)) list.push(await call<string>("messenger_upload", f.name, await fileToBase64(f)));
      await load(list);
    } catch (e) {
      toast.error(errorText(e));
      setLoading(false);
    }
  };

  const demo = async () => {
    setLoading(true);
    try {
      await load(await call<string[]>(rpc("demo_files")));
    } catch (e) {
      toast.error(errorText(e));
      setLoading(false);
    }
  };

  const run = async () => {
    setPhase("working");
    setProgress({ step: "read", progress: 0.02 });
    const unsub = subscribe((name, payload) => {
      if (name === "import.progress") setProgress(payload as { step: string; progress: number });
    });
    try {
      const res = await call<Result>(rpc("import"), paths, owner);
      setResult(res);
      setPhase("done");
      await refresh();
      toast.success(t(line ? "ln.done" : "ms.done"));
    } catch (e) {
      toast.error(errorText(e));
      setPhase("preview");
    } finally {
      unsub();
    }
  };

  const show = async (tab: "chats" | "photos") => {
    if (!result) return;
    try {
      await call("open_extraction", result.case_id, result.extraction_id);
      resetRecords();
      setTab(tab);
      await refresh();
      closeDialog("messenger");
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  return (
    <Modal open={!!open} onClose={close} width={860} dismissable={phase !== "working"}>
      <div className="relative flex items-start gap-4 border-b border-line px-6 pt-5 pb-4">
        {line ? <LineMark /> : <MessengerMark />}
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-[21px] leading-tight font-semibold text-ink">{t(line ? "ln.title" : "ms.title")}</h2>
          <p className="mt-1 text-[13.5px] text-muted">{t(line ? "ln.sub" : "ms.sub")}</p>
        </div>
        {phase !== "working" && (
          <button onClick={close} className="focus-ring -mt-1 -mr-2 grid size-9 place-items-center rounded-xl text-muted hover:bg-surface-3 hover:text-ink" aria-label="close">
            <X className="size-5" />
          </button>
        )}
        <span className="absolute bottom-[-1px] left-6 h-[3px] w-14 rounded-full bg-gold-400" />
      </div>

      <div className="max-h-[calc(100vh-220px)] min-h-[360px] overflow-auto px-6 py-5">
        {phase === "pick" && (
          <div className="flex flex-col gap-4" data-testid="ms-pick">
            <div className="inline-flex w-fit gap-1 rounded-xl bg-surface-3 p-1">
              {(["messenger", "line"] as const).map((src) => (
                <button
                  key={src}
                  type="button"
                  data-testid={`import-source-${src}`}
                  onClick={() => setSource(src)}
                  className={clsx(
                    "focus-ring flex h-9 items-center gap-2 rounded-lg px-3.5 text-[13.5px] font-semibold transition",
                    source === src ? "bg-surface text-ink shadow-sm ring-1 ring-line" : "text-muted hover:text-ink",
                  )}
                >
                  {src === "line" ? <LineMark className="size-5 rounded-md shadow-none" icon="size-3" /> : <MessengerMark className="size-5 rounded-md shadow-none" icon="size-3" />}
                  {src === "line" ? "LINE (.txt)" : "Messenger"}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => void pick()}
              disabled={loading}
              data-testid="ms-choose"
              className="focus-ring group flex flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-line-strong bg-surface-2 px-6 py-8 text-center transition hover:border-navy-400 hover:bg-navy-50/40 dark:hover:border-gold-400 dark:hover:bg-gold-400/5"
            >
              <span className="grid size-14 place-items-center rounded-2xl bg-surface text-navy-600 shadow-sm ring-1 ring-line transition group-hover:scale-105 dark:text-gold-300">
                {loading ? <Spinner className="size-6" /> : <FileArchive className="size-7" />}
              </span>
              <span className="font-display text-[17px] font-semibold text-ink">{t("ms.choose")}</span>
              <span className="text-[13px] text-muted">{t(line ? "ln.chooseHint" : "ms.chooseHint")}</span>
            </button>
            <input ref={fileRef} type="file" accept={line ? ".txt,.zip" : ".zip,.json"} multiple hidden onChange={(e) => void upload(e.target.files)} />
            {line ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  {(["Android", "Ios"] as const).map((os) => (
                    <div key={os} className="rounded-2xl border border-line bg-surface p-4">
                      <div className="mb-1.5 flex items-center gap-2 text-[13.5px] font-bold text-ink">
                        <MessagesSquare className="size-4 text-[#06c755]" />
                        {t(`ln.how${os}`)}
                      </div>
                      <p className="text-[12.5px] leading-relaxed text-muted">{t(`ln.how${os}Body`)}</p>
                    </div>
                  ))}
                </div>
                <div className="flex items-start gap-3 rounded-2xl border border-sky-200 bg-sky-50/70 px-4 py-3 text-[12.5px] text-sky-800 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-200">
                  <ImageIcon className="mt-0.5 size-4 shrink-0" />
                  {t("ln.note")}
                </div>
              </>
            ) : (
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-2xl border border-line bg-surface p-4">
                <div className="mb-1.5 flex items-center gap-2 text-[13.5px] font-bold text-ink">
                  <MessagesSquare className="size-4 text-sky-500" />
                  {t("ms.howDyi")}
                </div>
                <p className="text-[12.5px] leading-relaxed text-muted">{t("ms.howDyiBody")}</p>
              </div>
              <div className="rounded-2xl border border-line bg-surface p-4">
                <div className="mb-1.5 flex items-center gap-2 text-[13.5px] font-bold text-ink">
                  <Lock className="size-4 text-violet-500" />
                  {t("ms.howE2ee")}
                </div>
                <p className="text-[12.5px] leading-relaxed text-muted">{t("ms.howE2eeBody")}</p>
              </div>
            </div>
            )}
            <div className="flex items-start gap-3 rounded-2xl border border-gold-200 bg-gold-50/70 px-4 py-3 text-[12.5px] text-gold-800 dark:border-gold-500/30 dark:bg-gold-500/10 dark:text-gold-200">
              <Info className="mt-0.5 size-4 shrink-0" />
              {t(line ? "ln.legal" : "ms.legal")}
            </div>
          </div>
        )}

        {phase === "preview" && pv && (
          <div className="flex flex-col gap-4" data-testid="ms-preview">
            <div className="grid grid-cols-4 gap-2.5">
              <Stat icon={<MessagesSquare />} label={t("ms.threads")} value={pv.threads.toLocaleString()} />
              <Stat icon={<MessageCircle />} label={t("ms.messages")} value={pv.messages.toLocaleString()} />
              <Stat icon={<ImageIcon />} label={t("ms.media")} value={pv.media.toLocaleString()} />
              <Stat icon={<CalendarRange />} label={t("ms.range")} value={<span className="text-[14px]">{pv.first ? `${fmtDate(pv.first)} – ${fmtDate(pv.last)}` : "—"}</span>} />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {pv.e2ee_threads > 0 && (
                <Badge tone="violet">
                  <Lock className="size-3" /> {t("ms.e2ee", { n: pv.e2ee_threads })}
                </Badge>
              )}
              {pv.requests > 0 && <Badge tone="amber">{t("ms.requests", { n: pv.requests })}</Badge>}
              {!!pv.skipped?.length && (
                <Badge tone="amber">
                  <AlertTriangle className="size-3" /> {t("ln.skipped", { n: pv.skipped.length })}
                </Badge>
              )}
              {pv.warnings.includes("no_owner") && (
                <Badge tone="amber">
                  <AlertTriangle className="size-3" /> {t("ln.noOwner")}
                </Badge>
              )}
              {pv.warnings.includes("html_skipped") && (
                <Badge tone="red">
                  <AlertTriangle className="size-3" /> {t("ms.htmlSkipped")}
                </Badge>
              )}
            </div>
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="h-3.5 w-1 rounded-full bg-gold-400" />
                <h4 className="text-[13.5px] font-bold text-ink">{t("ms.owner")}</h4>
                <span className="text-[12px] text-muted">{t("ms.ownerHint")}</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {pv.candidates.slice(0, 6).map((c) => {
                  const on = c.name === owner;
                  return (
                    <button
                      key={c.name}
                      type="button"
                      onClick={() => setOwner(c.name)}
                      data-testid="ms-owner"
                      className={clsx(
                        "focus-ring flex items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition",
                        on ? "border-navy-600 bg-navy-50/60 dark:border-gold-400 dark:bg-gold-400/10" : "border-line hover:bg-surface-2",
                      )}
                    >
                      <span className={clsx("grid size-5 shrink-0 place-items-center rounded-full border-2", on ? "border-navy-700 dark:border-gold-400" : "border-line-strong")}>
                        {on && <span className="size-2.5 rounded-full bg-navy-700 dark:bg-gold-400" />}
                      </span>
                      <UserRound className="size-4 text-muted" />
                      <span className="min-w-0 flex-1 truncate text-[13.5px] font-semibold text-ink">{c.name}</span>
                      <span className="tabular shrink-0 text-[11.5px] text-muted">{t("ms.ownerStat", { t: c.threads, m: c.messages.toLocaleString() })}</span>
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="h-3.5 w-1 rounded-full bg-gold-400" />
                <h4 className="text-[13.5px] font-bold text-ink">{t("ms.sources")}</h4>
              </div>
              <div className="flex flex-col gap-1.5">
                {pv.sources.map((s) => (
                  <div key={s.path} className="flex items-center gap-3 rounded-xl bg-surface-2 px-3 py-2 text-[13px]">
                    {s.size == null ? <FolderOpen className="size-4 text-gold-500" /> : <FileArchive className="size-4 text-gold-500" />}
                    <span className="min-w-0 flex-1 truncate font-medium text-ink" title={s.path}>
                      {s.name}
                    </span>
                    {s.size != null && <span className="tabular text-[12px] text-muted">{fmtSize(s.size)}</span>}
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[12px] text-muted">{t("ms.hashNote")}</p>
            </div>
          </div>
        )}

        {phase === "working" && (
          <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-4 text-center" data-testid="ms-working">
            <MessengerMark className="size-16 animate-pulse" icon="size-8" />
            <div className="font-display text-[20px] font-semibold text-ink">{t("ms.working")}</div>
            <div className="text-[13.5px] text-muted">{t(`ms.p.${progress.step}`)}</div>
            <ProgressBar value={progress.progress} tone="gold" className="h-2 w-full max-w-md" />
          </div>
        )}

        {phase === "done" && result && (
          <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 text-center" data-testid="ms-done">
            <span className="grid size-16 place-items-center rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-white shadow-lg">
              <CircleCheckBig className="size-8" />
            </span>
            <div className="font-display text-[22px] font-semibold text-ink">{t(line ? "ln.done" : "ms.done")}</div>
            <div className="text-[14px] text-muted">{t("ms.doneSub", { owner: result.owner, threads: result.threads, chats: (result.counts.chats ?? 0).toLocaleString(), photos: (result.counts.photos ?? 0).toLocaleString() })}</div>
            {result.missing_media > 0 && (
              <div className="flex items-center gap-2 rounded-xl bg-amber-50 px-3 py-2 text-[12.5px] text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">
                <AlertTriangle className="size-4" /> {t("ms.missing", { n: result.missing_media })}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-line bg-surface-2 px-6 py-3.5">
        {phase === "pick" && (
          <>
            <Button variant="ghost" icon={<Sparkles className="size-4 text-gold-500" />} onClick={() => void demo()} disabled={loading} data-testid="ms-demo">
              {t("ms.demo")}
            </Button>
            <div className="flex-1" />
            <Button variant="ghost" onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button variant="primary" icon={<Upload className="size-4" />} onClick={() => void pick()} loading={loading}>
              {t("ms.choose")}
            </Button>
          </>
        )}
        {phase === "preview" && (
          <>
            <Button variant="ghost" onClick={() => setPhase("pick")}>
              {t("rw.prev")}
            </Button>
            <div className="flex-1" />
            <Button variant="gold" icon={<MessageCircle className="size-4" />} onClick={() => void run()} disabled={!owner} data-testid="ms-import">
              {t("ms.import", { n: pv?.messages.toLocaleString() ?? "" })}
            </Button>
          </>
        )}
        {phase === "working" && <div className="flex-1 text-center text-[12.5px] text-muted">{t("ms.wait")}</div>}
        {phase === "done" && (
          <>
            <div className="flex-1" />
            <Button variant="ghost" onClick={close}>
              {t("rw.close")}
            </Button>
            {!line && (
              <Button variant="outline" icon={<ImageIcon className="size-4" />} onClick={() => void show("photos")}>
                {t("ms.viewPhotos")}
              </Button>
            )}
            <Button variant="primary" icon={<MessagesSquare className="size-4" />} onClick={() => void show("chats")} data-testid="ms-view">
              {t("ms.viewChats")}
            </Button>
          </>
        )}
      </div>
    </Modal>
  );
}
