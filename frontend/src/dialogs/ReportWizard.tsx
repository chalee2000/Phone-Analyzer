import clsx from "clsx";
import {
  ArrowLeft,
  ArrowRight,
  BookmarkCheck,
  Briefcase,
  CalendarRange,
  Check,
  CircleCheckBig,
  ClipboardCheck,
  Database,
  Eye,
  EyeOff,
  FileBadge,
  FileSpreadsheet,
  FileText,
  FileType2,
  FolderOpen,
  Globe,
  Hash,
  Image,
  Info,
  KeyRound,
  Languages,
  LayoutList,
  ListOrdered,
  Network,
  Package,
  PenLine,
  PhoneCall,
  ScrollText,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Smartphone,
  Users,
  GitMerge,
  BarChart3,
  RotateCcw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { CopyButton } from "../components/DevicePanel";
import { AndroidIcon, IphoneIcon } from "../components/icons";
import { TAB_ICONS } from "../components/TabBar";
import { Badge, Button, Field, Input, Modal, ProgressBar, Spinner, Switch } from "../components/ui";
import { DEVICE_COLORS, type CaseDevice } from "../lib/analysis";
import { call, subscribe } from "../lib/bridge";
import { fmtSize } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { renderNetworkPng } from "../lib/reportChart";
import { useStore } from "../lib/store";
import { ALL_KINDS, type Kind } from "../lib/types";

type Format = "pdf" | "docx" | "xlsx" | "html" | "zip";
type Section = "devices" | "summary" | "network" | "cross_device" | "top_contacts" | "bookmarks" | "records" | "photos" | "hashes" | "audit" | "signature";
type StepId = "general" | "case" | "dataset" | "security" | "format" | "summary";

const FORMATS: Format[] = ["pdf", "docx", "xlsx", "html", "zip"];
const SECTIONS: Section[] = ["devices", "summary", "network", "cross_device", "top_contacts", "bookmarks", "records", "photos", "hashes", "audit", "signature"];
const CLASSIFICATIONS = ["", "ปกปิด", "ลับ", "ลับมาก", "ลับที่สุด"];
const CASE_KEYS = ["case_no", "title", "crime_type", "evidence_no", "examiner", "investigator", "department", "organization", "location", "note"] as const;
const MAX_ROWS = [500, 1000, 3000, 10000, 50000];

const FORMAT_META: Record<Format, { icon: ReactNode; name: string; tone: string }> = {
  pdf: { icon: <FileText className="size-5" />, name: "PDF", tone: "from-rose-500 to-rose-700" },
  docx: { icon: <FileType2 className="size-5" />, name: "Word", tone: "from-indigo-500 to-indigo-700" },
  xlsx: { icon: <FileSpreadsheet className="size-5" />, name: "Excel", tone: "from-emerald-500 to-emerald-700" },
  html: { icon: <Globe className="size-5" />, name: "HTML", tone: "from-sky-500 to-sky-700" },
  zip: { icon: <Package className="size-5" />, name: "ZIP", tone: "from-amber-500 to-amber-700" },
};

const SECTION_ICON: Record<Section, ReactNode> = {
  devices: <Smartphone className="size-4" />,
  summary: <BarChart3 className="size-4" />,
  network: <Network className="size-4" />,
  cross_device: <GitMerge className="size-4" />,
  top_contacts: <Users className="size-4" />,
  bookmarks: <BookmarkCheck className="size-4" />,
  records: <LayoutList className="size-4" />,
  photos: <Image className="size-4" />,
  hashes: <Hash className="size-4" />,
  audit: <ScrollText className="size-4" />,
  signature: <PenLine className="size-4" />,
};

const STEPS: { id: StepId; icon: ReactNode }[] = [
  { id: "general", icon: <Settings2 className="size-[18px]" /> },
  { id: "case", icon: <Briefcase className="size-[18px]" /> },
  { id: "dataset", icon: <Database className="size-[18px]" /> },
  { id: "security", icon: <ShieldCheck className="size-[18px]" /> },
  { id: "format", icon: <SlidersHorizontal className="size-[18px]" /> },
  { id: "summary", icon: <ClipboardCheck className="size-[18px]" /> },
];

interface ReportDevice extends CaseDevice {
  counts: Partial<Record<Kind, number>>;
}
interface Defaults {
  file_name: string;
  out_dir: string;
  case: Record<string, string>;
  devices: ReportDevice[];
  bookmarks: number;
}
interface Prefs {
  formats: Format[];
  sections: Section[];
  classification: string;
  hash_file: boolean;
  lang: "th" | "en";
  buddhist_year: boolean;
  newest_first: boolean;
  orientation: "landscape" | "portrait";
  max_rows: number;
  thumbnails: boolean;
  top_n: number;
}
interface ReportFile {
  format: Format;
  path: string;
  name: string;
  size: number;
  sha256: string;
}
interface ReportResult {
  report_id: string;
  out_dir: string;
  files: ReportFile[];
}

const PREFS_KEY = "spni.report.prefs";
const DEFAULT_PREFS: Prefs = {
  formats: ["pdf"],
  sections: [...SECTIONS],
  classification: "",
  hash_file: true,
  lang: "th",
  buddhist_year: true,
  newest_first: true,
  orientation: "landscape",
  max_rows: 3000,
  thumbnails: true,
  top_n: 20,
};

function loadPrefs(): Prefs {
  try {
    return { ...DEFAULT_PREFS, ...(JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") as Partial<Prefs>) };
  } catch {
    return DEFAULT_PREFS;
  }
}
function savePrefs(p: Prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(p));
  } catch {
    /* ignore */
  }
}

/* ── small building blocks ─────────────────────────────────────────── */
function Seg<T extends string | number | boolean>({ value, options, onChange, disabled }: { value: T; options: { v: T; label: ReactNode }[]; onChange: (v: T) => void; disabled?: boolean }) {
  return (
    <div className={clsx("inline-flex flex-wrap gap-1 rounded-xl bg-surface-3 p-1", disabled && "pointer-events-none opacity-45")}>
      {options.map((o) => (
        <button
          key={String(o.v)}
          type="button"
          onClick={() => onChange(o.v)}
          className={clsx(
            "focus-ring flex h-8 items-center gap-1.5 rounded-lg px-3 text-[13px] font-semibold transition",
            value === o.v ? "bg-surface text-navy-800 shadow-sm ring-1 ring-line dark:text-gold-200" : "text-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function ToggleRow({ icon, label, hint, checked, onChange, disabled, right }: { icon: ReactNode; label: ReactNode; hint?: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; right?: ReactNode }) {
  return (
    <div className={clsx("flex items-center gap-3 rounded-xl border px-3 py-2.5 transition", checked && !disabled ? "border-navy-200 bg-navy-50/50 dark:border-navy-600 dark:bg-navy-800/30" : "border-line bg-surface", disabled && "opacity-50")}>
      <span className={clsx("grid size-8 shrink-0 place-items-center rounded-lg", checked && !disabled ? "bg-navy-700 text-white dark:bg-gold-400 dark:text-navy-950" : "bg-surface-3 text-muted")}>{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13.5px] font-semibold text-ink">{label}</span>
        {hint && <span className="block text-[12px] text-muted">{hint}</span>}
      </span>
      {right}
      <Switch checked={checked && !disabled} onChange={onChange} disabled={disabled} />
    </div>
  );
}

function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-2.5 flex items-center gap-2">
      <span className="h-3.5 w-1 rounded-full bg-gold-400" />
      <h4 className="flex-1 text-[13.5px] font-bold text-ink">{children}</h4>
      {right}
    </div>
  );
}

function Stamp({ text }: { text: string }) {
  return <span className="inline-block -rotate-3 rounded-md border-2 border-rose-600 px-2 py-0.5 text-[12px] font-extrabold tracking-wider text-rose-600 dark:border-rose-400 dark:text-rose-400">{text}</span>;
}

function DeviceIcon({ d }: { d: CaseDevice }) {
  if (d.method === "cdr") return <PhoneCall className="size-5" />;
  return d.platform === "ios" ? <IphoneIcon className="size-5" /> : <AndroidIcon className="size-5" />;
}

/* ── the wizard ────────────────────────────────────────────────────── */
export function ReportWizard() {
  const { t } = useI18n();
  const { dialogs, closeDialog, state, errorText, info } = useStore();
  const open = !!dialogs.report;
  const [step, setStep] = useState(0);
  const [visited, setVisited] = useState<Set<number>>(new Set([0]));
  const [defaults, setDefaults] = useState<Defaults | null>(null);
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs);
  const [fileName, setFileName] = useState("");
  const [outDir, setOutDir] = useState("");
  const [docTitle, setDocTitle] = useState("");
  const [caseInfo, setCaseInfo] = useState<Record<string, string>>({});
  const [devices, setDevices] = useState<string[]>([]);
  const [kinds, setKinds] = useState<Kind[]>([...ALL_KINDS]);
  const [range, setRange] = useState<"all" | "custom">("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [phase, setPhase] = useState<"edit" | "working" | "done">("edit");
  const [progress, setProgress] = useState<{ step: string; progress: number }>({ step: "chart", progress: 0 });
  const [result, setResult] = useState<ReportResult | null>(null);

  const setPref = <K extends keyof Prefs>(k: K, v: Prefs[K]) => setPrefs((p) => ({ ...p, [k]: v }));

  // Load defaults every time the wizard opens.
  useEffect(() => {
    if (!open) return;
    setStep(0);
    setVisited(new Set([0]));
    setPhase("edit");
    setResult(null);
    setPassword("");
    setConfirm("");
    const p = loadPrefs();
    if (dialogs.report?.formats?.length) p.formats = dialogs.report.formats as Format[];
    setPrefs(p);
    void call<Defaults>("report_defaults")
      .then((d) => {
        setDefaults(d);
        setFileName(d.file_name);
        setOutDir("");
        setDocTitle("");
        let examiner = "";
        try {
          examiner = localStorage.getItem("spni.examiner") ?? "";
        } catch {
          /* ignore */
        }
        setCaseInfo({ ...d.case, examiner: d.case.examiner || examiner, investigator: d.case.investigator || "" });
        setDevices(d.devices.map((x) => x.id));
        setKinds([...ALL_KINDS]);
      })
      .catch((e) => {
        toast.error(errorText(e));
        closeDialog("report");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const kindCounts = useMemo(() => {
    const out: Partial<Record<Kind, number>> = {};
    for (const d of defaults?.devices ?? []) {
      if (!devices.includes(d.id)) continue;
      for (const k of ALL_KINDS) out[k] = (out[k] ?? 0) + (d.counts[k] ?? 0);
    }
    return out;
  }, [defaults, devices]);
  const totalRecords = kinds.reduce((a, k) => a + (kindCounts[k] ?? 0), 0);
  const multi = devices.length > 1;

  const errors = useMemo(() => {
    const e: Partial<Record<StepId, string>> = {};
    if (!fileName.trim()) e.general = t("rw.err.name");
    else if (!prefs.formats.length) e.general = t("rw.err.formats");
    if (!devices.length) e.dataset = t("rw.err.devices");
    if (password && password !== confirm) e.security = t("rw.mismatch");
    return e;
  }, [fileName, prefs.formats, devices, password, confirm, t]);

  const go = (i: number) => {
    setStep(i);
    setVisited((v) => new Set(v).add(i));
  };

  const generate = useCallback(async () => {
    const firstError = STEPS.findIndex((s) => errors[s.id]);
    if (firstError >= 0) {
      go(firstError);
      toast.warning(errors[STEPS[firstError].id]);
      return;
    }
    savePrefs(prefs);
    try {
      if (caseInfo.examiner) localStorage.setItem("spni.examiner", caseInfo.examiner);
    } catch {
      /* ignore */
    }
    setPhase("working");
    setProgress({ step: "chart", progress: 0.02 });
    const unsub = subscribe((name, payload) => {
      if (name === "report.progress") setProgress(payload as { step: string; progress: number });
    });
    try {
      let chart: string | null = null;
      if (prefs.sections.includes("network")) {
        try {
          chart = await renderNetworkPng(devices);
        } catch {
          chart = null; // the report is still useful without the picture
        }
      }
      const spec = {
        file_name: fileName.trim(),
        formats: prefs.formats,
        out_dir: outDir,
        title: docTitle.trim(),
        case: caseInfo,
        extractions: devices,
        kinds,
        sections: prefs.sections.filter((s) => s !== "cross_device" || multi),
        date_from: range === "custom" && from ? new Date(from + "T00:00:00").getTime() : null,
        date_to: range === "custom" && to ? new Date(to + "T23:59:59").getTime() : null,
        top_n: prefs.top_n,
        pdf_password: password,
        classification: prefs.classification,
        hash_file: prefs.hash_file,
        lang: prefs.lang,
        buddhist_year: prefs.buddhist_year,
        newest_first: prefs.newest_first,
        orientation: prefs.orientation,
        max_rows: prefs.max_rows,
        thumbnails: prefs.thumbnails,
      };
      const res = await call<ReportResult>("generate_report", spec, chart);
      setResult(res);
      setPhase("done");
      toast.success(t("rw.done"));
    } catch (e) {
      toast.error(errorText(e));
      setPhase("edit");
    } finally {
      unsub();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [errors, prefs, caseInfo, devices, fileName, outDir, docTitle, kinds, range, from, to, password, multi, t, errorText]);

  const browse = async () => {
    try {
      const dir = await call<string | null>("choose_folder", outDir || defaults?.out_dir || "");
      if (dir) setOutDir(dir);
      else if (!info || info.platform !== "win32") toast(t("rw.noPicker"));
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  const close = () => phase !== "working" && closeDialog("report");
  const current = STEPS[step].id;

  /* ── step bodies ──────────────────────────────────────────────── */
  const general = (
    <div className="flex flex-col gap-5">
      <Field label={t("rw.fileName")}>
        <Input value={fileName} onChange={(e) => setFileName(e.target.value)} icon={<FileBadge className="size-4" />} data-testid="rw-filename" />
      </Field>
      <div>
        <SectionTitle>{t("rw.formats")}</SectionTitle>
        <div className="grid grid-cols-5 gap-2.5">
          {FORMATS.map((f) => {
            const on = prefs.formats.includes(f);
            const m = FORMAT_META[f];
            return (
              <button
                key={f}
                type="button"
                data-testid={`rw-fmt-${f}`}
                onClick={() => setPref("formats", on ? prefs.formats.filter((x) => x !== f) : [...prefs.formats, f])}
                className={clsx(
                  "focus-ring group relative flex flex-col items-start gap-2 rounded-2xl border p-3 text-left transition",
                  on ? "border-navy-600 bg-navy-50/60 shadow-[0_8px_20px_-14px_rgba(18,40,90,0.8)] dark:border-gold-400 dark:bg-gold-400/10" : "border-line bg-surface hover:border-line-strong hover:bg-surface-2",
                )}
              >
                <span className={clsx("grid size-10 place-items-center rounded-xl bg-gradient-to-br text-white shadow", m.tone)}>{m.icon}</span>
                <span className="text-[14px] font-bold text-ink">{f === "zip" ? t("rw.fmt.zipName") : m.name}</span>
                <span className="text-[11.5px] leading-snug text-muted">{t(`rw.fmt.${f}`)}</span>
                <span className={clsx("absolute top-2.5 right-2.5 grid size-5 place-items-center rounded-full border transition", on ? "border-navy-700 bg-navy-700 text-white dark:border-gold-400 dark:bg-gold-400 dark:text-navy-950" : "border-line-strong")}>
                  {on && <Check className="size-3.5" strokeWidth={3} />}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <Field label={t("rw.outDir")}>
        <div className="flex gap-2">
          <div className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-xl border border-line-strong bg-surface-2 px-3">
            <FolderOpen className="size-4 shrink-0 text-gold-500" />
            <span className="truncate font-mono text-[12.5px] text-ink-2" title={outDir || defaults?.out_dir}>
              {outDir || defaults?.out_dir}
            </span>
          </div>
          <Button variant="outline" onClick={() => void browse()}>
            {t("rw.browse")}
          </Button>
          {outDir && (
            <Button variant="ghost" icon={<RotateCcw className="size-4" />} onClick={() => setOutDir("")}>
              {t("rw.defaultDir")}
            </Button>
          )}
        </div>
      </Field>
      <Field label={t("rw.docTitle")}>
        <Input value={docTitle} onChange={(e) => setDocTitle(e.target.value)} placeholder={prefs.lang === "th" ? "รายงานผลการตรวจพิสูจน์ข้อมูลโทรศัพท์มือถือ" : "Mobile Device Forensic Report"} />
      </Field>
    </div>
  );

  const caseStep = (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-3 rounded-2xl border border-gold-200 bg-gold-50/70 px-4 py-3 text-[13px] text-gold-800 dark:border-gold-500/30 dark:bg-gold-500/10 dark:text-gold-200">
        <Info className="mt-0.5 size-4 shrink-0" />
        {t("rw.caseHint")}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3.5">
        {CASE_KEYS.map((k) => (
          <div key={k} className={k === "note" ? "col-span-2" : ""}>
            <Field label={t(`rw.f.${k}`)}>
              <Input value={caseInfo[k] ?? ""} onChange={(e) => setCaseInfo((c) => ({ ...c, [k]: e.target.value }))} data-testid={`rw-case-${k}`} />
            </Field>
          </div>
        ))}
      </div>
    </div>
  );

  const dataset = (
    <div className="flex flex-col gap-5">
      <div>
        <SectionTitle>{t("rw.devices")}</SectionTitle>
        <div className="grid grid-cols-3 gap-2.5">
          {defaults?.devices.map((d, i) => {
            const on = devices.includes(d.id);
            const total = Object.values(d.counts).reduce((a, b) => a + (b ?? 0), 0);
            const color = DEVICE_COLORS[i % DEVICE_COLORS.length];
            return (
              <button
                key={d.id}
                type="button"
                data-testid="rw-device"
                onClick={() => setDevices((v) => (on ? v.filter((x) => x !== d.id) : [...v, d.id]))}
                className={clsx("focus-ring relative flex items-center gap-3 rounded-2xl border p-3 text-left transition", on ? "border-navy-600 bg-navy-50/60 dark:border-gold-400 dark:bg-gold-400/10" : "border-line opacity-70 hover:opacity-100")}
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-xl text-white" style={{ background: color }}>
                  <DeviceIcon d={d} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] font-bold text-ink">{d.label}</span>
                  <span className="block truncate text-[12px] text-muted">
                    {d.number || d.serial} · {t("rw.records", { n: total.toLocaleString() })}
                  </span>
                </span>
                <span className={clsx("grid size-5 shrink-0 place-items-center rounded-md border", on ? "border-navy-700 bg-navy-700 text-white dark:border-gold-400 dark:bg-gold-400 dark:text-navy-950" : "border-line-strong")}>
                  {on && <Check className="size-3.5" strokeWidth={3} />}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <div>
        <SectionTitle
          right={
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" onClick={() => setKinds([...ALL_KINDS])}>
                {t("rw.all")}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setKinds([])}>
                {t("rw.none")}
              </Button>
            </div>
          }
        >
          {t("rw.kinds")}
        </SectionTitle>
        <div className="grid grid-cols-4 gap-2">
          {ALL_KINDS.map((k) => {
            const on = kinds.includes(k);
            const n = kindCounts[k] ?? 0;
            return (
              <button
                key={k}
                type="button"
                onClick={() => setKinds((v) => (on ? v.filter((x) => x !== k) : [...v, k]))}
                className={clsx(
                  "focus-ring flex h-10 items-center gap-2 rounded-xl border px-2.5 text-left text-[13px] font-semibold transition",
                  on ? "border-navy-600 bg-navy-700 text-white dark:border-gold-400 dark:bg-gold-400 dark:text-navy-950" : "border-line bg-surface text-ink-2 hover:bg-surface-2",
                  !n && !on && "opacity-55",
                )}
              >
                <span className="shrink-0 [&>svg]:size-4">{TAB_ICONS[k]}</span>
                <span className="min-w-0 flex-1 truncate">{t(`tab.${k}`)}</span>
                <span className={clsx("tabular text-[11.5px]", on ? "opacity-80" : "text-faint")}>{n.toLocaleString()}</span>
              </button>
            );
          })}
        </div>
      </div>
      <div>
        <SectionTitle>{t("rw.sections")}</SectionTitle>
        <div className="grid grid-cols-2 gap-2">
          {SECTIONS.map((s) => {
            const disabled = (s === "cross_device" && !multi) || (s === "bookmarks" && !defaults?.bookmarks) || (s === "photos" && !kinds.includes("photos"));
            const hint = s === "cross_device" && !multi ? t("rw.needTwo") : undefined;
            return (
              <ToggleRow
                key={s}
                icon={SECTION_ICON[s]}
                label={t(`rw.sec.${s}`, { n: defaults?.bookmarks ?? 0 })}
                hint={hint}
                checked={prefs.sections.includes(s)}
                disabled={disabled}
                onChange={(v) => setPref("sections", v ? [...prefs.sections, s] : prefs.sections.filter((x) => x !== s))}
                right={
                  s === "top_contacts" && prefs.sections.includes("top_contacts") ? (
                    <select
                      value={prefs.top_n}
                      onChange={(e) => setPref("top_n", Number(e.target.value))}
                      className="h-7 rounded-lg border border-line bg-surface px-1.5 text-[12px] text-ink"
                    >
                      {[10, 20, 30, 50].map((n) => (
                        <option key={n} value={n}>
                          Top {n}
                        </option>
                      ))}
                    </select>
                  ) : undefined
                }
              />
            );
          })}
        </div>
      </div>
      <div>
        <SectionTitle>{t("rw.range")}</SectionTitle>
        <div className="flex flex-wrap items-center gap-3">
          <Seg value={range} onChange={setRange} options={[{ v: "all", label: t("rw.range.all") }, { v: "custom", label: t("rw.range.custom") }]} />
          {range === "custom" && (
            <div className="flex items-center gap-2 text-[13px] text-muted">
              <CalendarRange className="size-4" />
              {t("rw.from")}
              <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-9 rounded-lg border border-line-strong bg-surface px-2 text-ink" />
              {t("rw.to")}
              <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-9 rounded-lg border border-line-strong bg-surface px-2 text-ink" />
            </div>
          )}
        </div>
      </div>
    </div>
  );

  const security = (
    <div className="flex flex-col gap-5">
      <div>
        <SectionTitle>{t("rw.password")}</SectionTitle>
        <div className="grid grid-cols-2 gap-3">
          <Input
            type={showPw ? "text" : "password"}
            icon={<KeyRound className="size-4" />}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            data-testid="rw-password"
          />
          <div className="flex gap-2">
            <Input className="flex-1" type={showPw ? "text" : "password"} value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder={t("rw.confirm")} autoComplete="new-password" data-testid="rw-confirm" />
            <Button variant="ghost" onClick={() => setShowPw((v) => !v)} aria-label="show">
              {showPw ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </Button>
          </div>
        </div>
        <p className={clsx("mt-1.5 text-[12px]", password && password !== confirm ? "font-semibold text-rose-600" : "text-muted")}>
          {password && password !== confirm ? t("rw.mismatch") : t("rw.passwordHint")}
        </p>
      </div>
      <div>
        <SectionTitle>{t("rw.cls")}</SectionTitle>
        <div className="grid grid-cols-5 gap-2.5">
          {CLASSIFICATIONS.map((c) => {
            const on = prefs.classification === c;
            return (
              <button
                key={c || "none"}
                type="button"
                data-testid={`rw-cls-${c || "none"}`}
                onClick={() => setPref("classification", c)}
                className={clsx(
                  "focus-ring flex h-[74px] flex-col items-center justify-center gap-1.5 rounded-2xl border transition",
                  on ? (c ? "border-rose-500 bg-rose-50 ring-2 ring-rose-200 dark:bg-rose-500/10 dark:ring-rose-500/30" : "border-navy-600 bg-navy-50/60 ring-2 ring-navy-100 dark:border-gold-400 dark:bg-gold-400/10 dark:ring-gold-400/20") : "border-line bg-surface hover:bg-surface-2",
                )}
              >
                {c ? <Stamp text={c} /> : <span className="text-[13px] font-semibold text-muted">{t("rw.cls.none")}</span>}
              </button>
            );
          })}
        </div>
        <p className="mt-1.5 text-[12px] text-muted">{t("rw.clsHint")}</p>
      </div>
      <ToggleRow icon={<Hash className="size-4" />} label={t("rw.hashFile")} checked={prefs.hash_file} onChange={(v) => setPref("hash_file", v)} />
      <div className="flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-[13px] text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">
        <ShieldCheck className="mt-0.5 size-4 shrink-0" />
        {t("rw.auditNote")}
      </div>
    </div>
  );

  const Page = ({ portrait }: { portrait: boolean }) => (
    <span className={clsx("inline-block rounded-[3px] border-2 border-current", portrait ? "h-4 w-3" : "h-3 w-4")} />
  );
  const format = (
    <div className="grid grid-cols-2 gap-x-6 gap-y-5">
      <Field label={t("rw.lang")}>
        <Seg value={prefs.lang} onChange={(v) => setPref("lang", v)} options={[{ v: "th", label: <><Languages className="size-4" />ไทย</> }, { v: "en", label: "English" }]} />
      </Field>
      <Field label={t("rw.year")}>
        <Seg value={prefs.buddhist_year} disabled={prefs.lang === "en"} onChange={(v) => setPref("buddhist_year", v)} options={[{ v: true, label: t("rw.year.be") }, { v: false, label: t("rw.year.ad") }]} />
      </Field>
      <Field label={t("rw.order")}>
        <Seg value={prefs.newest_first} onChange={(v) => setPref("newest_first", v)} options={[{ v: true, label: t("rw.order.new") }, { v: false, label: t("rw.order.old") }]} />
      </Field>
      <Field label={t("rw.orient")}>
        <Seg
          value={prefs.orientation}
          onChange={(v) => setPref("orientation", v)}
          options={[
            { v: "landscape", label: <><Page portrait={false} />{t("rw.orient.landscape")}</> },
            { v: "portrait", label: <><Page portrait />{t("rw.orient.portrait")}</> },
          ]}
        />
      </Field>
      <div className="col-span-2">
        <Field label={t("rw.maxRows")}>
          <Seg value={prefs.max_rows} onChange={(v) => setPref("max_rows", v)} options={MAX_ROWS.map((n) => ({ v: n, label: n >= 50000 ? t("rw.unlimited") : n.toLocaleString() }))} />
        </Field>
      </div>
      <div className="col-span-2">
        <ToggleRow icon={<Image className="size-4" />} label={t("rw.thumbs")} checked={prefs.thumbnails} onChange={(v) => setPref("thumbnails", v)} />
      </div>
    </div>
  );

  const SumCard = ({ icon, title, to: target, children }: { icon: ReactNode; title: string; to: number; children: ReactNode }) => (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="grid size-7 place-items-center rounded-lg bg-navy-50 text-navy-700 dark:bg-navy-800 dark:text-gold-300">{icon}</span>
        <span className="flex-1 text-[13.5px] font-bold text-ink">{title}</span>
        <button className="text-[12px] font-semibold text-navy-600 hover:underline dark:text-gold-300" onClick={() => go(target)}>
          {t("rw.edit")}
        </button>
      </div>
      <div className="space-y-1 text-[13px] text-ink-2">{children}</div>
    </div>
  );
  const summary = (
    <div className="grid grid-cols-2 gap-3">
      <SumCard icon={<FileBadge className="size-4" />} title={t("rw.sum.file")} to={0}>
        <div className="font-semibold break-all text-ink">{fileName}</div>
        <div className="flex flex-wrap gap-1">
          {prefs.formats.map((f) => (
            <Badge key={f} tone="navy">
              {f === "zip" ? "ZIP" : FORMAT_META[f].name}
            </Badge>
          ))}
        </div>
        <div className="truncate font-mono text-[11.5px] text-muted">{outDir || defaults?.out_dir}</div>
      </SumCard>
      <SumCard icon={<Briefcase className="size-4" />} title={t("rw.sum.case")} to={1}>
        <div className="font-semibold text-ink">{[caseInfo.case_no, caseInfo.title].filter(Boolean).join(" · ") || "—"}</div>
        <div>
          {t("rw.f.examiner")}: {caseInfo.examiner || "—"}
        </div>
        <div>
          {t("rw.f.evidence_no")}: {caseInfo.evidence_no || "—"}
        </div>
      </SumCard>
      <SumCard icon={<Database className="size-4" />} title={t("rw.sum.data")} to={2}>
        <div className="font-semibold text-ink">{t("rw.sum.devices", { n: devices.length, k: kinds.length, r: totalRecords.toLocaleString() })}</div>
        <div>{range === "all" || (!from && !to) ? t("rw.range.all") : `${from || "…"} – ${to || "…"}`}</div>
        <div className="flex flex-wrap gap-1">
          {prefs.sections
            .filter((s) => s !== "cross_device" || multi)
            .map((s) => (
              <span key={s} className="inline-flex items-center gap-1 rounded-md bg-surface-3 px-1.5 py-0.5 text-[11.5px] text-ink-2 [&>svg]:size-3">
                {SECTION_ICON[s]}
                {t(`rw.sec.${s}`, { n: defaults?.bookmarks ?? 0 })}
              </span>
            ))}
        </div>
      </SumCard>
      <SumCard icon={<ShieldCheck className="size-4" />} title={t("rw.sum.security")} to={3}>
        <div className="flex items-center gap-2">
          <KeyRound className="size-4 text-muted" />
          {password ? t("rw.pw.on") : t("rw.pw.off")}
        </div>
        <div className="flex items-center gap-2">{prefs.classification ? <Stamp text={prefs.classification} /> : t("rw.cls.none")}</div>
      </SumCard>
      <div className="col-span-2">
        <SumCard icon={<ListOrdered className="size-4" />} title={t("rw.sum.format")} to={4}>
          {[
            prefs.lang === "th" ? "ไทย" : "English",
            prefs.lang === "th" ? (prefs.buddhist_year ? t("rw.year.be") : t("rw.year.ad")) : t("rw.year.ad"),
            prefs.newest_first ? t("rw.order.new") : t("rw.order.old"),
            t(`rw.orient.${prefs.orientation}`),
            `${t("rw.maxRows")}: ${prefs.max_rows >= 50000 ? t("rw.unlimited") : prefs.max_rows.toLocaleString()}`,
          ].join(" · ")}
        </SumCard>
      </div>
    </div>
  );

  const bodies: Record<StepId, ReactNode> = { general, case: caseStep, dataset, security, format, summary };

  /* ── working / done panes ─────────────────────────────────────── */
  const working = (
    <div className="flex flex-1 flex-col items-center justify-center gap-5 px-16 text-center" data-testid="rw-working">
      <div className="relative grid size-24 place-items-center">
        <span className="absolute inset-0 animate-ping rounded-full bg-gold-300/30" />
        <span className="relative grid size-20 place-items-center rounded-full bg-gradient-to-br from-navy-600 to-navy-900 text-gold-300 shadow-xl">
          <FileBadge className="size-9" />
        </span>
      </div>
      <div>
        <div className="font-display text-[22px] font-semibold text-ink">{t("rw.working")}</div>
        <div className="mt-1 flex items-center justify-center gap-2 text-[14px] text-muted">
          <Spinner className="size-4" />
          {t(`rw.p.${progress.step}`)}
        </div>
      </div>
      <ProgressBar value={progress.progress} tone="gold" className="h-2 w-full max-w-md" />
    </div>
  );

  const done = result && (
    <div className="flex flex-1 flex-col overflow-auto px-8 py-6" data-testid="rw-done">
      <div className="mb-5 flex items-center gap-4">
        <span className="grid size-14 place-items-center rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-white shadow-lg">
          <CircleCheckBig className="size-7" />
        </span>
        <div>
          <div className="font-display text-[22px] font-semibold text-ink">{t("rw.done")}</div>
          <div className="text-[13.5px] text-muted">{t("rw.doneSub", { id: result.report_id })}</div>
        </div>
      </div>
      <div className="flex flex-col gap-2.5">
        {result.files.map((f) => (
          <div key={f.path} className="flex items-center gap-4 rounded-2xl border border-line bg-surface px-4 py-3" data-selectable>
            <span className={clsx("grid size-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br text-white", FORMAT_META[f.format].tone)}>{FORMAT_META[f.format].icon}</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-[14.5px] font-bold text-ink">{f.name}</span>
                <Badge tone="slate">{fmtSize(f.size)}</Badge>
              </div>
              <div className="mt-0.5 flex items-center gap-1 font-mono text-[11.5px] text-muted">
                <span className="font-sans font-semibold text-ink-2">SHA-256</span>
                <span className="truncate">{f.sha256}</span>
                <CopyButton value={f.sha256} className="size-6" />
              </div>
            </div>
            <Button size="sm" variant="soft" onClick={() => void call("open_file", f.path).catch((e) => toast.error(errorText(e)))}>
              {t("rw.openFile")}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <Modal open={open} onClose={close} width={1120} dismissable={phase !== "working"} className="h-[min(760px,calc(100vh-48px))]">
      <div className="flex h-full min-h-0">
        {/* step rail */}
        <aside className="titlebar-pattern flex w-[250px] shrink-0 flex-col px-4 pt-6 pb-5 text-white">
          <div className="mb-6 flex items-center gap-3 px-1">
            <span className="grid size-11 place-items-center rounded-2xl bg-gradient-to-br from-gold-300 to-gold-500 text-navy-950 shadow-lg">
              <FileBadge className="size-5" />
            </span>
            <div className="min-w-0">
              <div className="font-display text-[17px] leading-tight font-semibold">{t("rw.title")}</div>
              <div className="truncate text-[12px] text-white/55">{state.case?.case_no || state.case?.title}</div>
            </div>
          </div>
          <nav className="flex flex-col gap-1">
            {STEPS.map((s, i) => {
              const active = phase === "edit" && i === step;
              const err = errors[s.id] && visited.has(i);
              const ok = phase === "done" || (visited.has(i) && !errors[s.id] && i !== step);
              return (
                <button
                  key={s.id}
                  disabled={phase !== "edit"}
                  onClick={() => go(i)}
                  data-testid={`rw-step-${s.id}`}
                  className={clsx(
                    "group relative flex items-center gap-3 rounded-xl px-2.5 py-2.5 text-left transition",
                    active ? "bg-white/12 ring-1 ring-white/15" : "hover:bg-white/6",
                    phase !== "edit" && "opacity-60",
                  )}
                >
                  {active && <span className="absolute top-2 bottom-2 left-0 w-1 rounded-full bg-gold-400" />}
                  <span
                    className={clsx(
                      "grid size-9 shrink-0 place-items-center rounded-xl transition",
                      active ? "bg-gold-400 text-navy-950" : err ? "bg-rose-500/90 text-white" : ok ? "bg-emerald-500/85 text-white" : "bg-white/10 text-white/70",
                    )}
                  >
                    {ok && !active ? <Check className="size-4" strokeWidth={3} /> : s.icon}
                  </span>
                  <span className="min-w-0">
                    <span className={clsx("block text-[13.5px] font-semibold", active ? "text-white" : "text-white/80")}>
                      {i + 1}. {t(`rw.s.${s.id}`)}
                    </span>
                    <span className="block truncate text-[11.5px] text-white/45">{t(`rw.s.${s.id}.sub`)}</span>
                  </span>
                </button>
              );
            })}
          </nav>
          <div className="mt-auto rounded-xl bg-white/6 px-3 py-2.5 text-[11.5px] leading-relaxed text-white/55">
            <ShieldCheck className="mb-1 size-4 text-gold-300" />
            {t("rw.sub")}
          </div>
        </aside>

        {/* content */}
        <section className="flex min-w-0 flex-1 flex-col">
          {phase === "edit" && (
            <>
              <header className="relative flex items-center gap-3 border-b border-line px-7 pt-5 pb-4">
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] font-semibold tracking-wide text-gold-600 dark:text-gold-300">{t("rw.step", { n: step + 1, total: STEPS.length })}</div>
                  <h2 className="font-display text-[21px] leading-tight font-semibold text-ink">{t(`rw.s.${current}`)}</h2>
                </div>
                <span className="absolute bottom-[-1px] left-7 h-[3px] w-14 rounded-full bg-gold-400" />
              </header>
              <div className="min-h-0 flex-1 overflow-auto px-7 py-5">{defaults ? bodies[current] : <div className="skeleton h-48 rounded-2xl" />}</div>
            </>
          )}
          {phase === "working" && working}
          {phase === "done" && done}

          <footer className="flex items-center gap-2 border-t border-line bg-surface-2 px-6 py-3.5">
            {phase === "edit" ? (
              <>
                <div className="flex-1 truncate text-[12.5px] text-rose-600">{errors[current]}</div>
                <Button variant="ghost" onClick={close}>
                  {t("common.cancel")}
                </Button>
                <Button variant="outline" icon={<ArrowLeft className="size-4" />} disabled={step === 0} onClick={() => go(step - 1)} data-testid="rw-prev">
                  {t("rw.prev")}
                </Button>
                {step < STEPS.length - 1 && (
                  <Button variant="primary" onClick={() => go(step + 1)} data-testid="rw-next">
                    {t("rw.next")}
                    <ArrowRight className="size-4" />
                  </Button>
                )}
                <Button variant="gold" icon={<FileBadge className="size-4" />} onClick={() => void generate()} disabled={!defaults} data-testid="rw-generate">
                  {t("rw.generate")}
                </Button>
              </>
            ) : phase === "done" && result ? (
              <>
                <div className="flex-1" />
                <Button variant="ghost" icon={<RotateCcw className="size-4" />} onClick={() => (setPhase("edit"), setResult(null))}>
                  {t("rw.again")}
                </Button>
                <Button variant="outline" icon={<FolderOpen className="size-4" />} onClick={() => void call("reveal", result.files[0]?.path ?? result.out_dir).catch((e) => toast.error(errorText(e)))}>
                  {t("rw.openFolder")}
                </Button>
                <Button variant="primary" onClick={close} data-testid="rw-close">
                  {t("rw.close")}
                </Button>
              </>
            ) : (
              <div className="flex-1 text-center text-[12.5px] text-muted">{t("rw.p.wait")}</div>
            )}
          </footer>
        </section>
      </div>
    </Modal>
  );
}
