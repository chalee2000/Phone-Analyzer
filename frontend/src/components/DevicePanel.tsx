import clsx from "clsx";
import { BatteryCharging, Check, Copy, HardDrive, Pencil, Unplug, X } from "lucide-react";
import { useEffect, useState } from "react";
import { fmtIso, fmtSize } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { PhoneMockup } from "./PhoneMockup";
import { Badge, Button } from "./ui";

export function CopyButton({ value, className }: { value: string; className?: string }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  return (
    <button
      title={t("device.copy")}
      onClick={(e) => {
        e.stopPropagation();
        void navigator.clipboard?.writeText(value);
        setDone(true);
        window.setTimeout(() => setDone(false), 1200);
      }}
      className={clsx("focus-ring grid size-7 place-items-center rounded-lg text-faint transition hover:bg-surface-3 hover:text-ink", className)}
    >
      {done ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
    </button>
  );
}

function BatteryRing({ level, charging }: { level: number; charging: boolean }) {
  const r = 18;
  const c = 2 * Math.PI * r;
  const tone = level > 50 ? "#10b981" : level > 20 ? "#f59e0b" : "#f43f5e";
  return (
    <div className="relative size-12">
      <svg viewBox="0 0 44 44" className="size-12 -rotate-90">
        <circle cx="22" cy="22" r={r} stroke="var(--border)" strokeWidth="4.5" fill="none" />
        <circle cx="22" cy="22" r={r} stroke={tone} strokeWidth="4.5" fill="none" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - level / 100)} />
      </svg>
      <span className="tabular absolute inset-0 grid place-items-center text-[11.5px] font-bold text-ink">
        {charging ? <BatteryCharging className="size-4 text-emerald-500" /> : `${level}`}
      </span>
    </div>
  );
}

function usePhoneWidth() {
  const [h, setH] = useState(() => window.innerHeight);
  useEffect(() => {
    const onResize = () => setH(window.innerHeight);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return h >= 1080 ? 176 : h >= 940 ? 136 : 112;
}

export function DevicePanel() {
  const { t } = useI18n();
  const phoneWidth = usePhoneWidth();
  const { state, openDialog, disconnect, closeExtraction, job } = useStore();
  const dev = state.device;
  if (!dev) return null;
  const info = dev.info;
  const ios = info.platform === "ios";
  const title = info.market_name || info.model;
  const connected = !dev.offline;
  const used = info.storage_total && info.storage_free != null ? 1 - info.storage_free / info.storage_total : null;
  const running = !!job && !job.finishedAt;

  return (
    <aside className="card relative flex w-[340px] shrink-0 flex-col items-center overflow-x-hidden overflow-y-auto px-6 pt-7 pb-4 2xl:w-[380px]">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(closest-side,rgba(36,71,154,0.12),transparent)] dark:bg-[radial-gradient(closest-side,rgba(242,193,78,0.10),transparent)]" />
      <PhoneMockup platform={info.platform} battery={info.battery_level} connected={connected} width={phoneWidth} />

      <h2 className="mt-6 max-w-full shrink-0 truncate text-center font-display text-[27px] leading-tight font-bold text-ink" data-testid="device-title">
        {title}
      </h2>
      <p className="mt-0.5 text-[14.5px] text-muted">
        {ios ? "iOS" : "Android"} {info.os_version}
        {info.brand && !ios ? ` · ${info.brand}` : ""}
      </p>

      <div className="mt-3 flex flex-wrap items-center justify-center gap-1.5">
        {connected ? (
          <Badge tone="green" className="px-3 py-1 text-[13px]">
            <span className="size-2 rounded-full bg-emerald-500" /> {t("conn.connected")}
          </Badge>
        ) : (
          <Badge tone="amber" className="px-3 py-1 text-[13px]">
            {t("conn.offline")}
          </Badge>
        )}
        {dev.demo && (
          <Badge tone="gold" className="px-3 py-1 text-[13px]">
            {t("conn.demo")}
          </Badge>
        )}
      </div>

      <button
        onClick={() => openDialog("number")}
        className="group mt-3 flex items-center gap-2 rounded-xl px-3 py-1.5 transition hover:bg-surface-2"
        data-testid="device-number"
      >
        {info.phone_number ? (
          <span className="tabular font-display text-[21px] font-semibold text-gold-600 dark:text-gold-300">{info.phone_number}</span>
        ) : (
          <span className="text-[13.5px] text-faint">{t("device.noNumber")}</span>
        )}
        <Pencil className="size-3.5 text-faint group-hover:text-ink" />
      </button>

      <div className="mt-4 grid w-full grid-cols-2 gap-2.5">
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface-2 px-3 py-2.5">
          <BatteryRing level={info.battery_level ?? 0} charging={info.battery_status === "charging"} />
          <div className="min-w-0">
            <div className="text-[11.5px] text-muted">{t("device.battery")}</div>
            <div className="tabular font-display text-[17px] font-semibold text-ink">{info.battery_level != null ? `${info.battery_level}%` : "—"}</div>
          </div>
        </div>
        <div className="flex flex-col justify-center gap-1.5 rounded-2xl border border-line bg-surface-2 px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-[11.5px] text-muted">
            <HardDrive className="size-3.5" /> {t("device.storage")}
          </div>
          <div className="tabular font-display text-[15px] leading-none font-semibold text-ink">{fmtSize(info.storage_free)}</div>
          <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
            <div className="h-full rounded-full bg-gradient-to-r from-navy-400 to-navy-700 dark:from-gold-300 dark:to-gold-500" style={{ width: `${Math.round((used ?? 0) * 100)}%` }} />
          </div>
          <div className="tabular text-[10.5px] text-faint">/ {fmtSize(info.storage_total)}</div>
        </div>
      </div>

      <div className="mt-2.5 flex w-full items-center gap-2 rounded-2xl border border-line px-3 py-2">
        <span className="text-[11.5px] whitespace-nowrap text-muted">Serial</span>
        <span className="tabular min-w-0 flex-1 truncate font-mono text-[12px] text-ink-2" data-selectable>
          {info.serial}
        </span>
        <CopyButton value={info.serial} />
      </div>

      {state.extraction && (
        <p className="mt-3 text-center text-[12px] text-faint">{t("device.offlineSub", { date: fmtIso(state.extraction.finished || state.extraction.started) })}</p>
      )}

      {connected ? (
        <Button variant="ghost" size="sm" className="mt-auto shrink-0 text-muted" icon={<Unplug className="size-4" />} onClick={() => void disconnect()} disabled={running}>
          {t("common.disconnect")}
        </Button>
      ) : (
        <Button variant="ghost" size="sm" className="mt-auto shrink-0 text-muted" icon={<X className="size-4" />} onClick={() => void closeExtraction()}>
          {t("common.closeData")}
        </Button>
      )}
    </aside>
  );
}
