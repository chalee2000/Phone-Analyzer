import clsx from "clsx";
import {
  BookUser,
  ChartColumnBig,
  Database,
  Download,
  Ellipsis,
  FileBadge,
  FileImage,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  GitMerge,
  History,
  Info,
  Link2,
  MessageCircle,
  Network,
  PhoneCall,
  ScrollText,
  Search,
  Share2,
  Sparkles,
  Stethoscope,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { call } from "../lib/bridge";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { AndroidIcon, IphoneIcon } from "./icons";
import { Spinner, Switch, Tooltip } from "./ui";

type Size = "lg" | "md" | "sm";

function useRibbonSize(): Size {
  const [w, setW] = useState(() => window.innerWidth);
  useEffect(() => {
    const onResize = () => setW(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return w >= 1780 ? "lg" : w >= 1440 ? "md" : "sm";
}

/** Compact two-row grid used for the analysis tools on narrower windows. */
function MiniButton({ icon, label, tone, iconOnly, onClick, soon, testId }: { icon: ReactNode; label: string; tone: string; iconOnly: boolean; onClick?: () => void; soon?: boolean; testId?: string }) {
  const { t } = useI18n();
  return (
    <Tooltip label={iconOnly ? (soon ? `${label} · ${t("rb.soon")}` : label) : undefined}>
      <button
        data-testid={testId}
        onClick={soon || !onClick ? () => toast(t("rb.soon.toast"), { icon: <Sparkles className="size-4 text-gold-500" /> }) : onClick}
        className={clsx(
          "focus-ring group relative flex h-[36px] items-center gap-2 rounded-xl text-left transition hover:bg-surface-2",
          iconOnly ? "w-[42px] justify-center" : "w-[124px] px-1.5",
        )}
      >
        <span className={clsx("grid size-[28px] shrink-0 place-items-center rounded-lg ring-1", TONES[tone])}>{icon}</span>
        {!iconOnly && <span className="truncate text-[12px] font-medium text-ink-2">{label}</span>}
        {soon && <span className="absolute top-1 right-1 size-1.5 rounded-full bg-gold-400" />}
      </button>
    </Tooltip>
  );
}

const TONES: Record<string, string> = {
  blue: "bg-sky-50 text-sky-600 ring-sky-100 dark:bg-sky-500/12 dark:text-sky-300 dark:ring-sky-400/15",
  indigo: "bg-indigo-50 text-indigo-600 ring-indigo-100 dark:bg-indigo-500/12 dark:text-indigo-300 dark:ring-indigo-400/15",
  violet: "bg-violet-50 text-violet-600 ring-violet-100 dark:bg-violet-500/12 dark:text-violet-300 dark:ring-violet-400/15",
  emerald: "bg-emerald-50 text-emerald-600 ring-emerald-100 dark:bg-emerald-500/12 dark:text-emerald-300 dark:ring-emerald-400/15",
  teal: "bg-teal-50 text-teal-600 ring-teal-100 dark:bg-teal-500/12 dark:text-teal-300 dark:ring-teal-400/15",
  rose: "bg-rose-50 text-rose-600 ring-rose-100 dark:bg-rose-500/12 dark:text-rose-300 dark:ring-rose-400/15",
  orange: "bg-orange-50 text-orange-600 ring-orange-100 dark:bg-orange-500/12 dark:text-orange-300 dark:ring-orange-400/15",
  amber: "bg-amber-50 text-amber-600 ring-amber-100 dark:bg-amber-500/12 dark:text-amber-300 dark:ring-amber-400/15",
  navy: "bg-navy-50 text-navy-600 ring-navy-100 dark:bg-navy-500/15 dark:text-navy-200 dark:ring-navy-400/15",
  slate: "bg-surface-3 text-ink-2 ring-line",
};

function RButton({
  icon,
  label,
  tone = "navy",
  onClick,
  primary,
  disabled,
  soon,
  tip,
  loading,
  testId,
  size = "lg",
}: {
  size?: Size;
  icon: ReactNode;
  label: string;
  tone?: keyof typeof TONES;
  onClick?: () => void;
  primary?: boolean;
  disabled?: boolean;
  soon?: boolean;
  tip?: string;
  loading?: boolean;
  testId?: string;
}) {
  const { t } = useI18n();
  return (
    <Tooltip label={tip}>
      <button
        data-testid={testId}
        onClick={soon ? () => toast(t("rb.soon.toast"), { icon: <Sparkles className="size-4 text-gold-500" /> }) : onClick}
        disabled={disabled || loading}
        className={clsx(
          "focus-ring group relative flex flex-col items-center justify-start gap-1.5 rounded-2xl px-1 transition-all duration-150",
          size === "lg" && "h-[84px] w-[88px] pt-2.5",
          size === "md" && "h-[80px] w-[72px] pt-2",
          size === "sm" && "h-[76px] w-[68px] pt-2",
          "disabled:cursor-not-allowed disabled:opacity-45",
          primary
            ? "bg-gradient-to-b from-gold-50 to-gold-100/70 ring-1 ring-gold-300 hover:-translate-y-0.5 hover:shadow-[0_10px_22px_-12px_rgba(220,162,42,0.9)] dark:from-gold-500/15 dark:to-gold-500/5 dark:ring-gold-400/40"
            : "hover:-translate-y-0.5 hover:bg-surface-2 hover:shadow-[0_8px_18px_-12px_rgba(16,32,72,0.35)]",
          soon && "opacity-80",
        )}
      >
        <span
          className={clsx(
            "grid place-items-center rounded-xl ring-1 transition-transform duration-200 group-hover:scale-105",
            size === "sm" ? "size-9" : "size-10",
            primary ? "bg-gradient-to-b from-gold-300 to-gold-500 text-navy-950 ring-gold-400/60 shadow-[0_6px_14px_-6px_rgba(220,162,42,0.9)]" : TONES[tone],
          )}
        >
          {loading ? <Spinner className="size-5" /> : icon}
        </span>
        <span className={clsx("line-clamp-2 text-center leading-[1.25]", size === "sm" ? "text-[11px]" : "text-[12px]", primary ? "font-bold text-navy-900 dark:text-gold-200" : "font-medium text-ink-2")}>
          {label}
        </span>
        {soon && (
          <span className="absolute top-1 right-1 rounded-full bg-gold-400/90 px-1.5 text-[9.5px] leading-4 font-bold text-navy-950">{t("rb.soon")}</span>
        )}
      </button>
    </Tooltip>
  );
}

function Group({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("card flex shrink-0 flex-col px-3 pt-2 pb-2", className)}>
      <h3 className="mb-1 flex items-center gap-2 px-1 text-[12px] font-semibold tracking-wide text-muted">
        <span className="h-3 w-1 rounded-full bg-gold-400" />
        {title}
      </h3>
      <div className="flex items-center gap-0.5">{children}</div>
    </section>
  );
}

function PlatformToggle({ size }: { size: Size }) {
  const { platform, setPlatform, state } = useStore();
  const locked = !!state.device && !state.device.offline;
  const item = (p: "android" | "ios", icon: ReactNode, label: string) => (
    <button
      data-testid={`platform-${p}`}
      onClick={() => setPlatform(p)}
      disabled={locked && platform !== p}
      className={clsx(
        "focus-ring flex flex-col items-center justify-center gap-1.5 rounded-xl text-[13.5px] font-bold transition-all",
        size === "sm" ? "h-[68px] w-[64px]" : "h-[72px] w-[72px]",
        platform === p
          ? "bg-gradient-to-b from-navy-700 to-navy-900 text-white shadow-[0_8px_18px_-8px_rgba(11,27,61,0.8)]"
          : "text-ink-2 hover:bg-surface disabled:opacity-40",
      )}
    >
      {icon}
      {label}
    </button>
  );
  return (
    <div className="mr-1.5 flex gap-1 rounded-2xl bg-surface-3 p-1">
      {item("android", <AndroidIcon className={clsx("size-6", platform === "android" && "text-[#3DDC84]")} />, "Android")}
      {item("ios", <IphoneIcon className="size-6" />, "iOS")}
    </div>
  );
}

function MoreMenu({ size }: { size: Size }) {
  const { t } = useI18n();
  const { info, setInfo, openDialog, platform, state } = useStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);
  const item = (icon: ReactNode, label: string, onClick: () => void, right?: ReactNode) => (
    <button
      onClick={() => {
        onClick();
        if (!right) setOpen(false);
      }}
      className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[13.5px] text-ink hover:bg-surface-2"
    >
      <span className="text-muted">{icon}</span>
      <span className="flex-1">{label}</span>
      {right}
    </button>
  );
  return (
    <div className="relative" ref={ref}>
      <RButton size={size} icon={<Ellipsis className="size-5" />} label={t("rb.more")} tone="slate" onClick={() => setOpen((o) => !o)} testId="more" />
      {open && (
        <div className="absolute top-full right-0 z-30 mt-2 w-72 rounded-2xl border border-line bg-surface p-1.5 shadow-[var(--shadow-pop)]">
          {item(<Stethoscope className="size-4.5" />, t("more.diag"), () => openDialog("diag", { platform, notFound: false }))}
          {item(<ScrollText className="size-4.5" />, t("more.audit"), () => openDialog("audit"))}
          {item(<FolderOpen className="size-4.5" />, t("more.folder"), () => state.case && void call("open_case_folder"))}
          {item(<MessageCircle className="size-4.5" />, t("ms.open"), () => openDialog("messenger"))}
          {item(<MessageCircle className="size-4.5 text-[#06c755]" />, t("ln.open"), () => openDialog("messenger", "line"))}
          <div className="my-1 h-px bg-line" />
          {item(
            <Sparkles className="size-4.5" />,
            t("more.demo"),
            () => {},
            <Switch
              checked={!!info?.demo}
              onChange={async (v) => {
                await call("set_demo", v);
                if (info) setInfo({ ...info, demo: v });
              }}
            />,
          )}
          {item(<Info className="size-4.5" />, t("more.about"), () => openDialog("about"))}
        </div>
      )}
    </div>
  );
}

export function Ribbon() {
  const { t, lang } = useI18n();
  const { state, scan, scanning, openDialog, exportReport, job, platform, setTab, exportNetwork } = useStore();
  const connected = !!state.device && !state.device.offline;
  const running = state.running || (!!job && !job.finishedAt);
  const hasData = !!state.extraction;
  const size = useRibbonSize();
  const hasCase = !!state.case;
  const canReport = hasData || !!state.case?.extraction_count;
  const analysis: { icon: ReactNode; label: string; tone: string; onClick?: () => void; soon?: boolean; id: string }[] = [
    { id: "i2", icon: <Share2 className="size-[18px]" />, label: t("rb.i2"), tone: "orange", onClick: () => (hasCase ? void exportNetwork("anx") : openDialog("cases")) },
    { id: "timeline", icon: <ChartColumnBig className="size-[18px]" />, label: t("rb.timeline"), tone: "blue", onClick: () => setTab("timeline") },
    { id: "link", icon: <Link2 className="size-[18px]" />, label: t("rb.link"), tone: "indigo", soon: true },
    { id: "pattern", icon: <Network className="size-[18px]" />, label: t("rb.pattern"), tone: "amber", onClick: () => setTab("comms") },
    { id: "cross", icon: <GitMerge className="size-[18px]" />, label: t("rb.cross"), tone: "violet", onClick: () => setTab("network") },
    {
      id: "cdr",
      icon: <PhoneCall className="size-[18px]" />,
      label: t("rb.cdr"),
      tone: "teal",
      onClick: () => {
        setTab("comms");
        window.dispatchEvent(new Event("spni:cdr-import"));
      },
    },
  ];

  return (
    <div className="flex shrink-0 gap-3 overflow-x-auto px-5 pt-3.5 pb-1">
      <Group title={t("group.device")}>
        <PlatformToggle size={size} />
        <RButton size={size} icon={<Search className="size-5" />} label={t("rb.scan")} tone="blue" onClick={() => void scan()} loading={scanning} tip={t("tip.scan")} testId="scan" />
        <RButton
          icon={<Download className="size-5" />}
          label={t("rb.extract")}
          primary
          disabled={!connected || running}
          onClick={() => openDialog("extract")}
          tip={t("tip.extract")}
          testId="extract"
        />
        <RButton size={size} icon={<History className="size-5" />} label={t("rb.history")} tone="violet" onClick={() => openDialog("history")} tip={t("tip.history")} testId="history" />
        <RButton size={size} icon={<Stethoscope className="size-5" />} label={t("rb.diag")} tone="teal" onClick={() => openDialog("diag", { platform, notFound: false })} tip={t("tip.diag")} testId="diag" />
        <RButton size={size} icon={<FileImage className="size-5" />} label={t("rb.word")} tone="indigo" disabled={!hasData} onClick={() => void exportReport("word", lang)} tip={t("tip.word")} testId="word" />
      </Group>

      <Group title={t("group.analysis")}>
        {size === "lg" ? (
          analysis.map((a) => <RButton size={size} key={a.id} icon={a.icon} label={a.label} tone={a.tone} soon={a.soon} onClick={a.onClick} testId={`rb-${a.id}`} />)
        ) : (
          <div className="grid grid-flow-col grid-rows-2 gap-x-0.5 gap-y-1 py-0.5">
            {analysis.map((a) => (
              <MiniButton key={a.id} icon={a.icon} label={a.label} tone={a.tone} iconOnly={size === "sm"} onClick={a.onClick} soon={a.soon} testId={`rb-${a.id}`} />
            ))}
          </div>
        )}
      </Group>

      <Group title={t("group.report")}>
        <RButton size={size} icon={<FileSpreadsheet className="size-5" />} label={t("rb.excel")} tone="emerald" disabled={!hasData} onClick={() => void exportReport("excel", lang)} tip={t("tip.excel")} testId="excel" />
        <RButton size={size} icon={<FileText className="size-5" />} label={t("rb.pdf")} tone="rose" disabled={!canReport} onClick={() => openDialog("report", { formats: ["pdf"] })} tip={t("tip.pdf")} testId="pdf" />
        <RButton size={size} icon={<FileBadge className="size-5" />} label={t("rb.report")} tone="navy" disabled={!canReport} onClick={() => openDialog("report", {})} tip={t("tip.report")} testId="report" />
      </Group>

      <Group title={t("group.case")}>
        <RButton size={size} icon={<FolderOpen className="size-5" />} label={t("rb.cases")} tone="amber" onClick={() => openDialog("cases")} tip={t("tip.cases")} testId="cases" />
        <RButton size={size} icon={<Database className="size-5" />} label={t("rb.database")} tone="navy" onClick={() => (state.case ? void call("open_case_folder") : openDialog("cases"))} tip={t("tip.database")} />
        <RButton size={size} icon={<BookUser className="size-5" />} label={t("rb.numbers")} tone="blue" soon />
        <MoreMenu size={size} />
      </Group>
    </div>
  );
}
