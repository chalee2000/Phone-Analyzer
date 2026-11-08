import clsx from "clsx";
import { FolderOpen, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { fmtDateTime } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";

export function StatusBar() {
  const { t } = useI18n();
  const { state, job, deviceName, info } = useStore();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const running = !!job && !job.finishedAt;
  const total = Object.values(state.counts).reduce((a, b) => a + (b ?? 0), 0);
  let text = t("status.ready");
  let tone = "bg-white/50";
  if (running) {
    text = t("status.extracting", { device: deviceName });
    tone = "bg-gold-400 animate-[blink_1.4s_ease-in-out_infinite]";
  } else if (state.extraction && state.device) {
    text = `${t("status.connected", { device: deviceName })} · ${t("status.done", { n: total.toLocaleString() })}`;
    tone = "bg-emerald-400";
  } else if (state.device) {
    text = t("status.connected", { device: deviceName });
    tone = "bg-emerald-400";
  }
  return (
    <footer className="flex h-8 shrink-0 items-center gap-4 bg-navy-950 px-4 text-[12px] text-white/75">
      <span className="flex min-w-0 items-center gap-2">
        <span className={clsx("size-2 rounded-full", tone)} />
        <span className="truncate" data-testid="status-text">{text}</span>
      </span>
      {state.case && (
        <span className="hidden items-center gap-1.5 text-white/60 md:flex">
          <FolderOpen className="size-3.5 text-gold-300" />
          {t("status.case")}: {state.case.case_no || state.case.title}
        </span>
      )}
      <span className="ml-auto flex items-center gap-1.5 text-white/55">
        <ShieldCheck className="size-3.5 text-emerald-300" /> SHA-256
      </span>
      <span className="tabular text-white/60">
        SPNI Phone Analysis v{info?.version ?? "4.0.0"} &nbsp;|&nbsp; {fmtDateTime(now).slice(0, 16)}
      </span>
    </footer>
  );
}
