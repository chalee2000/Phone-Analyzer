import { useVirtualizer } from "@tanstack/react-virtual";
import clsx from "clsx";
import { ChevronDown, Eye, EyeOff, FileSpreadsheet, FileUp, Folder, MessageSquareText, Network, Phone, PhoneCall, Sparkles, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { AnalysisEmpty, Panel } from "../components/AnalysisEmpty";
import { CommsMap, toMapPoints } from "../components/CommsMap";
import { Badge, Button, Spinner } from "../components/ui";
import { DEVICE_COLORS, fileToBase64, type CaseDevice, type CommRow, type ContactSummary, type GeoPoint } from "../lib/analysis";
import { call } from "../lib/bridge";
import { fmtDateTime, fmtDuration, fmtHours } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { Avatar, DIRECTION_STYLE } from "./CallsView";

interface CommData {
  devices: CaseDevice[];
  rows: CommRow[];
  geo: GeoPoint[];
  contacts: ContactSummary[];
}

type QueryId =
  | "everything" | "allCalls" | "today" | "week" | "night" | "missed" | "short" | "long" | "withLoc"
  | "allSms" | "smsUnknown" | "chats" | "top" | "unsaved" | "common";

const DAY = 86_400_000;

function nightOf(ts: number | null) {
  if (!ts) return false;
  const h = new Date(ts).getHours();
  return h >= 22 || h < 5;
}

export function CommsView() {
  const { state } = useStore();
  if (!state.case || !state.case.extraction_count) return <CommsEmpty />;
  return <Comms />;
}

function CommsEmpty() {
  const { t } = useI18n();
  const { refresh } = useStore();
  return (
    <div className="flex h-full flex-col gap-3">
      <AnalysisEmpty icon={<PhoneCall />} />
      <div className="card flex items-center justify-center gap-3 p-4">
        <span className="text-[13px] text-muted">{t("cm.cdrHint")}</span>
        <CdrButtons onDone={() => void refresh()} />
      </div>
    </div>
  );
}

function CdrButtons({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const { errorText } = useStore();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const open = () => input.current?.click();
    window.addEventListener("spni:cdr-import", open);
    return () => window.removeEventListener("spni:cdr-import", open);
  }, []);
  const done = (res: { target: string; counts: Record<string, number> }) => {
    const n = Object.values(res.counts).reduce((a, b) => a + b, 0);
    toast.success(t("cm.cdrImported", { target: res.target, n }));
    onDone();
  };
  return (
    <span className="flex gap-2">
      <input
        ref={input}
        type="file"
        accept=".csv,.txt,.xlsx"
        className="hidden"
        onChange={async (e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (!f) return;
          setBusy(true);
          try {
            done(await call("import_cdr", f.name, await fileToBase64(f)));
          } catch (err) {
            toast.error(errorText(err));
          } finally {
            setBusy(false);
          }
        }}
      />
      <Button size="sm" variant="primary" icon={<FileUp className="size-4" />} loading={busy} onClick={() => input.current?.click()} data-testid="cdr-import">
        {t("cm.importCdr")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        icon={<Sparkles className="size-4" />}
        onClick={async () => {
          setBusy(true);
          try {
            done(await call("import_demo_cdr"));
          } catch (err) {
            toast.error(errorText(err));
          } finally {
            setBusy(false);
          }
        }}
        data-testid="cdr-demo"
      >
        {t("cm.demoCdr")}
      </Button>
    </span>
  );
}

function Comms() {
  const { t, lang } = useI18n();
  const { state, errorText, refresh, setTab } = useStore();
  const [data, setData] = useState<CommData | null>(null);
  const [query, setQuery] = useState<QueryId>("everything");
  const [hiddenDevices, setHiddenDevices] = useState<Set<string>>(new Set());
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [focus, setFocus] = useState<string | null>(null);
  const [party, setParty] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({ calls: true, messages: true, contacts: true });

  const load = useCallback(async () => {
    try {
      setData(await call<CommData>("comm_analysis", {}));
    } catch (e) {
      toast.error(errorText(e));
    }
  }, [errorText]);
  useEffect(() => {
    void load();
  }, [load, state.case?.id, state.case?.extraction_count]);

  const colorOf = useCallback(
    (id: string) => {
      const d = data?.devices.find((x) => x.id === id);
      return DEVICE_COLORS[(d?.index ?? 0) % DEVICE_COLORS.length];
    },
    [data],
  );
  const devLabel = (id: string) => data?.devices.find((x) => x.id === id)?.label ?? id;

  const base = useMemo(() => (data?.rows ?? []).filter((r) => !hiddenDevices.has(r.device)), [data, hiddenDevices]);
  const contactsByKey = useMemo(() => new Map((data?.contacts ?? []).map((c) => [c.key, c])), [data]);
  const latest = useMemo(() => Math.max(0, ...base.map((r) => r.ts ?? 0)), [base]);

  const queries = useMemo(() => {
    const today = new Date(latest).toDateString();
    const top = new Set((data?.contacts ?? []).filter((c) => c.is_phone).slice(0, 20).map((c) => c.key));
    const common = new Set((data?.contacts ?? []).filter((c) => c.devices.length > 1).map((c) => c.key));
    const keyOf = (r: CommRow) => (r.kind === "chat" ? `${r.service}:${r.name}` : r.number || r.name);
    const f: Record<QueryId, (r: CommRow) => boolean> = {
      everything: () => true,
      allCalls: (r) => r.kind === "call",
      today: (r) => r.kind === "call" && !!r.ts && new Date(r.ts).toDateString() === today,
      week: (r) => r.kind === "call" && !!r.ts && r.ts >= latest - 7 * DAY,
      night: (r) => r.kind === "call" && nightOf(r.ts),
      missed: (r) => r.kind === "call" && ["missed", "rejected", "blocked"].includes(r.dir),
      short: (r) => r.kind === "call" && r.duration > 0 && r.duration < 10,
      long: (r) => r.kind === "call" && r.duration > 600,
      withLoc: (r) => r.lat != null,
      allSms: (r) => r.kind === "sms",
      smsUnknown: (r) => r.kind === "sms" && !r.saved && !r.name,
      chats: (r) => r.kind === "chat",
      top: (r) => top.has(keyOf(r)),
      unsaved: (r) => r.kind !== "chat" && !r.saved && !r.name && /^\+?\d{9,}$/.test(r.number),
      common: (r) => common.has(keyOf(r)),
    };
    const counts = Object.fromEntries(Object.entries(f).map(([k, fn]) => [k, base.filter(fn).length])) as Record<QueryId, number>;
    return { f, counts };
  }, [base, data, latest]);

  const rows = useMemo(() => {
    const fn = queries.f[query];
    let out = base.filter(fn);
    if (party) out = out.filter((r) => (r.kind === "chat" ? `${r.service}:${r.name}` : r.number || r.name) === party);
    return out;
  }, [base, queries, query, party]);
  const geo = useMemo(() => (query === "everything" || query === "withLoc" ? (data?.geo ?? []).filter((g) => !hiddenDevices.has(g.device)) : []), [data, query, hiddenDevices]);
  const points = useMemo(() => toMapPoints(rows, geo, colorOf), [rows, geo, colorOf]);

  if (!data) {
    return (
      <div className="card grid h-full place-items-center text-muted">
        <span className="flex items-center gap-2">
          <Spinner className="size-5" /> {t("an.loading")}
        </span>
      </div>
    );
  }

  const tree: { id: string; label: string; icon: ReactNode; items: QueryId[] }[] = [
    { id: "calls", label: t("cm.group.calls"), icon: <Phone className="size-4" />, items: ["allCalls", "today", "week", "night", "missed", "short", "long", "withLoc"] },
    { id: "messages", label: t("cm.group.messages"), icon: <MessageSquareText className="size-4" />, items: ["allSms", "smsUnknown", "chats"] },
    { id: "contacts", label: t("cm.group.contacts"), icon: <Users className="size-4" />, items: ["top", "unsaved", "common"] },
  ];
  const selectedParty = party ? contactsByKey.get(party) : null;

  return (
    <div className="flex h-full min-h-0 gap-3" data-testid="comms-view">
      {/* queries */}
      <aside className="card flex w-[250px] shrink-0 flex-col overflow-hidden">
        <Panel title={t("cm.queries")}>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
            <QueryItem active={query === "everything"} label={t("cm.q.everything")} count={queries.counts.everything} onClick={() => setQuery("everything")} icon={<Folder className="size-4 text-gold-500" />} />
            {tree.map((g) => (
              <div key={g.id}>
                <button onClick={() => setOpen({ ...open, [g.id]: !open[g.id] })} className="mt-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-[12.5px] font-bold text-ink-2 hover:bg-surface-2">
                  <ChevronDown className={clsx("size-3.5 transition", !open[g.id] && "-rotate-90")} />
                  <span className="text-gold-500">{g.icon}</span>
                  {g.label}
                </button>
                {open[g.id] &&
                  g.items.map((id) => (
                    <QueryItem key={id} indent active={query === id} label={t(`cm.q.${id}`)} count={queries.counts[id]} onClick={() => setQuery(id)} testId={`q-${id}`} />
                  ))}
              </div>
            ))}
          </div>
        </Panel>
        <div className="mt-auto border-t border-line p-3">
          <CdrButtons onDone={() => (void refresh(), void load())} />
        </div>
      </aside>

      {/* map + results */}
      <section className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="card flex min-h-[260px] flex-[1.05] flex-col overflow-hidden">
          <div className="flex shrink-0 items-center gap-2 border-b border-line px-4 py-2">
            <span className="h-3 w-1 rounded-full bg-gold-400" />
            <h4 className="text-[12.5px] font-bold text-ink-2">{t("cm.map")}</h4>
            <span className="tabular text-[11.5px] text-muted">
              {t("cm.towers")} {rows.filter((r) => r.lat != null).length} · {t("cm.photos")} {geo.length}
            </span>
          </div>
          <div className="min-h-0 flex-1">
            <CommsMap points={points} focusId={focus} onPick={setFocus} />
          </div>
        </div>
        <ResultTable
          rows={rows}
          checked={checked}
          setChecked={setChecked}
          focus={focus}
          onFocus={(r) => {
            setFocus(r.id);
            setParty(null);
          }}
          onParty={(key) => setParty(key)}
          devLabel={devLabel}
          colorOf={colorOf}
          title={party ? `${t(`cm.q.${query}`)} · ${selectedParty?.name || party}` : t(`cm.q.${query}`)}
          clearParty={party ? () => setParty(null) : undefined}
        />
      </section>

      {/* subjects + profile */}
      <aside className="card flex w-[330px] shrink-0 flex-col overflow-hidden 2xl:w-[360px]">
        <Panel title={t("cm.subjects")}>
          <div className="flex flex-col gap-1.5 px-3 pb-2">
            {data.devices.map((d) => {
              const hidden = hiddenDevices.has(d.id);
              return (
                <div key={d.id} className="flex items-center gap-2 rounded-xl px-3 py-2 text-white shadow-sm" style={{ background: hidden ? "#64748b" : DEVICE_COLORS[d.index % DEVICE_COLORS.length] }}>
                  <PhoneCall className="size-4 opacity-90" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-bold text-navy-950">{d.label}</span>
                    <span className="block truncate font-mono text-[11px] text-navy-950/75">{d.number || d.serial}</span>
                  </span>
                  <button
                    onClick={() => {
                      const next = new Set(hiddenDevices);
                      if (hidden) next.delete(d.id);
                      else next.add(d.id);
                      setHiddenDevices(next);
                    }}
                    className="grid size-7 place-items-center rounded-lg bg-white/30 text-navy-950 hover:bg-white/50"
                  >
                    {hidden ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              );
            })}
          </div>
        </Panel>
        <div className="min-h-0 flex-1 overflow-y-auto border-t border-line">
          {selectedParty ? (
            <Profile c={selectedParty} rows={base.filter((r) => (r.kind === "chat" ? `${r.service}:${r.name}` : r.number || r.name) === selectedParty.key)} devLabel={devLabel} lang={lang} onNetwork={() => setTab("network")} />
          ) : (
            <TopContacts contacts={data.contacts.filter((c) => c.devices.some((d) => !hiddenDevices.has(d)))} onPick={setParty} />
          )}
        </div>
      </aside>
    </div>
  );
}

function QueryItem({ label, count, active, onClick, indent, icon, testId }: { label: string; count: number; active: boolean; onClick: () => void; indent?: boolean; icon?: ReactNode; testId?: string }) {
  return (
    <button
      onClick={onClick}
      data-testid={testId}
      className={clsx(
        "flex w-full items-center gap-2 rounded-lg py-1.5 pr-2 text-left text-[12.5px] transition",
        indent ? "pl-9" : "pl-2",
        active ? "bg-navy-800 font-semibold text-white dark:bg-gold-400 dark:text-navy-950" : "text-ink-2 hover:bg-surface-2",
      )}
    >
      {icon}
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className={clsx("tabular text-[11.5px]", active ? "opacity-80" : "text-faint")}>{count.toLocaleString()}</span>
    </button>
  );
}

function ResultTable({
  rows,
  checked,
  setChecked,
  focus,
  onFocus,
  onParty,
  devLabel,
  colorOf,
  title,
  clearParty,
}: {
  rows: CommRow[];
  checked: Set<string>;
  setChecked: (s: Set<string>) => void;
  focus: string | null;
  onFocus: (r: CommRow) => void;
  onParty: (key: string) => void;
  devLabel: (id: string) => string;
  colorOf: (id: string) => string;
  title: string;
  clearParty?: () => void;
}) {
  const { t } = useI18n();
  const { errorText } = useStore();
  const ref = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({ count: rows.length, getScrollElement: () => ref.current, estimateSize: () => 38, overscan: 14 });
  const allChecked = rows.length > 0 && rows.every((r) => checked.has(r.id));
  const cols = "30px 46px minmax(120px,1fr) 146px 60px 92px 112px minmax(110px,1fr) 64px 132px minmax(120px,1fr)";
  const doExport = async () => {
    const ids = checked.size ? rows.filter((r) => checked.has(r.id)).map((r) => r.id) : rows.map((r) => r.id);
    const id = toast.loading(t("export.working", { fmt: "Excel" }));
    try {
      const res = await call<{ path: string; name: string }>("export_comms", ids);
      toast.success(t("export.done", { name: res.name }), { id, action: { label: t("export.open"), onClick: () => void call("reveal", res.path) } });
    } catch (e) {
      toast.error(errorText(e), { id });
    }
  };
  return (
    <div className="card flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-2 border-b border-line px-4 py-2">
        <span className="h-3 w-1 rounded-full bg-gold-400" />
        <h4 className="truncate text-[12.5px] font-bold text-ink-2">
          {t("cm.results")} — {title}
        </h4>
        {clearParty && (
          <button onClick={clearParty} className="rounded-full bg-surface-3 px-2 text-[11px] text-muted hover:text-ink">
            ✕
          </button>
        )}
        <span className="tabular ml-auto text-[12px] text-muted">
          {rows.length.toLocaleString()} {checked.size ? `· ${t("cm.selected", { n: checked.size })}` : ""}
        </span>
        <Button size="sm" variant="outline" icon={<FileSpreadsheet className="size-4" />} onClick={() => void doExport()} data-testid="comms-export">
          {t("cm.export")}
        </Button>
      </div>
      <div ref={ref} className="min-h-0 flex-1 overflow-auto" data-testid="comms-table">
      <div className="min-w-[1060px]">
      <div className="sticky top-0 z-10 grid items-center gap-2 bg-surface-2 px-3 py-2 text-[11.5px] font-semibold text-muted" style={{ gridTemplateColumns: cols }}>
        <input type="checkbox" checked={allChecked} onChange={() => setChecked(allChecked ? new Set() : new Set(rows.map((r) => r.id)))} className="accent-[#24479a]" />
        <span>#</span>
        <span>{t("cm.col.device")}</span>
        <span>{t("col.datetime")}</span>
        <span>{t("cm.col.kind")}</span>
        <span>{t("cm.col.dir")}</span>
        <span>{t("col.number")}</span>
        <span>{t("col.name")}</span>
        <span className="text-right">{t("col.duration")}</span>
        <span>{t("cm.col.cell")}</span>
        <span>{t("cm.col.site")}</span>
      </div>
        <div style={{ height: v.getTotalSize(), position: "relative" }}>
          {v.getVirtualItems().map((it) => {
            const r = rows[it.index];
            const on = checked.has(r.id);
            const st = DIRECTION_STYLE[r.dir] ?? DIRECTION_STYLE.unknown;
            const key = r.kind === "chat" ? `${r.service}:${r.name}` : r.number || r.name;
            return (
              <div
                key={r.id}
                onClick={() => onFocus(r)}
                className={clsx(
                  "absolute inset-x-0 grid cursor-pointer items-center gap-2 border-b border-line/60 px-3 text-[12.5px]",
                  focus === r.id ? "bg-gold-50 dark:bg-gold-500/10" : on ? "bg-sky-50 dark:bg-sky-500/10" : it.index % 2 ? "bg-surface-2/40" : "",
                  "hover:bg-row-hover",
                )}
                style={{ gridTemplateColumns: cols, height: it.size, transform: `translateY(${it.start}px)` }}
              >
                <input
                  type="checkbox"
                  checked={on}
                  onClick={(e) => e.stopPropagation()}
                  onChange={() => {
                    const next = new Set(checked);
                    if (on) next.delete(r.id);
                    else next.add(r.id);
                    setChecked(next);
                  }}
                  className="accent-[#24479a]"
                />
                <span className="tabular text-faint">{it.index + 1}</span>
                <span className="flex min-w-0 items-center gap-1.5 truncate">
                  <span className="size-2 shrink-0 rounded-full" style={{ background: colorOf(r.device) }} />
                  <span className="truncate">{devLabel(r.device)}</span>
                </span>
                <span className="tabular truncate">{fmtDateTime(r.ts)}</span>
                <span>
                  <Badge tone={r.kind === "call" ? "blue" : r.kind === "sms" ? "gold" : "green"}>{t(`kind.${r.kind}`)}</Badge>
                </span>
                <span className="truncate text-ink-2">{r.kind === "call" ? <span className="flex items-center gap-1">{st.icon} {t(`dir.${r.dir}`)}</span> : t(`msgdir.${r.dir}`)}</span>
                <button onClick={(e) => (e.stopPropagation(), onParty(key))} className="truncate text-left font-mono text-navy-600 hover:underline dark:text-gold-300">
                  {r.number || r.service}
                </button>
                <span className="truncate">{r.name || <span className="text-faint">—</span>}</span>
                <span className="tabular text-right">{r.kind === "call" ? fmtDuration(r.duration) : ""}</span>
                <span className="truncate font-mono text-[11.5px] text-muted">{r.cell}</span>
                <span className="truncate text-muted">{r.site || r.body}</span>
              </div>
            );
          })}
        </div>
      </div>
      </div>
    </div>
  );
}

function TopContacts({ contacts, onPick }: { contacts: ContactSummary[]; onPick: (key: string) => void }) {
  const { t } = useI18n();
  const max = contacts[0]?.total ?? 1;
  return (
    <Panel title={t("cm.summary")}>
      <p className="px-4 pb-2 text-[11.5px] text-faint">{t("cm.pickContact")}</p>
      <div className="px-2 pb-3">
        {contacts.slice(0, 60).map((c) => (
          <button key={c.key} onClick={() => onPick(c.key)} className="flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left hover:bg-surface-2" data-testid="top-contact">
            <Avatar name={c.name || c.number || c.key} size={30} />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5 truncate text-[12.5px] font-semibold text-ink">
                {c.name || c.number || c.key}
                {c.devices.length > 1 && <Badge tone="red">×{c.devices.length}</Badge>}
              </span>
              <span className="mt-0.5 block h-1.5 overflow-hidden rounded-full bg-surface-3">
                <span className="block h-full rounded-full bg-gradient-to-r from-gold-300 to-gold-500" style={{ width: `${(c.total / max) * 100}%` }} />
              </span>
            </span>
            <span className="tabular text-[12px] font-bold text-muted">{c.total}</span>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function Profile({ c, rows, devLabel, lang, onNetwork }: { c: ContactSummary; rows: CommRow[]; devLabel: (id: string) => string; lang: "th" | "en"; onNetwork: () => void }) {
  const { t } = useI18n();
  const grid = useMemo(() => {
    const g = Array.from({ length: 7 }, () => new Array(24).fill(0));
    rows.forEach((r) => {
      if (!r.ts) return;
      const d = new Date(r.ts);
      g[(d.getDay() + 6) % 7][d.getHours()]++;
    });
    return g;
  }, [rows]);
  const max = Math.max(1, ...grid.flat());
  const days = lang === "th" ? ["จ", "อ", "พ", "พฤ", "ศ", "ส", "อา"] : ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
  const stat = (label: string, value: ReactNode) => (
    <div className="rounded-xl bg-surface-2 px-2 py-2 text-center">
      <div className="tabular font-display text-[16px] font-bold text-ink">{value}</div>
      <div className="truncate text-[10.5px] text-muted">{label}</div>
    </div>
  );
  return (
    <div className="pb-4" data-testid="contact-profile">
      <div className="flex items-center gap-3 px-4 pt-4 pb-3">
        <Avatar name={c.name || c.number || c.key} size={44} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-display text-[17px] font-semibold text-ink">{c.name || c.number || c.key}</div>
          <div className="truncate font-mono text-[12px] text-muted">{c.number || c.app}</div>
        </div>
        <Button size="sm" variant="soft" icon={<Network className="size-4" />} onClick={onNetwork}>
          {t("tab.network")}
        </Button>
      </div>
      <div className="grid grid-cols-3 gap-1.5 px-4">
        {stat(t("dir.outgoing"), c.calls_out)}
        {stat(t("dir.incoming"), c.calls_in)}
        {stat(t("dir.missed"), c.missed)}
        {stat("SMS", c.sms_in + c.sms_out)}
        {stat(t("tab.chats"), c.chats)}
        {stat(t("cm.total"), c.total)}
      </div>
      <div className="mt-3 flex flex-col gap-1 px-4 text-[12.5px] text-ink-2">
        <div className="flex justify-between">
          <span className="text-muted">{t("calls.talk")}</span>
          <b>{fmtHours(c.duration, lang)}</b>
        </div>
        <div className="flex justify-between">
          <span className="text-muted">{t("cm.activeDays")}</span>
          <b>{c.active_days}</b>
        </div>
        <div className="flex justify-between">
          <span className="text-muted">{t("cm.nightShare")}</span>
          <b>{Math.round((c.night / Math.max(1, c.total)) * 100)}%</b>
        </div>
        <div className="flex justify-between">
          <span className="text-muted">{t("net.first")}</span>
          <span className="tabular">{fmtDateTime(c.first)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted">{t("net.last")}</span>
          <span className="tabular">{fmtDateTime(c.last)}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-muted">{t("net.foundIn")}:</span>
          {c.devices.map((d) => (
            <Badge key={d} tone="slate">
              {devLabel(d)}
            </Badge>
          ))}
        </div>
      </div>
      <Panel title={t("cm.hourly")}>
        <div className="px-4">
          <div className="grid gap-[2px]" style={{ gridTemplateColumns: "22px repeat(24, minmax(0, 1fr))" }}>
            {grid.map((row, di) => (
              <div key={di} className="contents">
                <span className="text-[10px] leading-[13px] text-muted">{days[di]}</span>
                {row.map((v, h) => (
                  <span key={h} title={`${days[di]} ${h}:00 · ${v}`} className="h-[13px] rounded-[2px]" style={{ background: v ? `rgba(220,162,42,${0.18 + 0.82 * (v / max)})` : "var(--surface-3)" }} />
                ))}
              </div>
            ))}
          </div>
          <div className="mt-1 ml-[22px] flex justify-between text-[9.5px] text-faint">
            <span>00</span>
            <span>06</span>
            <span>12</span>
            <span>18</span>
            <span>23</span>
          </div>
        </div>
      </Panel>
    </div>
  );
}
