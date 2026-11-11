import clsx from "clsx";
import { AlertTriangle, CircleCheckBig, Hand, Image as ImageIcon, Layers, MessagesSquare, Play, ScanLine, Smartphone, Square, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Badge, Button, Field, Input, Modal, ProgressBar, Spinner } from "../components/ui";
import { mediaUrlFor } from "../lib/analysis";
import { call, subscribe } from "../lib/bridge";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";

interface Progress {
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
}

const PAGE_LIMITS = [50, 100, 200, 500];

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
  }, [open]);

  useEffect(() => {
    if (!open) return;
    return subscribe((name, payload) => {
      if (name === "capture.progress") setProg(payload as Progress);
      if (name === "capture.done") {
        const d = payload as Done;
        setDone(d);
        setPhase("done");
        setStopping(false);
        if (d.error) toast.error(d.error);
        void refresh();
      }
    });
  }, [open, refresh]);

  const start = async () => {
    try {
      setProg(null);
      setDone(null);
      await call("capture_start", { max_pages: maxPages, title: title.trim() });
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
            <ol className="flex flex-col gap-3">
              <Step n={1} icon={<Smartphone />}>{t("cp.step1")}</Step>
              <Step n={2} icon={<MessagesSquare />}>{t("cp.step2")}</Step>
              <Step n={3} icon={<Hand />}>{t("cp.step3")}</Step>
            </ol>
            <div className="grid grid-cols-2 gap-4">
              <Field label={t("cp.thread")} hint={t("cp.threadHint")}>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("cp.threadPlaceholder")} />
              </Field>
              <Field label={t("cp.maxPages")}>
                <div className="flex gap-1 rounded-xl bg-surface-3 p-1">
                  {PAGE_LIMITS.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setMaxPages(n)}
                      className={clsx("h-8 flex-1 rounded-lg text-[13px] font-semibold transition", maxPages === n ? "bg-surface text-ink shadow-sm ring-1 ring-line" : "text-muted hover:text-ink")}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </Field>
            </div>
            <div className="flex items-start gap-3 rounded-2xl border border-gold-200 bg-gold-50/70 px-4 py-3 text-[12.5px] text-gold-800 dark:border-gold-500/30 dark:bg-gold-500/10 dark:text-gold-200">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              {t("cp.note")}
            </div>
          </div>
        )}

        {phase === "running" && (
          <div className="flex flex-col justify-center gap-5" data-testid="cp-running">
            <div>
              <div className="font-display text-[22px] font-semibold text-ink">{t("cp.running")}</div>
              <div className="mt-1 text-[13.5px] text-muted">{t("cp.runningSub")}</div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-2xl border border-line bg-surface p-4">
                <div className="flex items-center gap-1.5 text-[12px] font-semibold text-muted">
                  <Layers className="size-3.5" /> {t("cp.pages")}
                </div>
                <div className="mt-1 font-display text-[26px] font-semibold text-ink">
                  {prog?.page ?? 0}
                  <span className="text-[15px] text-muted"> / {prog?.max ?? maxPages}</span>
                </div>
              </div>
              <div className="rounded-2xl border border-line bg-surface p-4">
                <div className="flex items-center gap-1.5 text-[12px] font-semibold text-muted">
                  <MessagesSquare className="size-3.5" /> {t("cp.items")}
                </div>
                <div className="mt-1 font-display text-[26px] font-semibold text-ink">{(prog?.messages ?? 0).toLocaleString()}</div>
              </div>
            </div>
            <ProgressBar value={prog ? prog.page / prog.max : 0.02} tone="gold" className="h-2" />
            <p className="text-[12.5px] text-muted">{t("cp.dontTouch")}</p>
          </div>
        )}

        {phase === "done" && done && (
          <div className="flex flex-col justify-center gap-4" data-testid="cp-done">
            {done.error ? (
              <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-[13px] text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {done.error}
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <span className="grid size-12 place-items-center rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-white">
                    <CircleCheckBig className="size-6" />
                  </span>
                  <div>
                    <div className="font-display text-[21px] font-semibold text-ink">{t("cp.done")}</div>
                    <div className="text-[13px] text-muted">{[done.app, done.title].filter(Boolean).join(" · ")}</div>
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
                  <Badge tone={done.reached_top ? "green" : "amber"}>{t(done.reached_top ? "cp.top" : done.stopped ? "cp.stopped" : "cp.limit")}</Badge>
                </div>
                {!done.text_pages && (
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
            <Button variant="gold" icon={<Play className="size-4" />} onClick={() => void start()} data-testid="cp-start">
              {t("cp.start")}
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
              {t("cp.again")}
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
