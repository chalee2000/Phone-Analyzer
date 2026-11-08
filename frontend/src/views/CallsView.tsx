import clsx from "clsx";
import { Clock, PhoneIncoming, PhoneMissed, PhoneOff, PhoneOutgoing, TrendingUp } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { DataTable, SearchBox, Toolbar, type Column } from "../components/DataTable";
import { EmptySearch, KindView } from "../components/States";
import { Badge, Chip } from "../components/ui";
import { avatarColor, fmtDateTime, fmtDuration, fmtHours, initials, matches } from "../lib/format";
import { useI18n } from "../lib/i18n";
import type { CallRecord } from "../lib/types";

export const DIRECTION_STYLE: Record<string, { icon: ReactNode; tone: string }> = {
  incoming: { icon: <PhoneIncoming className="size-3.5" />, tone: "blue" },
  outgoing: { icon: <PhoneOutgoing className="size-3.5" />, tone: "green" },
  missed: { icon: <PhoneMissed className="size-3.5" />, tone: "red" },
  rejected: { icon: <PhoneOff className="size-3.5" />, tone: "amber" },
  blocked: { icon: <PhoneOff className="size-3.5" />, tone: "slate" },
  voicemail: { icon: <PhoneMissed className="size-3.5" />, tone: "violet" },
  unknown: { icon: <PhoneIncoming className="size-3.5" />, tone: "slate" },
};

export function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  return (
    <span
      className={clsx("grid shrink-0 place-items-center rounded-full bg-gradient-to-br font-semibold text-white", avatarColor(name || "?"))}
      style={{ width: size, height: size, fontSize: size * 0.42 }}
    >
      {initials(name || "?")}
    </span>
  );
}

function Calls({ rows }: { rows: CallRecord[] }) {
  const { t, lang } = useI18n();
  const [q, setQ] = useState("");
  const [dir, setDir] = useState("all");
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    rows.forEach((r) => (c[r.direction] = (c[r.direction] ?? 0) + 1));
    return c;
  }, [rows]);
  const talk = useMemo(() => rows.reduce((a, r) => a + (r.duration || 0), 0), [rows]);
  const top = useMemo(() => {
    const m = new Map<string, { name: string; number: string; n: number }>();
    rows.forEach((r) => {
      const e = m.get(r.number) ?? { name: r.name, number: r.number, n: 0 };
      e.n++;
      m.set(r.number, e);
    });
    return [...m.values()].sort((a, b) => b.n - a.n).slice(0, 5);
  }, [rows]);
  const filtered = useMemo(
    () => rows.filter((r) => (dir === "all" || r.direction === dir) && matches([r.number, r.name, r.location, r.service], q)),
    [rows, q, dir],
  );
  const columns: Column<CallRecord>[] = [
    {
      key: "type",
      header: t("col.type"),
      width: "118px",
      render: (r) => {
        const s = DIRECTION_STYLE[r.direction] ?? DIRECTION_STYLE.unknown;
        return (
          <Badge tone={s.tone}>
            {s.icon} {t(`dir.${r.direction}`)}
          </Badge>
        );
      },
      sort: (r) => r.direction,
    },
    { key: "time", header: t("col.datetime"), width: "170px", render: (r) => <span className="tabular text-ink-2">{fmtDateTime(r.timestamp)}</span>, sort: (r) => r.timestamp ?? 0 },
    {
      key: "name",
      header: t("col.name"),
      width: "1.4fr",
      render: (r) => (
        <span className="flex items-center gap-2.5">
          <Avatar name={r.name || r.number} size={30} />
          <span className="truncate font-medium">{r.name || <span className="text-faint">—</span>}</span>
        </span>
      ),
      sort: (r) => r.name,
    },
    { key: "number", header: t("col.number"), width: "1fr", render: (r) => <span className="tabular font-mono text-[13px]">{r.number}</span>, sort: (r) => r.number },
    { key: "dur", header: t("col.duration"), width: "96px", align: "right", render: (r) => <span className="tabular">{fmtDuration(r.duration)}</span>, sort: (r) => r.duration },
    {
      key: "sim",
      header: t("col.sim"),
      width: "150px",
      render: (r) => (
        <span className="flex items-center gap-1.5 text-[12.5px] text-muted">
          {r.sim}
          {r.service !== "cellular" && <Badge tone="violet">{r.service}</Badge>}
        </span>
      ),
    },
  ];
  return (
    <div className="flex h-full min-h-0 gap-4">
      <div className="card flex min-w-0 flex-1 flex-col gap-3 p-5">
        <Toolbar shown={filtered.length} total={rows.length}>
          <SearchBox value={q} onChange={setQ} />
          <Chip active={dir === "all"} onClick={() => setDir("all")} count={rows.length}>
            {t("tb.all")}
          </Chip>
          {["incoming", "outgoing", "missed", "rejected"].map((d) =>
            counts[d] ? (
              <Chip key={d} active={dir === d} onClick={() => setDir(d)} count={counts[d]}>
                {t(`dir.${d}`)}
              </Chip>
            ) : null,
          )}
        </Toolbar>
        <DataTable rows={filtered} columns={columns} empty={<EmptySearch />} initialSort={{ key: "time", dir: "desc" }} testId="calls-table" />
      </div>
      <aside className="hidden w-[290px] shrink-0 flex-col gap-4 2xl:flex xl:flex">
        <div className="card p-5">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-muted">
            <Clock className="size-4" /> {t("calls.talk")}
          </div>
          <div className="mt-2 font-display text-[28px] font-bold text-navy-800 dark:text-white">{fmtHours(talk, lang)}</div>
          <div className="mt-4 flex h-2.5 overflow-hidden rounded-full">
            {["incoming", "outgoing", "missed", "rejected"].map((d, i) => (
              <span
                key={d}
                className={["bg-sky-500", "bg-emerald-500", "bg-rose-500", "bg-amber-400"][i]}
                style={{ width: `${((counts[d] ?? 0) / rows.length) * 100}%` }}
                title={t(`dir.${d}`)}
              />
            ))}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-y-1.5 text-[12.5px] text-muted">
            {["incoming", "outgoing", "missed", "rejected"].map((d, i) => (
              <span key={d} className="flex items-center gap-1.5">
                <span className={clsx("size-2 rounded-full", ["bg-sky-500", "bg-emerald-500", "bg-rose-500", "bg-amber-400"][i])} />
                {t(`dir.${d}`)} <b className="tabular text-ink">{counts[d] ?? 0}</b>
              </span>
            ))}
          </div>
        </div>
        <div className="card flex-1 p-5">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-muted">
            <TrendingUp className="size-4" /> {t("calls.top")}
          </div>
          <div className="mt-3 flex flex-col gap-3">
            {top.map((p, i) => (
              <button key={p.number} onClick={() => setQ(p.number)} className="group flex items-center gap-3 text-left">
                <span className="tabular w-4 text-[12px] font-bold text-faint">{i + 1}</span>
                <Avatar name={p.name || p.number} size={34} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] font-semibold text-ink group-hover:text-navy-600 dark:group-hover:text-gold-300">{p.name || p.number}</span>
                  <span className="block h-1.5 overflow-hidden rounded-full bg-surface-3">
                    <span className="block h-full rounded-full bg-gradient-to-r from-gold-300 to-gold-500" style={{ width: `${(p.n / top[0].n) * 100}%` }} />
                  </span>
                </span>
                <span className="tabular text-[12px] text-muted">{t("calls.times", { n: p.n })}</span>
              </button>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}

export function CallsView() {
  return <KindView<CallRecord> kind="calls">{(rows) => <Calls rows={rows} />}</KindView>;
}
