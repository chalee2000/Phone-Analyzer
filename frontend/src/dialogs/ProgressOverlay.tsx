import clsx from "clsx";
import { CircleAlert, CircleCheck, CircleDashed, FileText, Lock, Sparkles, X } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { PhoneMockup } from "../components/PhoneMockup";
import { TAB_ICONS } from "../components/TabBar";
import { Button, Modal, ProgressBar, Spinner } from "../components/ui";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";

function elapsed(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function Burst() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {Array.from({ length: 22 }).map((_, i) => {
        const angle = (i / 22) * Math.PI * 2;
        return (
          <motion.span
            key={i}
            className={clsx("absolute top-[38%] left-1/2 size-2 rounded-full", i % 3 === 0 ? "bg-gold-400" : i % 3 === 1 ? "bg-emerald-400" : "bg-sky-400")}
            initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
            animate={{ x: Math.cos(angle) * (140 + (i % 4) * 30), y: Math.sin(angle) * (100 + (i % 5) * 18), opacity: 0, scale: 0.4 }}
            transition={{ duration: 1.1, ease: "easeOut" }}
          />
        );
      })}
    </div>
  );
}

export function ProgressOverlay() {
  const { t } = useI18n();
  const { job, setJob, cancelExtraction, state, deviceName, setTab, openDialog } = useStore();
  const [now, setNow] = useState(Date.now());
  const done = !!job?.finishedAt;
  const jobId = job?.id;
  useEffect(() => {
    if (!jobId || done) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(id);
  }, [jobId, done]);
  if (!job) return null;

  const steps = job.kinds.map((k) => ({ kind: k, ...(job.steps[k] ?? { status: "waiting" as const, progress: 0 }) }));
  const finished = steps.filter((s) => s.status !== "waiting" && s.status !== "running").length;
  const overall = done ? 1 : (finished + steps.reduce((a, s) => a + (s.status === "running" ? s.progress : 0), 0)) / Math.max(1, steps.length);
  const total = steps.reduce((a, s) => a + (s.count ?? 0), 0);
  const stage = job.stage;
  const stageText = stage
    ? t(`pg.stage.${stage.message}`, { p: stage.progress != null ? `${Math.round(stage.progress * 100)}%` : "" })
    : "";
  const close = () => setJob(null);
  const ok = job.status === "completed";

  return (
    <Modal open dismissable={done} onClose={close} width={900}>
      <div className="relative flex min-h-0" data-testid="progress-overlay">
        {done && ok && <Burst />}
        <div className="relative hidden w-[260px] shrink-0 flex-col items-center justify-center bg-gradient-to-b from-navy-800 to-navy-950 py-10 text-white md:flex">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_30%,rgba(242,193,78,0.18),transparent_60%)]" />
          <PhoneMockup platform={state.device?.info.platform ?? "android"} battery={state.device?.info.battery_level} connected={!done} width={150} />
          <div className="relative mt-6 px-6 text-center">
            <div className="font-display text-[18px] font-semibold">{deviceName}</div>
            <div className="tabular mt-1 text-[12.5px] text-white/60">{elapsed((job.finishedAt ?? now) - job.startedAt)}</div>
          </div>
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="border-b border-line px-6 pt-5 pb-4">
            <div className="flex items-center gap-3">
              {done ? (
                ok ? (
                  <CircleCheck className="size-7 text-emerald-500" />
                ) : (
                  <CircleAlert className="size-7 text-amber-500" />
                )
              ) : (
                <Spinner className="size-6 text-navy-600 dark:text-gold-300" />
              )}
              <h2 className="font-display text-[21px] font-semibold text-ink">
                {done ? (ok ? t("pg.done") : job.status === "cancelled" ? t("pg.cancelled") : t("pg.failed")) : t("pg.title")}
              </h2>
              <span className="tabular ml-auto font-display text-[22px] font-bold text-navy-700 dark:text-gold-300">{Math.round(overall * 100)}%</span>
            </div>
            <ProgressBar value={overall} tone={done && ok ? "green" : "gold"} className="mt-3 h-2" />
            <div className="mt-2 min-h-5 text-[12.5px] text-muted">
              {done
                ? job.message === "ios_backup_password_required"
                  ? t("pg.passwordRequired")
                  : job.message || `${t("pg.items", { n: total.toLocaleString() })} · ${t("pg.elapsed", { t: elapsed(job.finishedAt! - job.startedAt) })}`
                : stageText}
            </div>
          </div>
          <div className="grid max-h-[420px] min-h-0 grid-cols-2 gap-x-4 gap-y-1 overflow-auto px-6 py-4">
            {steps.map((s) => (
              <div key={s.kind} className="flex items-center gap-3 rounded-xl px-2 py-2">
                <span
                  className={clsx(
                    "grid size-9 shrink-0 place-items-center rounded-xl",
                    s.status === "done" && "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15",
                    s.status === "running" && "bg-gold-50 text-gold-600 dark:bg-gold-500/15",
                    s.status === "waiting" && "bg-surface-3 text-faint",
                    (s.status === "unavailable" || s.status === "error") && "bg-amber-50 text-amber-600 dark:bg-amber-500/15",
                  )}
                >
                  {TAB_ICONS[s.kind]}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[13.5px] font-semibold text-ink">{t(`tab.${s.kind}`)}</span>
                    <span className="tabular ml-auto text-[12px] text-muted">
                      {s.status === "done" && t("pg.items", { n: (s.count ?? 0).toLocaleString() })}
                      {s.status === "waiting" && t("pg.waiting")}
                      {s.status === "running" && s.count != null && s.count.toLocaleString()}
                    </span>
                    {s.status === "done" && <CircleCheck className="size-4 text-emerald-500" />}
                    {s.status === "waiting" && <CircleDashed className="size-4 text-faint" />}
                    {s.status === "running" && <Spinner className="size-4 text-gold-500" />}
                    {(s.status === "unavailable" || s.status === "error") && <Lock className="size-4 text-amber-500" />}
                  </div>
                  {s.status === "running" ? (
                    <ProgressBar value={s.progress} tone="gold" className="mt-1.5" />
                  ) : s.status === "unavailable" || s.status === "error" ? (
                    <div className="mt-0.5 truncate text-[11.5px] text-amber-600 dark:text-amber-400">{t(`reason.${s.reason ?? "error"}`)}</div>
                  ) : (
                    <ProgressBar value={s.status === "done" ? 1 : 0} tone="green" className="mt-1.5" />
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-auto flex items-center justify-end gap-2 border-t border-line bg-surface-2 px-6 py-4">
            {!done ? (
              <Button variant="outline" icon={<X className="size-4" />} onClick={() => void cancelExtraction()}>
                {t("pg.cancel")}
              </Button>
            ) : (
              <>
                {ok && (
                  <Button
                    variant="outline"
                    icon={<FileText className="size-4" />}
                    onClick={() => {
                      close();
                      openDialog("report", { formats: ["pdf"] });
                    }}
                    data-testid="pg-report"
                  >
                    {t("pg.pdf")}
                  </Button>
                )}
                <Button
                  variant="primary"
                  icon={<Sparkles className="size-4" />}
                  onClick={() => {
                    close();
                    setTab("device");
                  }}
                  data-testid="view-data"
                >
                  {t("pg.view")}
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}
