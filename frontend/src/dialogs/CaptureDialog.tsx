import clsx from "clsx";
import { AlertTriangle, Check, CircleCheckBig, Hand, Image as ImageIcon, Layers, ListChecks, MessagesSquare, Plane, Play, ScanLine, Smartphone, Square, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Badge, Button, Field, Input, Modal, ProgressBar, Spinner } from "../components/ui";
import { mediaUrlFor } from "../lib/analysis";
import { call, subscribe } from "../lib/bridge";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { LineMark, MessengerMark } from "./MessengerImportDialog";

interface Progress {
  mode?: "all" | "current";
  chat?: number;
  chats_done?: number;
  page: number;
  max: number;
  title: string;
  app: string;
  messages: number;
  preview: string;
  case_id: string;
  extraction_id: string;
}
interface Done {
  case_id: string;
  extraction_id: string;
  pages?: number;
  messages?: number;
  pictures?: number;
  title?: string;
  app?: string;
  reached_top?: boolean;
  stopped?: boolean;
  text_pages?: number;
  error?: string;
  detail?: string;
  mode?: "all" | "current";
  interrupted?: string;
  chats?: ChatSummary[];
}
interface ChatSummary {
  title: string;
  app: string;
  pages: number;
  messages: number;
  pictures: number;
  reached_top: boolean;
  skipped?: string;
}
interface ChatApp {
  key: "line" | "messenger";
  package: string;
  name: string;
  installed: boolean | null;
}
type Mode = "all" | "current";

const PAGE_LIMITS = [50, 100, 200, 500];
const CHAT_LIMITS = [10, 30, 100, 500];
const PAGES_PER_CHAT = [20, 60, 200];

function Segmented<T extends number>({ values, value, onChange, label }: { values: T[]; value: T; onChange: (v: T) => void; label?: (v: T) => string }) {
  return (
    <div className="flex gap-1 rounded-xl bg-surface-3 p-1">
      {values.map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          className={clsx("h-8 flex-1 rounded-lg text-[13px] font-semibold transition", value === n ? "bg-surface text-ink shadow-sm ring-1 ring-line" : "text-muted hover:text-ink")}
        >
          {label ? label(n) : n}
        </button>
      ))}
    </div>
  );
}

function Stat({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-3.5">
      <div className="flex items-center gap-1.5 text-[12px] font-semibold text-muted [&>svg]:size-3.5">
        {icon} {label}
      </div>
      <div className="mt-1 font-display text-[24px] leading-tight font-semibold text-ink">{children}</div>
    </div>
  );
}

function Step({ n, icon, children }: { n: number; icon: ReactNode; children: ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-navy-50 text-navy-700 dark:bg-navy-800 dark:text-gold-300 [&>svg]:size-4">{icon}</span>
      <span className="pt-1 text-[13.5px] leading-relaxed text-ink-2">
        <b className="mr-1 text-ink">{n}.</b>
        {children}
      </span>
    </li>
  );
}

/** Phone-shaped frame for the latest screenshot. */
function PhoneFrame({ src, busy }: { src?: string; busy?: boolean }) {
  return (
    <div className="relative mx-auto aspect-[9/19.5] w-[230px] rounded-[34px] border-[7px] border-navy-900 bg-navy-950 shadow-[0_24px_50px_-24px_rgba(11,27,61,0.8)]">
      <div className="absolute inset-0 overflow-hidden rounded-[27px]">
        {src ? (
          <img src={src} alt="" className="size-full object-cover object-top" />
        ) : (
          <div className="grid size-full place-items-center text-white/40">
            <Smartphone className="size-10" />
          </div>
        )}
      </div>
      {busy && (
        <div className="absolute inset-x-0 bottom-3 flex justify-center">
          <span className="flex items-center gap-1.5 rounded-full bg-black/55 px-2.5 py-1 text-[11px] text-white">
            <Spinner className="size-3" /> REC
          </span>
        </div>
      )}
    </div>
  );
}

