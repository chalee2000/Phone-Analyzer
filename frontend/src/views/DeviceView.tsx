import clsx from "clsx";
import { Download, Image as ImageIcon, MessageSquareText, Pencil, Phone, Sparkles, User } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { CopyButton, DevicePanel } from "../components/DevicePanel";
import { Button } from "../components/ui";
import { fmtSize } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useRecords, useStore } from "../lib/store";
import type { CallRecord, DeviceInfo, SmsMessage } from "../lib/types";

function useCountUp(target: number | undefined, ms = 700) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (target == null) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / ms);
      setValue(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return value;
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  if (!values.length || Math.max(...values) === 0) return null;
  const max = Math.max(...values);
  const w = 96;
  const h = 30;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - (v / max) * (h - 4) - 2]);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <defs>
        <linearGradient id={`sg-${color}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.28" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line} L${w},${h} L0,${h} Z`} fill={`url(#sg-${color})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function perDay(timestamps: (number | null)[], days = 14): number[] {
  const out = new Array(days).fill(0);
  const ts = timestamps.filter((x): x is number => !!x);
  if (!ts.length) return out;
  const end = new Date(Math.max(...ts));
  end.setHours(23, 59, 59, 999);
  for (const t of ts) {
    const diff = Math.floor((end.getTime() - t) / 86_400_000);
    if (diff >= 0 && diff < days) out[days - 1 - diff]++;
  }
  return out;
}

function StatCard({ icon, label, value, tone, spark, delay, onClick }: { icon: ReactNode; label: string; value?: number; tone: string; spark?: number[]; delay: number; onClick?: () => void }) {
  const n = useCountUp(value);
  const tones: Record<string, [string, string]> = {
    blue: ["from-sky-400 to-blue-600", "#2563eb"],
    gold: ["from-gold-300 to-gold-500", "#d4991f"],
    navy: ["from-navy-400 to-navy-700", "#24479a"],
    rose: ["from-pink-400 to-rose-500", "#e11d48"],
  };
  const [grad, color] = tones[tone];
  return (
    <motion.button
      onClick={onClick}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="focus-ring group relative flex items-center gap-4 overflow-hidden rounded-2xl border border-line bg-surface p-4 text-left transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-card)]"
    >
      <span className={clsx("grid size-[52px] shrink-0 place-items-center rounded-2xl bg-gradient-to-br text-white shadow-lg [&_svg]:size-6", grad)}>{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] font-medium text-muted">{label}</span>
        <span className="tabular block font-display text-[30px] leading-tight font-bold text-navy-800 dark:text-white">{value == null ? "—" : n.toLocaleString()}</span>
      </span>
      {spark && <span className="absolute right-3 bottom-3 hidden opacity-90 2xl:block">{<Sparkline values={spark} color={color} />}</span>}
    </motion.button>
  );
}

type Row = { label: string; value: ReactNode; copy?: string; note?: ReactNode; mono?: boolean };

function useRows(info: DeviceInfo): { title: string; rows: Row[] }[] {
  const { t } = useI18n();
  return useMemo(() => {
    const f = (key: keyof DeviceInfo, mono = false): Row | null => {
      const v = info[key];
      if (key === "imei" && !v && info.restricted?.imei) {
        return { label: t("f.imei"), value: <span className="text-faint italic">—</span>, note: t(`restricted.${info.restricted.imei}`) };
      }
      if (v == null || v === "" || (Array.isArray(v) && !v.length)) return null;
      return { label: t(`f.${key}`), value: String(v), copy: String(v), mono };
    };
    const extras = Object.entries(info.extra || {})
      .filter(([k]) => k !== "demo" && k !== "backup_encrypted")
      .map(([k, v]) => ({ label: k, value: v, copy: v, mono: true }));
    const hardware = [f("brand"), f("model"), f("market_name"), f("product"), f("device_name"), f("cpu_abi"), f("serial", true), f("imei", true), f("imei2", true)];
    const system = [f("os_version"), f("build_id", true), f("security_patch"), f("fingerprint", true), f("timezone")];
    const network = [f("phone_number", true), f("carrier"), f("wifi_mac", true), f("bluetooth_mac", true), f("bluetooth_name")];
    const security: (Row | null)[] = [
      ...(info.accounts || []).map((a) => ({ label: t("f.accounts"), value: a, copy: a })),
      info.storage_total ? { label: t("f.storage"), value: `${fmtSize(info.storage_free)} / ${fmtSize(info.storage_total)}` } : null,
      info.battery_level != null ? { label: t("f.battery"), value: `${info.battery_level}% · ${info.battery_status}` } : null,
      ...extras,
    ];
    return [
      { title: t("sec.hardware"), rows: hardware.filter(Boolean) as Row[] },
      { title: t("sec.system"), rows: system.filter(Boolean) as Row[] },
      { title: t("sec.network"), rows: network.filter(Boolean) as Row[] },
      { title: t("sec.security"), rows: security.filter(Boolean) as Row[] },
    ].filter((s) => s.rows.length);
  }, [info, t]);
}

export function DeviceView() {
  const { t } = useI18n();
  const { state, openDialog, setTab, job } = useStore();
  const info = state.device!.info;
  const sections = useRows(info);
  const calls = useRecords<CallRecord>("calls");
  const sms = useRecords<SmsMessage>("sms");
  const extracted = !!state.extraction;
  const connected = !state.device?.offline;
  const running = !!job && !job.finishedAt;
  const c = state.counts;

  return (
    <div className="flex h-full min-h-0 gap-4" data-testid="device-view">
      <DevicePanel />
      <section className="card flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-start gap-4 px-7 pt-6 pb-5">
          <div>
            <h2 className="font-display text-[30px] leading-tight font-bold text-navy-900 dark:text-white">{t("device.title")}</h2>
            <span className="mt-2 block h-[4px] w-24 rounded-full bg-gradient-to-r from-gold-300 to-gold-500" />
          </div>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" icon={<Pencil className="size-4" />} onClick={() => openDialog("number")}>
              {t("device.editNumber")}
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 px-7 xl:grid-cols-4">
          <StatCard delay={0.0} icon={<Phone />} label={t("stat.calls")} value={extracted ? (c.calls ?? 0) : undefined} tone="blue" spark={calls ? perDay(calls.map((x) => x.timestamp)) : undefined} onClick={() => setTab("calls")} />
          <StatCard delay={0.05} icon={<MessageSquareText />} label={t("stat.sms")} value={extracted ? (c.sms ?? 0) : undefined} tone="gold" spark={sms ? perDay(sms.map((x) => x.timestamp)) : undefined} onClick={() => setTab("sms")} />
          <StatCard delay={0.1} icon={<User />} label={t("stat.contacts")} value={extracted ? (c.contacts ?? 0) : undefined} tone="navy" onClick={() => setTab("contacts")} />
          <StatCard delay={0.15} icon={<ImageIcon />} label={t("stat.photos")} value={extracted ? (c.photos ?? 0) : undefined} tone="rose" onClick={() => setTab("photos")} />
        </div>

        {!extracted && connected && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="mx-7 mt-4 flex items-center gap-4 rounded-2xl border border-gold-200 bg-gradient-to-r from-gold-50 to-transparent px-5 py-4 dark:border-gold-500/30 dark:from-gold-500/10"
          >
            <span className="grid size-10 place-items-center rounded-xl bg-gold-400 text-navy-950">
              <Sparkles className="size-5" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="font-display text-[16px] font-semibold text-ink">{t("device.ready")}</div>
              <div className="text-[13px] text-muted">{t("device.readySub")}</div>
            </div>
            <Button variant="gold" icon={<Download className="size-4" />} onClick={() => openDialog("extract")} disabled={running} data-testid="extract-cta">
              {t("rb.extract")}
            </Button>
          </motion.div>
        )}

        <div className="mx-7 mt-5 mb-6 min-h-0 flex-1 overflow-auto rounded-2xl border border-line" data-selectable>
          <div className="sticky top-0 z-10 grid grid-cols-[minmax(180px,0.9fr)_1.6fr_1fr] gap-4 border-b border-line bg-surface-2 px-5 py-3 text-[13px] font-semibold text-muted">
            <span>{t("device.item")}</span>
            <span>{t("device.value")}</span>
            <span>{t("device.note")}</span>
          </div>
          {sections.map((s) => (
            <div key={s.title}>
              <div className="flex items-center gap-2 bg-surface px-5 pt-4 pb-1.5 text-[12px] font-bold tracking-wide text-navy-500 uppercase dark:text-gold-300">
                <span className="size-1.5 rounded-full bg-gold-400" /> {s.title}
              </div>
              {s.rows.map((r, i) => (
                <div
                  key={`${r.label}-${i}`}
                  className="group grid grid-cols-[minmax(180px,0.9fr)_1.6fr_1fr] items-center gap-4 border-b border-line/70 px-5 py-2.5 text-[14px] transition-colors last:border-b-0 hover:bg-row-hover"
                >
                  <span className="truncate text-ink-2">{r.label}</span>
                  <span className={clsx("flex min-w-0 items-center gap-1 text-ink", r.mono && "font-mono text-[13px]")}>
                    <span className="truncate">{r.value}</span>
                    {r.copy && <CopyButton value={r.copy} className="opacity-0 group-hover:opacity-100" />}
                  </span>
                  <span className="text-[12.5px] text-muted">{r.note}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
