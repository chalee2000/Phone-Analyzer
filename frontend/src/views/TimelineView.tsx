import { useVirtualizer } from "@tanstack/react-virtual";
import clsx from "clsx";
import { ChartGantt, Download, Pencil, Plus, Search, Star, Trash2 } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { AnalysisEmpty } from "../components/AnalysisEmpty";
import { Button, Chip, Field, Input, Modal, ModalHeader, Spinner, Switch } from "../components/ui";
import { DEVICE_COLORS, KIND_ICON, iconSvg, mediaUrlFor, type CaseDevice, type TimelineEvent } from "../lib/analysis";
import { call } from "../lib/bridge";
import { fmtDayHeader, fmtDuration } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";

const LANES = ["people", "objects", "locations", "events"] as const;
type Lane = (typeof LANES)[number];
const LANE_COLOR: Record<Lane, string> = { people: "#38bdf8", objects: "#f59e0b", locations: "#f43f5e", events: "#10b981" };
const TIME_COL = 132;
const DAY = 86_400_000;
const pad = (n: number) => String(n).padStart(2, "0");

const ENTRY_TYPES_TH = ["การจับกุม", "หมายค้น", "ตรวจยึดของกลาง", "สอบปากคำ", "ยานพาหนะ", "สถานที่เกิดเหตุ", "บุคคล", "พยานหลักฐาน", "บันทึก", "อื่น ๆ"];
const ENTRY_TYPES_EN = ["Arrest", "Search warrant", "Seizure", "Interview", "Vehicle", "Scene", "Person", "Exhibit", "Note", "Other"];

