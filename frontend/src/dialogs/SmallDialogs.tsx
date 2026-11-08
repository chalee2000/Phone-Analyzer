import clsx from "clsx";
import { ChevronRight, FolderOpen, FolderPlus, History, Info, Pencil, Phone, ScrollText, Smartphone } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AndroidIcon, IphoneIcon, LogoMark } from "../components/icons";
import { Badge, Button, Field, Input, Modal, ModalHeader } from "../components/ui";
import { call } from "../lib/bridge";
import { fmtIso } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import type { CaseMeta, ExtractionInfo } from "../lib/types";

/* ── Cases ─────────────────────────────────────────────────────────── */
export function CaseDialog() {
  const { t } = useI18n();
  const { dialogs, closeDialog, state, refresh, resetRecords, errorText } = useStore();
  const open = dialogs.cases;
  const [mode, setMode] = useState<"new" | "open">("new");
  const [cases, setCases] = useState<CaseMeta[]>([]);
  const [form, setForm] = useState({ case_no: "", title: "", investigator: "", unit: "", note: "" });
  useEffect(() => {
    if (!open) return;
    void call<CaseMeta[]>("list_cases").then((c) => {
      setCases(c);
      setMode(c.length && !state.case ? "open" : "new");
    });
    try {
      setForm((f) => ({ ...f, investigator: localStorage.getItem("spni.examiner") ?? "", unit: localStorage.getItem("spni.unit") ?? "" }));
    } catch {
      /* ignore */
    }
  }, [open, state.case]);
  const create = async () => {
    if (!form.case_no && !form.title) {
      toast.warning(t("case.required"));
      return;
    }
    try {
      await call("create_case", form);
      try {
        localStorage.setItem("spni.unit", form.unit);
      } catch {
        /* ignore */
      }
      resetRecords();
      await refresh();
      toast.success(t("case.created"));
      setForm({ case_no: "", title: "", investigator: form.investigator, unit: form.unit, note: "" });
      closeDialog("cases");
    } catch (e) {
      toast.error(errorText(e));
    }
  };
  const openCase = async (id: string) => {
    try {
      await call("open_case", id);
      resetRecords();
      await refresh();
      toast.success(t("case.opened"));
      closeDialog("cases");
    } catch (e) {
      toast.error(errorText(e));
    }
  };
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <Modal open={open} onClose={() => closeDialog("cases")} width={760}>
      <ModalHeader icon={<FolderOpen className="size-5" />} title={t("case.title")} sub={state.case ? `${t("case.current")}: ${state.case.case_no || state.case.title}` : t("case.noCase")} onClose={() => closeDialog("cases")} />
      <div className="flex gap-1 px-6 pt-4">
        {(["new", "open"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={clsx("flex h-9 items-center gap-2 rounded-xl px-4 text-[13.5px] font-semibold", mode === m ? "bg-navy-800 text-white dark:bg-gold-400 dark:text-navy-950" : "text-muted hover:bg-surface-2")}
          >
            {m === "new" ? <FolderPlus className="size-4" /> : <FolderOpen className="size-4" />}
            {m === "new" ? t("case.new") : `${t("case.open")} (${cases.length})`}
          </button>
        ))}
      </div>
      {mode === "new" ? (
        <div className="grid grid-cols-2 gap-4 px-6 py-5">
          <Field label={t("case.no")}>
            <Input value={form.case_no} onChange={set("case_no")} placeholder="123/2569" autoFocus data-testid="case-no" />
          </Field>
          <Field label={t("case.name")}>
            <Input value={form.title} onChange={set("title")} />
          </Field>
          <Field label={t("case.investigator")}>
            <Input value={form.investigator} onChange={set("investigator")} />
          </Field>
          <Field label={t("case.unit")}>
            <Input value={form.unit} onChange={set("unit")} />
          </Field>
          <div className="col-span-2">
            <Field label={t("case.note")}>
              <Input value={form.note} onChange={set("note")} />
            </Field>
          </div>
          <div className="col-span-2 flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => closeDialog("cases")}>
              {t("common.cancel")}
            </Button>
            <Button variant="primary" icon={<FolderPlus className="size-4" />} onClick={() => void create()} data-testid="case-create">
              {t("case.create")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="max-h-[440px] overflow-auto px-4 py-4">
          {cases.length === 0 && <p className="py-10 text-center text-muted">{t("case.none")}</p>}
          {cases.map((c) => (
            <button key={c.id} onClick={() => void openCase(c.id)} className="group flex w-full items-center gap-4 rounded-2xl px-3 py-3 text-left hover:bg-surface-2">
              <span className="grid size-11 place-items-center rounded-xl bg-gold-50 text-gold-600 dark:bg-gold-500/15 dark:text-gold-300">
                <FolderOpen className="size-5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2 text-[14.5px] font-semibold text-ink">
                  {c.case_no || c.title}
                  {state.case?.id === c.id && <Badge tone="green">{t("case.current")}</Badge>}
                </span>
                <span className="block truncate text-[12.5px] text-muted">
                  {[c.title !== c.case_no ? c.title : "", c.investigator, c.unit, fmtIso(c.created)].filter(Boolean).join(" · ")}
                </span>
              </span>
              <Badge tone="navy">{t("case.extractions", { n: c.extraction_count })}</Badge>
              <ChevronRight className="size-4 text-faint group-hover:text-ink" />
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}

/* ── Device history ────────────────────────────────────────────────── */
export function HistoryDialog() {
  const { t } = useI18n();
  const { dialogs, closeDialog, refresh, resetRecords, setTab, errorText } = useStore();
  const open = dialogs.history;
  const [items, setItems] = useState<ExtractionInfo[] | null>(null);
  useEffect(() => {
    if (open) void call<ExtractionInfo[]>("device_history").then(setItems);
  }, [open]);
  const pick = async (e: ExtractionInfo) => {
    try {
      await call("open_extraction", e.case_id, e.id);
      resetRecords();
      setTab("device");
      await refresh();
      closeDialog("history");
    } catch (err) {
      toast.error(errorText(err));
    }
  };
  return (
    <Modal open={open} onClose={() => closeDialog("history")} width={860}>
      <ModalHeader icon={<History className="size-5" />} title={t("hist.title")} sub={t("hist.sub")} onClose={() => closeDialog("history")} />
      <div className="max-h-[520px] overflow-auto px-4 py-3">
        {items && items.length === 0 && <p className="py-12 text-center text-muted">{t("hist.empty")}</p>}
        {items?.map((e) => {
          const total = Object.values(e.summary || {}).reduce((a, b) => a + (b ?? 0), 0);
          return (
            <button key={`${e.case_id}/${e.id}`} onClick={() => void pick(e)} className="group flex w-full items-center gap-4 rounded-2xl px-3 py-3 text-left hover:bg-surface-2" data-testid="history-item">
              <span className={clsx("grid size-11 place-items-center rounded-xl", e.platform === "ios" ? "bg-violet-50 text-violet-600 dark:bg-violet-500/15" : "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15")}>
                {e.platform === "ios" ? <IphoneIcon className="size-5" /> : <AndroidIcon className="size-5" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2 text-[14.5px] font-semibold text-ink">
                  {e.device?.brand && e.platform === "android" ? `${e.device.brand} ` : ""}
                  {e.model}
                  {e.method === "demo" && <Badge tone="gold">{t("conn.demo")}</Badge>}
                  {e.status !== "completed" && <Badge tone="amber">{e.status}</Badge>}
                </span>
                <span className="block truncate text-[12.5px] text-muted">
                  <span className="font-mono">{e.serial}</span> · {t("status.case")} {e.case_no || e.case_title} · {fmtIso(e.started)}
                </span>
              </span>
              <span className="tabular text-right text-[12.5px] text-muted">
                <b className="block font-display text-[16px] text-ink">{total.toLocaleString()}</b>
                {t("pg.items", { n: "" }).trim()}
              </span>
              <ChevronRight className="size-4 text-faint group-hover:text-ink" />
            </button>
          );
        })}
        {!items && <div className="skeleton m-3 h-16 rounded-2xl" />}
      </div>
    </Modal>
  );
}

/* ── Device number ─────────────────────────────────────────────────── */
export function NumberDialog() {
  const { t } = useI18n();
  const { dialogs, closeDialog, state, refresh, errorText } = useStore();
  const open = dialogs.number;
  const [value, setValue] = useState("");
  useEffect(() => {
    if (open) setValue(state.device?.info.phone_number ?? "");
  }, [open, state.device]);
  const save = async () => {
    try {
      await call("set_device_number", value);
      await refresh();
      toast.success(t("num.saved"));
      closeDialog("number");
    } catch (e) {
      toast.error(errorText(e));
    }
  };
  return (
    <Modal open={open} onClose={() => closeDialog("number")} width={480}>
      <ModalHeader icon={<Pencil className="size-5" />} title={t("num.title")} sub={t("num.sub")} onClose={() => closeDialog("number")} />
      <div className="px-6 py-5">
        <Input icon={<Phone className="size-4" />} value={value} onChange={(e) => setValue(e.target.value)} placeholder="08x-xxx-xxxx" autoFocus onKeyDown={(e) => e.key === "Enter" && void save()} data-testid="number-input" />
      </div>
      <div className="flex justify-end gap-2 border-t border-line bg-surface-2 px-6 py-4">
        <Button variant="ghost" onClick={() => closeDialog("number")}>
          {t("common.cancel")}
        </Button>
        <Button variant="primary" onClick={() => void save()}>
          {t("case.save")}
        </Button>
      </div>
    </Modal>
  );
}

/* ── Device picker ─────────────────────────────────────────────────── */
export function PickerDialog() {
  const { t } = useI18n();
  const { dialogs, closeDialog, connect } = useStore();
  const list = dialogs.picker;
  return (
    <Modal open={!!list} onClose={() => closeDialog("picker")} width={560}>
      <ModalHeader icon={<Smartphone className="size-5" />} title={t("pick.title")} sub={t("pick.sub")} onClose={() => closeDialog("picker")} />
      <div className="px-4 py-3">
        {list?.map((d) => (
          <button
            key={d.id}
            onClick={async () => {
              closeDialog("picker");
              await connect(d.id);
            }}
            className="group flex w-full items-center gap-4 rounded-2xl px-3 py-3 text-left hover:bg-surface-2"
          >
            <span className="grid size-11 place-items-center rounded-xl bg-surface-3">{d.platform === "ios" ? <IphoneIcon className="size-5" /> : <AndroidIcon className="size-5 text-[#3DDC84]" />}</span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2 text-[14.5px] font-semibold text-ink">
                {d.brand} {d.model} {d.demo && <Badge tone="gold">{t("conn.demo")}</Badge>}
              </span>
              <span className="block truncate font-mono text-[12px] text-muted">{d.serial}</span>
            </span>
            <ChevronRight className="size-4 text-faint group-hover:text-ink" />
          </button>
        ))}
      </div>
    </Modal>
  );
}

/* ── Audit log ─────────────────────────────────────────────────────── */
export function AuditDialog() {
  const { t } = useI18n();
  const { dialogs, closeDialog } = useStore();
  const open = dialogs.audit;
  const [rows, setRows] = useState<{ ts: string; action: string; detail: string }[]>([]);
  useEffect(() => {
    if (open) void call<typeof rows>("audit_log").then(setRows);
  }, [open]);
  return (
    <Modal open={open} onClose={() => closeDialog("audit")} width={1000}>
      <ModalHeader icon={<ScrollText className="size-5" />} title={t("audit.title")} sub={t("audit.sub")} onClose={() => closeDialog("audit")} />
      <div className="max-h-[560px] overflow-auto px-6 py-4" data-selectable>
        {rows.length === 0 && <p className="py-10 text-center text-muted">{t("empty.noData")}</p>}
        <table className="w-full text-[12.5px]">
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-line/70 align-top">
                <td className="tabular py-1.5 pr-4 whitespace-nowrap text-muted">{fmtIso(r.ts)}</td>
                <td className="py-1.5 pr-4 font-semibold whitespace-nowrap text-navy-600 dark:text-gold-300">{r.action}</td>
                <td className="py-1.5 font-mono break-all text-ink-2">{r.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}

/* ── About ─────────────────────────────────────────────────────────── */
export function AboutDialog() {
  const { t } = useI18n();
  const { dialogs, closeDialog, info } = useStore();
  return (
    <Modal open={dialogs.about} onClose={() => closeDialog("about")} width={540}>
      <div className="titlebar-pattern flex flex-col items-center px-8 pt-10 pb-8 text-center text-white">
        <LogoMark className="size-20" />
        <div className="mt-4 font-display text-[26px] font-semibold">
          <span className="gold-text">SPNI</span> Phone Analysis
        </div>
        <div className="tabular mt-1 text-white/60">v{info?.version}</div>
      </div>
      <div className="px-8 py-6 text-[14px] leading-relaxed text-ink-2">
        <div className="mb-2 flex items-center gap-2 font-semibold text-ink">
          <Info className="size-4" /> {t("about.title")}
        </div>
        {t("about.body")}
        <div className="mt-4 text-[12px] break-all text-faint">{info?.cases_root}</div>
      </div>
    </Modal>
  );
}