export function CaptureDialog() {
  const { t } = useI18n();
  const { dialogs, closeDialog, info, errorText, refresh, resetRecords, setTab, state } = useStore();
  const open = dialogs.capture;
  const [phase, setPhase] = useState<"intro" | "running" | "done">("intro");
  const [mode, setMode] = useState<Mode>("all");
  const [apps, setApps] = useState<ChatApp[]>([]);
  const [app, setApp] = useState<ChatApp["key"]>("line");
  const [maxChats, setMaxChats] = useState(30);
  const [perChat, setPerChat] = useState(60);
  const [maxPages, setMaxPages] = useState(200);
  const [title, setTitle] = useState("");
  const [prog, setProg] = useState<Progress | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPhase("intro");
    setProg(null);
    setDone(null);
    setStopping(false);
    void call<ChatApp[]>("capture_apps")
      .then((list) => {
        setApps(list);
        setApp((cur) => (list.find((a) => a.key === cur)?.installed === false ? (list.find((a) => a.installed)?.key ?? cur) : cur));
      })
      .catch(() => setApps([]));
  }, [open]);

  const errText = (code?: string) => {
    if (!code) return "";
    const key = `err.${code}`;
    const text = t(key);
    return text === key ? code : text;
  };

  useEffect(() => {
    if (!open) return;
    return subscribe((name, payload) => {
      if (name === "capture.progress") setProg(payload as Progress);
      if (name === "capture.done") {
        const d = payload as Done;
        setDone(d);
        setPhase("done");
        setStopping(false);
        if (d.error) toast.error(errText(d.error));
        void refresh();
      }
    });
  }, [open, refresh]);

  const start = async () => {
    try {
      setProg(null);
      setDone(null);
      await call(
        "capture_start",
        mode === "all" ? { mode, app, max_chats: maxChats, max_pages: perChat } : { mode, max_pages: maxPages, title: title.trim() },
      );
      setPhase("running");
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  const stop = async () => {
    setStopping(true);
    await call("capture_stop").catch(() => undefined);
  };

  const view = async () => {
    if (!done) return;
    try {
      await call("open_extraction", done.case_id, done.extraction_id);
      resetRecords();
      setTab("chats");
      await refresh();
      closeDialog("capture");
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  const preview = prog?.preview ? mediaUrlFor(info?.media_base, prog.case_id, prog.extraction_id, prog.preview) : undefined;
  const device = state.device?.info.market_name || state.device?.info.model || "Android";
  const close = () => phase !== "running" && closeDialog("capture");
  const appInfo = apps.find((a) => a.key === app);
  const appName = appInfo?.name ?? (app === "line" ? "LINE" : "Messenger");
  const all = mode === "all";
  const runAll = (prog?.mode ?? done?.mode ?? mode) === "all";
  const captured = (done?.chats ?? []).filter((c) => !c.skipped);

  return (
    <Modal open={open} onClose={close} width={880} dismissable={phase !== "running"}>
      <div className="relative flex items-start gap-4 border-b border-line px-6 pt-5 pb-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-navy-600 to-navy-900 text-white">
          <ScanLine className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-[21px] leading-tight font-semibold text-ink">{t("cp.title")}</h2>
          <p className="mt-1 text-[13.5px] text-muted">{t("cp.sub", { device })}</p>
        </div>
        {phase !== "running" && (
          <button onClick={close} className="focus-ring -mt-1 -mr-2 grid size-9 place-items-center rounded-xl text-muted hover:bg-surface-3 hover:text-ink" aria-label="close">
            <X className="size-5" />
          </button>
        )}
        <span className="absolute bottom-[-1px] left-6 h-[3px] w-14 rounded-full bg-gold-400" />
      </div>

      <div className="grid min-h-[460px] grid-cols-[290px_1fr] gap-6 px-6 py-5">
        <div className="flex flex-col items-center justify-center rounded-3xl bg-surface-2 py-5">
          <PhoneFrame src={preview} busy={phase === "running"} />
          {prog && <div className="mt-3 max-w-[230px] truncate text-center text-[12.5px] font-semibold text-ink-2">{[prog.app, prog.title].filter(Boolean).join(" · ")}</div>}
        </div>

        {phase === "intro" && (
          <div className="flex flex-col gap-4" data-testid="cp-intro">
            <div className="grid grid-cols-2 gap-2">
              {(["all", "current"] as Mode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  data-testid={`cp-mode-${m}`}
                  className={clsx(
                    "focus-ring flex items-start gap-2.5 rounded-2xl border px-3.5 py-3 text-left transition",
                    mode === m ? "border-gold-400 bg-gold-50/70 ring-1 ring-gold-300 dark:bg-gold-500/10" : "border-line bg-surface hover:border-line-strong",
                  )}
                >
                  <span className={clsx("mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl [&>svg]:size-4", mode === m ? "bg-gold-400 text-navy-950" : "bg-surface-3 text-muted")}>
                    {m === "all" ? <ListChecks /> : <MessagesSquare />}
                  </span>
                  <span>
                    <span className="block text-[14px] font-semibold text-ink">{t(m === "all" ? "cp.modeAll" : "cp.modeOne")}</span>
                    <span className="block text-[12px] leading-snug text-muted">{t(m === "all" ? "cp.modeAllSub" : "cp.modeOneSub")}</span>
                  </span>
                </button>
              ))}
            </div>

            {all ? (
              <>
                <div className="grid grid-cols-2 gap-2">
                  {(["line", "messenger"] as const).map((key) => {
                    const a = apps.find((x) => x.key === key);
                    const missing = a?.installed === false;
                    return (
                      <button
                        key={key}
                        type="button"
                        disabled={missing}
                        onClick={() => setApp(key)}
                        data-testid={`cp-app-${key}`}
                        className={clsx(
                          "focus-ring flex items-center gap-3 rounded-2xl border px-3.5 py-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-50",
                          app === key && !missing ? "border-navy-400 bg-navy-50/60 ring-1 ring-navy-300 dark:bg-navy-800/40" : "border-line bg-surface hover:border-line-strong",
                        )}
                      >
                        {key === "line" ? <LineMark className="size-9" icon="size-4" /> : <MessengerMark className="size-9" icon="size-4" />}
                        <span className="min-w-0 flex-1">
                          <span className="block text-[14px] font-semibold text-ink">{a?.name ?? (key === "line" ? "LINE" : "Messenger")}</span>
                          <span className={clsx("block text-[12px]", missing ? "text-rose-600" : "text-muted")}>
                            {a?.installed == null ? "\u00a0" : t(a.installed ? "cp.installed" : "cp.missing")}
                          </span>
                        </span>
                        {app === key && !missing && <Check className="size-4 text-navy-600 dark:text-gold-300" />}
                      </button>
                    );
                  })}
                </div>
                <ol className="flex flex-col gap-2.5">
                  <Step n={1} icon={<Plane />}>{t("cp.allStep1")}</Step>
                  <Step n={2} icon={<Smartphone />}>{t("cp.allStep2")}</Step>
                  <Step n={3} icon={<Hand />}>{t("cp.allStep3", { app: appName })}</Step>
                </ol>
                <div className="grid grid-cols-2 gap-4">
                  <Field label={t("cp.maxChats")}>
                    <Segmented values={CHAT_LIMITS} value={maxChats} onChange={setMaxChats} label={(n) => (n === 500 ? t("cp.allChats") : String(n))} />
                  </Field>
                  <Field label={t("cp.pagesPerChat")}>
                    <Segmented values={PAGES_PER_CHAT} value={perChat} onChange={setPerChat} />
                  </Field>
                </div>
                <div className="flex items-start gap-3 rounded-2xl border border-gold-200 bg-gold-50/70 px-4 py-3 text-[12.5px] leading-relaxed text-gold-800 dark:border-gold-500/30 dark:bg-gold-500/10 dark:text-gold-200">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  {t("cp.readWarn")}
                </div>
              </>
            ) : (
              <>
                <ol className="flex flex-col gap-2.5">
                  <Step n={1} icon={<Smartphone />}>{t("cp.step1")}</Step>
                  <Step n={2} icon={<MessagesSquare />}>{t("cp.step2")}</Step>
                  <Step n={3} icon={<Hand />}>{t("cp.step3")}</Step>
                </ol>
                <div className="grid grid-cols-2 gap-4">
                  <Field label={t("cp.thread")} hint={t("cp.threadHint")}>
                    <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("cp.threadPlaceholder")} />
                  </Field>
                  <Field label={t("cp.maxPages")}>
                    <Segmented values={PAGE_LIMITS} value={maxPages} onChange={setMaxPages} />
                  </Field>
                </div>
                <div className="flex items-start gap-3 rounded-2xl border border-gold-200 bg-gold-50/70 px-4 py-3 text-[12.5px] text-gold-800 dark:border-gold-500/30 dark:bg-gold-500/10 dark:text-gold-200">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  {t("cp.note")}
                </div>
              </>
            )}
          </div>
        )}

        {phase === "running" && (
          <div className="flex flex-col justify-center gap-5" data-testid="cp-running">
            <div>
              <div className="font-display text-[22px] font-semibold text-ink">{t(runAll ? "cp.runningAll" : "cp.running")}</div>
              <div className="mt-1 text-[13.5px] text-muted">{t(runAll ? "cp.runningAllSub" : "cp.runningSub")}</div>
            </div>
            {runAll && (
              <div className="flex items-center gap-2.5 rounded-2xl bg-surface-2 px-4 py-3">
                {app === "line" ? <LineMark className="size-8" icon="size-4" /> : <MessengerMark className="size-8" icon="size-4" />}
                <div className="min-w-0">
                  <div className="text-[12px] font-semibold text-muted">{t("cp.chatN", { n: prog?.chat ?? 1 })}</div>
                  <div className="truncate text-[15px] font-semibold text-ink" data-testid="cp-current">{prog?.title || t("cp.openingChat")}</div>
                </div>
              </div>
            )}
            <div className={clsx("grid gap-3", runAll ? "grid-cols-3" : "grid-cols-2")}>
              {runAll && (
                <Stat icon={<ListChecks />} label={t("cp.chatsDone")}>
                  {prog?.chats_done ?? Math.max(0, (prog?.chat ?? 1) - 1)}
                </Stat>
              )}
              <Stat icon={<Layers />} label={t(runAll ? "cp.pageInChat" : "cp.pages")}>
                {prog?.page ?? 0}
                <span className="text-[14px] text-muted"> / {prog?.max ?? (runAll ? perChat : maxPages)}</span>
              </Stat>
              <Stat icon={<MessagesSquare />} label={t(runAll ? "cp.total" : "cp.items")}>
                {(prog?.messages ?? 0).toLocaleString()}
              </Stat>
            </div>
            <ProgressBar value={prog && prog.max ? prog.page / prog.max : 0.02} tone="gold" className="h-2" />
            <p className="text-[12.5px] text-muted">{t("cp.dontTouch")}</p>
          </div>
        )}

        {phase === "done" && done && (
          <div className="flex min-w-0 flex-col justify-center gap-4" data-testid="cp-done">
            {done.error ? (
              <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-[13px] text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {errText(done.error)}
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <span className="grid size-12 place-items-center rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-white">
                    <CircleCheckBig className="size-6" />
                  </span>
                  <div>
                    <div className="font-display text-[21px] font-semibold text-ink">{runAll ? t("cp.doneAll", { app: done.app ?? "" }) : t("cp.done")}</div>
                    <div className="text-[13px] text-muted">{runAll ? t("cp.chatsN", { n: captured.length }) : [done.app, done.title].filter(Boolean).join(" · ")}</div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Badge tone="navy">
                    <Layers className="size-3" /> {t("cp.pagesN", { n: done.pages ?? 0 })}
                  </Badge>
                  <Badge tone="green">
                    <MessagesSquare className="size-3" /> {t("cp.messagesN", { n: (done.messages ?? 0).toLocaleString() })}
                  </Badge>
                  <Badge tone="violet">
                    <ImageIcon className="size-3" /> {t("cp.picturesN", { n: done.pictures ?? 0 })}
                  </Badge>
                  {!runAll && <Badge tone={done.reached_top ? "green" : "amber"}>{t(done.reached_top ? "cp.top" : done.stopped ? "cp.stopped" : "cp.limit")}</Badge>}
                  {runAll && done.stopped && <Badge tone="amber">{t("cp.stoppedAll")}</Badge>}
                </div>
                {runAll && (done.chats?.length ?? 0) > 0 && (
                  <div className="max-h-[188px] overflow-auto rounded-2xl border border-line" data-testid="cp-chats">
                    <table className="w-full text-[12.5px]">
                      <thead className="sticky top-0 bg-surface-2 text-left text-[11.5px] text-muted">
                        <tr>
                          <th className="px-3 py-1.5 font-semibold">{t("cp.colChat")}</th>
                          <th className="px-3 py-1.5 text-right font-semibold">{t("cp.colMsgs")}</th>
                          <th className="px-3 py-1.5 font-semibold">{t("cp.colStatus")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {done.chats!.map((c, i) => (
                          <tr key={i} className="border-t border-line">
                            <td className="max-w-[220px] truncate px-3 py-1.5 font-semibold text-ink">{c.title}</td>
                            <td className="tabular px-3 py-1.5 text-right text-ink-2">{c.skipped ? "—" : c.messages.toLocaleString()}</td>
                            <td className="px-3 py-1.5">
                              {c.skipped ? (
                                <Badge tone="slate">{t("cp.skipped")}</Badge>
                              ) : (
                                <Badge tone={c.reached_top ? "green" : "amber"}>{t(c.reached_top ? "cp.top" : done.stopped && i === done.chats!.length - 1 ? "cp.stopped" : "cp.limit")}</Badge>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {done.interrupted && (
                  <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {t("cp.interrupted", { reason: errText(done.interrupted) })}
                  </div>
                )}
                {!done.text_pages && (done.pages ?? 0) > 0 && (
                  <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {t("cp.noText")}
                  </div>
                )}
                <p className="text-[12.5px] text-muted">{t("cp.saved")}</p>
              </>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-line bg-surface-2 px-6 py-3.5">
        <div className="flex-1" />
        {phase === "intro" && (
          <>
            <Button variant="ghost" onClick={close}>
              {t("common.cancel")}
            </Button>
            <Button variant="gold" icon={<Play className="size-4" />} onClick={() => void start()} disabled={all && appInfo?.installed === false} data-testid="cp-start">
              {t(all ? "cp.startAll" : "cp.start")}
            </Button>
          </>
        )}
        {phase === "running" && (
          <Button variant="danger" icon={<Square className="size-4" />} loading={stopping} onClick={() => void stop()} data-testid="cp-stop">
            {t("cp.stop")}
          </Button>
        )}
        {phase === "done" && (
          <>
            <Button variant="ghost" onClick={close}>
              {t("rw.close")}
            </Button>
            <Button variant="outline" icon={<ScanLine className="size-4" />} onClick={() => setPhase("intro")} data-testid="cp-again">
              {t(runAll ? "cp.againAll" : "cp.again")}
            </Button>
            {!done?.error && (
              <Button variant="primary" icon={<MessagesSquare className="size-4" />} onClick={() => void view()} data-testid="cp-view">
                {t("ms.viewChats")}
              </Button>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