function elapsed(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `+${pad(Math.floor(s / 86400))}.${pad(Math.floor((s % 86400) / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

function dayKey(ts: number) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function toLocalInput(ms: number) {
  const d = new Date(ms);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type Row = { type: "day"; key: string; ts: number; count: number } | { type: "event"; ev: TimelineEvent };

export function TimelineView() {
  const { state } = useStore();
  if (!state.case || !state.case.extraction_count) return <AnalysisEmpty icon={<ChartGantt />} />;
  return <Timeline />;
}

function Timeline() {
  const { t, lang } = useI18n();
  const { state, info, errorText } = useStore();
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [devices, setDevices] = useState<CaseDevice[]>([]);
  const [lanes, setLanes] = useState<Set<Lane>>(new Set(LANES));
  const [hiddenKinds, setHiddenKinds] = useState<Set<string>>(new Set());
  const [hiddenDevices, setHiddenDevices] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [from, setFrom] = useState<number | null>(null);
  const [to, setTo] = useState<number | null>(null);
  const [bookmarkedOnly, setBookmarkedOnly] = useState(false);
  const [systemApps, setSystemApps] = useState(false);
  const [editing, setEditing] = useState<Partial<TimelineEvent> | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [range, setRange] = useState<"all" | 7 | 30 | "custom">("all");
  const initialRange = useRef(false);

  const load = useCallback(async () => {
    try {
      const res = await call<{ events: TimelineEvent[]; devices: CaseDevice[] }>("timeline", { system_apps: systemApps });
      setEvents(res.events);
      setDevices(res.devices);
      const ev = res.events;
      // Long histories (app installs, SIMs) would push recent activity far down: start on the last 30 days.
      if (!initialRange.current && ev.length && ev[ev.length - 1].ts - ev[0].ts > 45 * DAY) {
        initialRange.current = true;
        setFrom(ev[ev.length - 1].ts - 30 * DAY);
        setRange(30);
      }
    } catch (e) {
      toast.error(errorText(e));
    }
  }, [systemApps, errorText]);
  useEffect(() => {
    void load();
  }, [load, state.case?.id, state.case?.extraction_count]);

  const kindCounts = useMemo(() => {
    const c: Record<string, number> = {};
    (events ?? []).forEach((e) => (c[e.kind] = (c[e.kind] ?? 0) + 1));
    return c;
  }, [events]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (events ?? []).filter(
      (e) =>
        lanes.has(e.lane) &&
        !hiddenKinds.has(e.kind) &&
        !(e.device && hiddenDevices.has(e.device)) &&
        (from == null || e.ts >= from) &&
        (to == null || e.ts <= to) &&
        (!bookmarkedOnly || e.bookmark !== undefined) &&
        (!needle || [e.name, e.number, e.detail].some((v) => v && v.toLowerCase().includes(needle))),
    );
  }, [events, lanes, hiddenKinds, hiddenDevices, from, to, bookmarkedOnly, q]);

  const laneCounts = useMemo(() => {
    const c: Record<string, number> = {};
    (events ?? []).forEach((e) => (c[e.lane] = (c[e.lane] ?? 0) + 1));
    return c;
  }, [events]);

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    let current = "";
    let header: Row | null = null;
    for (const ev of filtered) {
      const k = dayKey(ev.ts);
      if (k !== current) {
        current = k;
        header = { type: "day", key: k, ts: ev.ts, count: 0 };
        out.push(header);
      }
      if (header && header.type === "day") header.count++;
      out.push({ type: "event", ev });
    }
    return out;
  }, [filtered]);

  const start = filtered[0]?.ts ?? 0;
  const parentRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  useLayoutEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, [events]);
  const avail = width - TIME_COL - 24;
  const cardW = Math.max(270, Math.min(440, avail * 0.36));
  const spacing = Math.max(60, (avail - cardW - 30) / 3);
  const laneX = LANES.map((_, i) => TIME_COL + 18 + i * spacing);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: (i) => (rows[i].type === "day" ? 44 : 112),
    overscan: 8,
  });

  const toggleBookmark = async (ev: TimelineEvent) => {
    const on = ev.bookmark === undefined;
    await call("timeline_bookmark", ev.id, on, "");
    setEvents((list) => (list ?? []).map((e) => (e.id === ev.id ? { ...e, bookmark: on ? "" : undefined } : e)));
  };

  const doExport = async (fmt: "xlsx" | "pdf") => {
    setExportOpen(false);
    const id = toast.loading(t("export.working", { fmt: fmt.toUpperCase() }));
    try {
      const res = await call<{ path: string; name: string }>("export_timeline", fmt, filtered.map((e) => e.id), { system_apps: systemApps });
      toast.success(t("export.done", { name: res.name }), { id, action: { label: t("export.open"), onClick: () => void call("reveal", res.path) } });
    } catch (e) {
      toast.error(errorText(e), { id });
    }
  };

  const quick = (days: 7 | 30 | null) => {
    setRange(days ?? "all");
    if (days == null || !events?.length) {
      setFrom(null);
      setTo(null);
      return;
    }
    const end = events[events.length - 1].ts;
    setFrom(end - days * DAY);
    setTo(null);
  };

  if (!events) {
    return (
      <div className="card grid h-full place-items-center text-muted">
        <span className="flex items-center gap-2">
          <Spinner className="size-5" /> {t("an.loading")}
        </span>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3" data-testid="timeline-view">
      <div className="card flex shrink-0 flex-wrap items-center gap-2 px-4 py-3">
        <h3 className="mr-2 font-display text-[18px] font-semibold text-ink">{t("tl.title")}</h3>
        <span className="tabular rounded-full bg-surface-3 px-2.5 py-0.5 text-[12px] font-semibold text-muted">{t("tl.events", { n: filtered.length.toLocaleString() })}</span>
        <Input className="ml-2 w-60" icon={<Search className="size-4" />} placeholder={t("tb.search")} value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="flex gap-1">
          {LANES.map((l) => (
            <Chip
              key={l}
              active={lanes.has(l)}
              count={laneCounts[l] ?? 0}
              onClick={() => {
                const next = new Set(lanes);
                if (next.has(l)) next.delete(l);
                else next.add(l);
                setLanes(next);
              }}
            >
              <span className="size-2 rounded-full" style={{ background: LANE_COLOR[l] }} /> {t(`tl.lane.${l}`)}
            </Chip>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <label className="flex items-center gap-2 text-[12.5px] text-ink-2">
            <Star className="size-4 text-gold-500" /> {t("tl.bookmarked")}
            <Switch checked={bookmarkedOnly} onChange={setBookmarkedOnly} />
          </label>
          <span className="relative">
            <Button variant="outline" size="sm" icon={<Download className="size-4" />} onClick={() => setExportOpen((o) => !o)}>
              {t("tl.export")}
            </Button>
            {exportOpen && (
              <div className="absolute top-full right-0 z-20 mt-1 w-40 rounded-xl border border-line bg-surface p-1 shadow-[var(--shadow-pop)]">
                <button className="w-full rounded-lg px-3 py-2 text-left text-[13px] hover:bg-surface-2" onClick={() => void doExport("xlsx")}>
                  Excel
                </button>
                <button className="w-full rounded-lg px-3 py-2 text-left text-[13px] hover:bg-surface-2" onClick={() => void doExport("pdf")}>
                  PDF
                </button>
              </div>
            )}
          </span>
          <Button variant="gold" size="sm" icon={<Plus className="size-4" />} onClick={() => setEditing({ ts: Date.now(), lane: "events", name: "", detail: "", extra: {} })} data-testid="tl-add">
            {t("tl.add")}
          </Button>
        </div>
        <div className="flex w-full flex-wrap items-center gap-1.5 pt-1">
          {Object.keys(kindCounts)
            .sort((a, b) => kindCounts[b] - kindCounts[a])
            .map((k) => (
              <button
                key={k}
                onClick={() => {
                  const next = new Set(hiddenKinds);
                  if (next.has(k)) next.delete(k);
                  else next.add(k);
                  setHiddenKinds(next);
                }}
                className={clsx("flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-semibold", hiddenKinds.has(k) ? "border-dashed border-line text-faint" : "border-line bg-surface-2 text-ink-2")}
              >
                <span className="size-3.5" dangerouslySetInnerHTML={{ __html: iconSvg(KIND_ICON[k] ?? KIND_ICON.manual, "currentColor", 14) }} />
                {t(`tl.kind.${k}`)} <span className="tabular text-faint">{kindCounts[k]}</span>
              </button>
            ))}
          <span className="mx-1 h-5 w-px bg-line" />
          {devices.map((d) => (
            <button
              key={d.id}
              onClick={() => {
                const next = new Set(hiddenDevices);
                if (next.has(d.id)) next.delete(d.id);
                else next.add(d.id);
                setHiddenDevices(next);
              }}
              className={clsx("flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-semibold", hiddenDevices.has(d.id) ? "border-dashed border-line text-faint" : "border-line bg-surface-2 text-ink-2")}
            >
              <span className="size-2.5 rounded-full" style={{ background: DEVICE_COLORS[d.index % DEVICE_COLORS.length] }} /> {d.label}
            </button>
          ))}
          <span className="ml-auto flex items-center gap-1.5 text-[12px] text-muted">
            {([7, 30, null] as const).map((n) => (
              <button
                key={String(n)}
                onClick={() => quick(n)}
                className={clsx("rounded-lg px-2 py-1 font-semibold", range === (n ?? "all") ? "bg-navy-800 text-white dark:bg-gold-400 dark:text-navy-950" : "hover:bg-surface-2")}
                data-testid={`tl-range-${n ?? "all"}`}
              >
                {t(`tl.range.${n ?? "all"}`)}
              </button>
            ))}
            {t("tl.from")}
            <input type="date" className="rounded-lg border border-line bg-surface px-2 py-1 text-[12px] text-ink" value={from ? toLocalInput(from).slice(0, 10) : ""} onChange={(e) => (setRange("custom"), setFrom(e.target.value ? new Date(e.target.value + "T00:00").getTime() : null))} />
            {t("tl.to")}
            <input type="date" className="rounded-lg border border-line bg-surface px-2 py-1 text-[12px] text-ink" value={to ? toLocalInput(to).slice(0, 10) : ""} onChange={(e) => (setRange("custom"), setTo(e.target.value ? new Date(e.target.value + "T23:59:59").getTime() : null))} />
            <label className="ml-2 flex items-center gap-1.5">
              {t("tl.systemApps")} <Switch checked={systemApps} onChange={setSystemApps} />
            </label>
          </span>
        </div>
      </div>

      <Overview events={filtered} onPickDay={(k) => virtualizer.scrollToIndex(rows.findIndex((r) => r.type === "day" && r.key === k), { align: "start" })} />

      <div className="card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="relative h-11 shrink-0 border-b border-line bg-surface-2">
          <span className="absolute top-3 left-5 text-[11.5px] font-bold tracking-wide text-muted" title={t("tl.elapsed")}>
            {t("tl.when")}
          </span>
          {LANES.map((l, i) => (
            <span key={l} className="absolute top-2.5 flex -translate-x-1/2 items-center gap-1.5 text-[12.5px] font-bold tracking-wide uppercase" style={{ left: laneX[i], color: LANE_COLOR[l] }}>
              {t(`tl.lane.${l}`)}
            </span>
          ))}
        </div>
        <div ref={parentRef} className="relative min-h-0 flex-1 overflow-auto" data-testid="timeline-scroll">
          {rows.length === 0 ? (
            <p className="p-10 text-center text-muted">{t("tl.empty")}</p>
          ) : (
            <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
              {LANES.map((l, i) => (
                <span key={l} className="pointer-events-none absolute top-0 bottom-0 w-[2px] opacity-50" style={{ left: laneX[i] - 1, background: LANE_COLOR[l] }} />
              ))}
              {virtualizer.getVirtualItems().map((it) => {
                const row = rows[it.index];
                return (
                  <div key={it.key} ref={virtualizer.measureElement} data-index={it.index} className="absolute inset-x-0" style={{ transform: `translateY(${it.start}px)` }}>
                    {row.type === "day" ? (
                      <div className="flex h-11 items-center gap-3 border-y border-line bg-surface-2/95 px-5 backdrop-blur">
                        <span className="font-display text-[14px] font-semibold text-ink">{fmtDayHeader(row.ts, lang)}</span>
                        <span className="tabular text-[12px] text-muted">{t("tl.events", { n: row.count })}</span>
                      </div>
                    ) : (
                      <EventRow
                        ev={row.ev}
                        start={start}
                        laneX={laneX}
                        cardW={cardW}
                        devices={devices}
                        thumb={row.ev.kind === "photo" && row.ev.extra.thumb ? mediaUrlFor(info?.media_base, state.case?.id, row.ev.device, row.ev.extra.thumb) : ""}
                        onBookmark={() => void toggleBookmark(row.ev)}
                        onEdit={() => setEditing(row.ev)}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <EntryDialog
        entry={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          toast.success(t("tl.saved"));
          void load();
        }}
      />
    </div>
  );
}

function Overview({ events, onPickDay }: { events: TimelineEvent[]; onPickDay: (key: string) => void }) {
  const { t, lang } = useI18n();
  const days = useMemo(() => {
    if (!events.length) return [];
    const map = new Map<string, Record<Lane, number> & { ts: number }>();
    for (const e of events) {
      const k = dayKey(e.ts);
      const d = map.get(k) ?? { ts: new Date(k + "T00:00").getTime(), people: 0, objects: 0, locations: 0, events: 0 };
      d[e.lane]++;
      map.set(k, d);
    }
    const first = new Date(dayKey(events[0].ts) + "T00:00").getTime();
    const last = new Date(dayKey(events[events.length - 1].ts) + "T00:00").getTime();
    const out: { key: string; ts: number; v: Record<Lane, number> }[] = [];
    const span = Math.min(400, Math.round((last - first) / DAY) + 1);
    const startAt = last - (span - 1) * DAY;
    for (let i = 0; i < span; i++) {
      const ts = startAt + i * DAY;
      const k = dayKey(ts);
      const d = map.get(k);
      out.push({ key: k, ts, v: { people: d?.people ?? 0, objects: d?.objects ?? 0, locations: d?.locations ?? 0, events: d?.events ?? 0 } });
    }
    return out;
  }, [events]);
  const max = Math.max(1, ...days.map((d) => LANES.reduce((a, l) => a + d.v[l], 0)));
  if (!days.length) return null;
  return (
    <div className="card shrink-0 px-4 pt-2.5 pb-2" data-testid="timeline-overview">
      <div className="mb-1 flex items-center gap-3 text-[11.5px] text-muted">
        <span className="font-semibold text-ink-2">{t("tl.overview")}</span>
        {LANES.map((l) => (
          <span key={l} className="flex items-center gap-1">
            <span className="size-2 rounded-sm" style={{ background: LANE_COLOR[l] }} /> {t(`tl.lane.${l}`)}
          </span>
        ))}
        <span className="tabular ml-auto">
          {fmtDayHeader(days[0].ts, lang)} – {fmtDayHeader(days[days.length - 1].ts, lang)}
        </span>
      </div>
      <div className="flex h-16 items-end gap-[2px]">
        {days.map((d) => {
          const total = LANES.reduce((a, l) => a + d.v[l], 0);
          return (
            <button
              key={d.key}
              title={`${d.key} · ${total}`}
              onClick={() => total && onPickDay(d.key)}
              className="group flex h-full min-w-[2px] flex-1 flex-col-reverse overflow-hidden rounded-t-sm hover:opacity-80"
            >
              {LANES.map((l) => (
                <span key={l} style={{ height: `${(d.v[l] / max) * 100}%`, background: LANE_COLOR[l] }} className="w-full shrink-0" />
              ))}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function EventRow({
  ev,
  start,
  laneX,
  cardW,
  devices,
  thumb,
  onBookmark,
  onEdit,
}: {
  ev: TimelineEvent;
  start: number;
  laneX: number[];
  cardW: number;
  devices: CaseDevice[];
  thumb: string;
  onBookmark: () => void;
  onEdit: () => void;
}) {
  const { t } = useI18n();
  const lane = LANES.indexOf(ev.lane);
  const color = LANE_COLOR[ev.lane];
  const d = new Date(ev.ts);
  const dev = devices.find((x) => x.id === ev.device);
  const dir = ev.extra.direction ? t(ev.kind === "call" ? `dir.${ev.extra.direction}` : `msgdir.${ev.extra.direction}`) : "";
  const kindLabel = ev.kind === "manual" ? ev.extra.entity_type || t("tl.kind.manual") : t(`tl.kind.${ev.kind}`);
  const third =
    ev.kind === "call"
      ? [t("tl.duration"), fmtDuration(ev.extra.duration)]
      : ev.number && ev.number !== ev.name
        ? [t("col.number"), ev.number]
        : ev.extra.lat != null
          ? [t("photos.coords"), `${Number(ev.extra.lat).toFixed(4)}, ${Number(ev.extra.lon).toFixed(4)}`]
          : null;
  return (
    <div className="relative" style={{ minHeight: 104 }} data-testid="tl-event">
      <div className="absolute top-3 left-5 text-[12px] leading-tight">
        <div className="tabular font-semibold text-ink">{`${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`}</div>
        <div className="tabular mt-0.5 text-[11px] font-semibold text-faint">{elapsed(ev.ts - start)}</div>
      </div>
      <span
        className="absolute top-3 grid size-10 -translate-x-1/2 place-items-center overflow-hidden rounded-full border-[3px] bg-surface shadow-md"
        style={{ left: laneX[lane], borderColor: color }}
      >
        {thumb ? (
          <img src={thumb} alt="" className="size-full object-cover" loading="lazy" />
        ) : (
          <span className="size-[18px]" dangerouslySetInnerHTML={{ __html: iconSvg(KIND_ICON[ev.kind] ?? KIND_ICON.manual, color, 18, 2.2) }} />
        )}
      </span>
      <div
        className={clsx("relative my-2.5 rounded-xl border border-line bg-surface shadow-[var(--shadow-card)]", ev.bookmark !== undefined && "ring-2 ring-gold-300")}
        style={{ marginLeft: laneX[lane] + 30, width: cardW, borderTop: `3px solid ${color}` }}
      >
        <div className="grid grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)_minmax(0,0.9fr)] gap-3 px-3.5 pt-2.5">
          <div className="min-w-0">
            <div className="text-[10px] font-bold tracking-wide text-faint uppercase">{t("tl.entityType")}</div>
            <div className="truncate text-[12.5px] font-semibold" style={{ color }}>
              {kindLabel}
              {dir && <span className="text-muted"> · {dir}</span>}
            </div>
          </div>
          <div className="min-w-0">
            <div className="text-[10px] font-bold tracking-wide text-faint uppercase">{t("tl.name")}</div>
            <div className="truncate text-[12.5px] font-semibold text-ink" title={ev.name}>
              {ev.name || "—"}
            </div>
          </div>
          {third && (
            <div className="min-w-0">
              <div className="text-[10px] font-bold tracking-wide text-faint uppercase">{third[0]}</div>
              <div className="tabular truncate font-mono text-[12px] text-ink-2">{third[1]}</div>
            </div>
          )}
        </div>
        {ev.detail && <p className="line-clamp-2 px-3.5 pt-1 text-[12.5px] leading-snug text-ink-2">{ev.detail}</p>}
        <div className="flex items-center gap-2 px-3.5 pt-1.5 pb-2 text-[11px] text-muted">
          {dev ? (
            <span className="flex min-w-0 items-center gap-1.5 truncate">
              <span className="size-2 shrink-0 rounded-full" style={{ background: DEVICE_COLORS[dev.index % DEVICE_COLORS.length] }} />
              {dev.label}
            </span>
          ) : (
            <span>{t("tl.examiner")}</span>
          )}
          <span className="ml-auto flex items-center gap-1">
            {ev.manual && (
              <button onClick={onEdit} className="grid size-6 place-items-center rounded-md hover:bg-surface-3" title={t("tl.edit")}>
                <Pencil className="size-3.5" />
              </button>
            )}
            <button onClick={onBookmark} className="grid size-6 place-items-center rounded-md hover:bg-surface-3" title={t("tl.bookmark")} data-testid="tl-bookmark">
              <Star className={clsx("size-3.5", ev.bookmark !== undefined ? "fill-gold-400 text-gold-500" : "")} />
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}

function EntryDialog({ entry, onClose, onSaved }: { entry: Partial<TimelineEvent> | null; onClose: () => void; onSaved: () => void }) {
  const { t, lang } = useI18n();
  const [when, setWhen] = useState("");
  const [lane, setLane] = useState<Lane>("events");
  const [type, setType] = useState("");
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const editingId = entry?.manual ? (entry.extra?.entry_id as string) : undefined;
  useEffect(() => {
    if (!entry) return;
    setWhen(toLocalInput(entry.ts ?? Date.now()));
    setLane((entry.lane as Lane) ?? "events");
    setType(entry.extra?.entity_type ?? "");
    setName(entry.name ?? "");
    setDesc(entry.detail ?? "");
  }, [entry]);
  const types = lang === "th" ? ENTRY_TYPES_TH : ENTRY_TYPES_EN;
  return (
    <Modal open={!!entry} onClose={onClose} width={560}>
      <ModalHeader icon={<Plus className="size-5" />} tone="gold" title={editingId ? t("tl.edit") : t("tl.add")} onClose={onClose} />
      <div className="flex flex-col gap-3 px-6 py-5">
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("tl.when")}>
            <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} data-testid="tl-when" />
          </Field>
          <Field label={t("tl.entityType")}>
            <Input list="tl-types" value={type} onChange={(e) => setType(e.target.value)} />
            <datalist id="tl-types">
              {types.map((x) => (
                <option key={x} value={x} />
              ))}
            </datalist>
          </Field>
        </div>
        <Field label={t("tl.lane")}>
          <div className="flex gap-1 rounded-xl bg-surface-3 p-1">
            {LANES.map((l) => (
              <button key={l} onClick={() => setLane(l)} className={clsx("flex flex-1 items-center justify-center gap-1.5 rounded-lg py-1.5 text-[12.5px] font-semibold", lane === l ? "bg-surface text-ink shadow" : "text-muted")}>
                <span className="size-2 rounded-full" style={{ background: LANE_COLOR[l] }} /> {t(`tl.lane.${l}`)}
              </button>
            ))}
          </div>
        </Field>
        <Field label={t("tl.name")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} data-testid="tl-name" />
        </Field>
        <Field label={t("tl.description")}>
          <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={3} className="rounded-xl border border-line-strong bg-surface px-3 py-2 text-[14px] text-ink outline-none focus:ring-[3px] focus:ring-[var(--ring)]" />
        </Field>
      </div>
      <div className="flex items-center gap-2 border-t border-line bg-surface-2 px-6 py-4">
        {editingId && (
          <Button
            variant="ghost"
            icon={<Trash2 className="size-4" />}
            onClick={async () => {
              await call("timeline_delete_entry", editingId);
              onSaved();
            }}
          >
            {t("tl.delete")}
          </Button>
        )}
        <Button variant="ghost" className="ml-auto" onClick={onClose}>
          {t("common.cancel")}
        </Button>
        <Button
          variant="primary"
          disabled={!when || !name.trim()}
          onClick={async () => {
            await call("timeline_save_entry", { id: editingId, ts: new Date(when).getTime(), lane, entity_type: type, name, description: desc });
            onSaved();
          }}
          data-testid="tl-save"
        >
          {t("tl.save")}
        </Button>
      </div>
    </Modal>
  );
}
