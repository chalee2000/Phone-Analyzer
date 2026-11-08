import clsx from "clsx";
import { AppWindow, EyeOff, Globe, Lock, LockOpen, Mic, NotebookPen, Pause, Play, ShieldCheck, Wifi } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { DataTable, SearchBox, Toolbar, type Column } from "../components/DataTable";
import { CopyButton } from "../components/DevicePanel";
import { SimChipIcon } from "../components/icons";
import { EmptySearch, KindView } from "../components/States";
import { Badge, Chip } from "../components/ui";
import { avatarColor, fmtDateTime, fmtDuration, fmtSize, matches } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import type { App, Note, SimCard, VoiceMemo, WebVisit, WifiNetwork } from "../lib/types";

export function useMediaUrl() {
  const { info, state } = useStore();
  return (rel: string) => {
    if (!info?.media_base || !state.extraction || !rel) return "";
    const parts = rel.split("/").map(encodeURIComponent).join("/");
    return `${info.media_base}/${encodeURIComponent(state.extraction.case_id)}/extractions/${encodeURIComponent(state.extraction.id)}/${parts}`;
  };
}

/* ── Web history ───────────────────────────────────────────────────── */
function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function Web({ rows }: { rows: WebVisit[] }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const filtered = useMemo(() => rows.filter((r) => matches([r.url, r.title], q)), [rows, q]);
  const columns: Column<WebVisit>[] = [
    { key: "time", header: t("col.datetime"), width: "170px", render: (r) => <span className="tabular text-ink-2">{fmtDateTime(r.timestamp)}</span>, sort: (r) => r.timestamp ?? 0 },
    {
      key: "title",
      header: t("col.title"),
      width: "1.6fr",
      render: (r) => {
        const host = hostOf(r.url);
        return (
          <span className="flex items-center gap-3">
            <span className={clsx("grid size-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br text-[13px] font-bold text-white uppercase", avatarColor(host))}>{host[0]}</span>
            <span className="min-w-0">
              <span className="block truncate font-medium">{r.title || host}</span>
              <span className="block truncate text-[12px] text-muted">{host}</span>
            </span>
          </span>
        );
      },
      sort: (r) => r.title,
    },
    { key: "url", header: t("col.url"), width: "2fr", render: (r) => <span className="truncate font-mono text-[12px] text-ink-2" title={r.url}>{r.url}</span>, sort: (r) => r.url },
    { key: "visits", header: t("col.visits"), width: "70px", align: "right", render: (r) => <span className="tabular">{r.visit_count}</span>, sort: (r) => r.visit_count },
  ];
  return (
    <div className="card flex h-full min-h-0 flex-col gap-3 p-5">
      <Toolbar shown={filtered.length} total={rows.length}>
        <SearchBox value={q} onChange={setQ} />
        <Badge tone="blue">
          <Globe className="size-3.5" /> {rows[0]?.browser}
        </Badge>
      </Toolbar>
      <DataTable rows={filtered} columns={columns} empty={<EmptySearch />} rowHeight={56} initialSort={{ key: "time", dir: "desc" }} />
    </div>
  );
}
export const WebView = () => <KindView<WebVisit> kind="web">{(rows) => <Web rows={rows} />}</KindView>;

/* ── Notes ─────────────────────────────────────────────────────────── */
function Notes({ rows }: { rows: Note[] }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const filtered = rows.filter((r) => matches([r.title, r.body, r.folder], q));
  return (
    <div className="card flex h-full min-h-0 flex-col gap-4 p-5">
      <Toolbar shown={filtered.length} total={rows.length}>
        <SearchBox value={q} onChange={setQ} />
      </Toolbar>
      <div className="min-h-0 flex-1 overflow-auto" data-selectable>
        {filtered.length === 0 ? (
          <EmptySearch />
        ) : (
          <div className="columns-1 gap-4 lg:columns-2 2xl:columns-3">
            {filtered.map((n, i) => (
              <article key={i} className="mb-4 break-inside-avoid rounded-2xl border border-line bg-gradient-to-b from-gold-50/70 to-surface p-5 shadow-[var(--shadow-card)] dark:from-gold-500/5">
                <div className="flex items-start gap-2">
                  <NotebookPen className="mt-1 size-4 shrink-0 text-gold-500" />
                  <h4 className="font-display text-[16.5px] font-semibold text-ink">{n.title}</h4>
                  {n.folder && <Badge tone="gold" className="ml-auto">{n.folder}</Badge>}
                </div>
                <p className="mt-2 text-[14px] leading-relaxed whitespace-pre-wrap text-ink-2">{n.body}</p>
                <div className="tabular mt-3 text-[11.5px] text-faint">
                  {t("notes.modified")} {fmtDateTime(n.modified)}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
export const NotesView = () => <KindView<Note> kind="notes">{(rows) => <Notes rows={rows} />}</KindView>;

/* ── Voice recordings ──────────────────────────────────────────────── */
function Voice({ rows }: { rows: VoiceMemo[] }) {
  const media = useMediaUrl();
  const [playing, setPlaying] = useState<number | null>(null);
  const [progress, setProgress] = useState(0);
  const audio = useRef<HTMLAudioElement>(null);
  const toggle = (i: number) => {
    const el = audio.current;
    if (!el) return;
    if (playing === i) {
      el.pause();
      setPlaying(null);
      return;
    }
    el.src = media(rows[i].path);
    void el.play();
    setPlaying(i);
  };
  return (
    <div className="card flex h-full min-h-0 flex-col gap-3 p-5">
      <audio
        ref={audio}
        onEnded={() => setPlaying(null)}
        onTimeUpdate={(e) => setProgress(e.currentTarget.duration ? e.currentTarget.currentTime / e.currentTarget.duration : 0)}
      />
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="grid gap-3 xl:grid-cols-2">
          {rows.map((r, i) => (
            <div key={i} className="flex items-center gap-4 rounded-2xl border border-line bg-surface-2 p-4">
              <button
                onClick={() => toggle(i)}
                className={clsx(
                  "focus-ring grid size-12 shrink-0 place-items-center rounded-full text-white shadow-lg transition",
                  playing === i ? "bg-gradient-to-b from-gold-300 to-gold-500 text-navy-950" : "bg-gradient-to-b from-navy-500 to-navy-800",
                )}
              >
                {playing === i ? <Pause className="size-5" /> : <Play className="ml-0.5 size-5" />}
              </button>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Mic className="size-3.5 text-rose-500" />
                  <span className="truncate text-[14.5px] font-semibold text-ink">{r.title}</span>
                  <span className="tabular ml-auto text-[12px] text-muted">{r.duration ? fmtDuration(r.duration) : ""}</span>
                </div>
                <div className="mt-2 flex h-6 items-center gap-[3px]">
                  {Array.from({ length: 48 }).map((_, b) => {
                    const h = 20 + 70 * Math.abs(Math.sin((b + 1) * 1.7 + i * 3) * Math.cos(b * 0.45));
                    const on = playing === i && b / 48 <= progress;
                    return <span key={b} className={clsx("w-[3px] rounded-full", on ? "bg-gold-500" : "bg-line-strong")} style={{ height: `${h}%` }} />;
                  })}
                </div>
                <div className="mt-1.5 flex items-center gap-2 text-[11.5px] text-faint">
                  <span className="tabular">{fmtDateTime(r.created)}</span>·<span>{fmtSize(r.size)}</span>·
                  <span className="truncate font-mono" title={r.sha256}>
                    SHA-256 {r.sha256.slice(0, 16)}…
                  </span>
                  <CopyButton value={r.sha256} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
export const VoiceView = () => <KindView<VoiceMemo> kind="voice">{(rows) => <Voice rows={rows} />}</KindView>;

/* ── Wi-Fi ─────────────────────────────────────────────────────────── */
function WifiNets({ rows }: { rows: WifiNetwork[] }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const filtered = rows.filter((r) => matches([r.ssid, r.bssid, r.security], q));
  const isOpen = (s: string) => !s || /open|none/i.test(s);
  return (
    <div className="card flex h-full min-h-0 flex-col gap-4 p-5">
      <Toolbar shown={filtered.length} total={rows.length}>
        <SearchBox value={q} onChange={setQ} />
      </Toolbar>
      <div className="min-h-0 flex-1 overflow-auto">
        {filtered.length === 0 ? (
          <EmptySearch />
        ) : (
          <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
            {filtered.map((w, i) => (
              <div key={i} className="group flex items-center gap-4 rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5">
                <span className={clsx("relative grid size-12 shrink-0 place-items-center rounded-2xl", isOpen(w.security) ? "bg-amber-50 text-amber-600 dark:bg-amber-500/15" : "bg-sky-50 text-sky-600 dark:bg-sky-500/15")}>
                  <Wifi className="size-6" />
                  <span className="absolute -right-1 -bottom-1 grid size-5 place-items-center rounded-full bg-surface shadow">
                    {isOpen(w.security) ? <LockOpen className="size-3 text-amber-600" /> : <Lock className="size-3 text-sky-600" />}
                  </span>
                </span>
                <div className="min-w-0 flex-1" data-selectable>
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[15px] font-semibold text-ink">{w.ssid}</span>
                    {w.hidden && (
                      <Badge tone="slate">
                        <EyeOff className="size-3" /> {t("wifi.hidden")}
                      </Badge>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <Badge tone={isOpen(w.security) ? "amber" : "blue"}>{isOpen(w.security) ? t("wifi.open") : w.security}</Badge>
                    {w.bssid && <span className="font-mono text-[11.5px] text-faint">{w.bssid}</span>}
                  </div>
                  {w.last_connected && (
                    <div className="tabular mt-1.5 text-[11.5px] text-muted">
                      {t("wifi.last")} {fmtDateTime(w.last_connected)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
export const WifiView = () => <KindView<WifiNetwork> kind="wifi">{(rows) => <WifiNets rows={rows} />}</KindView>;

/* ── SIM ───────────────────────────────────────────────────────────── */
const CARRIER_GRAD: Record<string, string> = {
  AIS: "from-[#7cc242] to-[#3d8b1f]",
  "TrueMove H": "from-[#ff4b4b] to-[#b5121b]",
  "TRUE-H": "from-[#ff4b4b] to-[#b5121b]",
  dtac: "from-[#3bb3ff] to-[#1565c0]",
  NT: "from-[#ffb341] to-[#d4791a]",
};

function Sims({ rows }: { rows: SimCard[] }) {
  const { t } = useI18n();
  return (
    <div className="card h-full min-h-0 overflow-auto p-6">
      <div className="grid gap-5 lg:grid-cols-2 2xl:grid-cols-3">
        {rows.map((s, i) => (
          <div
            key={i}
            className={clsx(
              "relative overflow-hidden rounded-[22px] bg-gradient-to-br p-5 text-white shadow-[0_18px_40px_-18px_rgba(8,19,41,0.55)]",
              CARRIER_GRAD[s.carrier] ?? "from-navy-600 to-navy-900",
              !s.active && "opacity-80 saturate-50",
            )}
            style={{ clipPath: "polygon(0 0, calc(100% - 38px) 0, 100% 38px, 100% 100%, 0 100%)" }}
            data-selectable
          >
            <div className="absolute -right-10 -bottom-16 size-48 rounded-full bg-white/10" />
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[12px] font-semibold text-white/75">{s.slot}</div>
                <div className="font-display text-[22px] font-bold">{s.carrier || s.display_name || "SIM"}</div>
              </div>
              <span className={clsx("mr-8 rounded-full px-2.5 py-1 text-[11.5px] font-bold", s.active ? "bg-white text-emerald-700" : "bg-black/25 text-white")}>
                {s.active ? t("sim.active") : t("sim.inactive")}
              </span>
            </div>
            <SimChipIcon className="mt-4 h-9 w-12" />
            <div className="tabular mt-3 font-display text-[22px] font-semibold tracking-wide">{s.number || "—"}</div>
            <div className="mt-3 grid grid-cols-[52px_1fr] gap-y-1 font-mono text-[12px] text-white/85">
              <span className="text-white/60">ICCID</span>
              <span className="truncate">{s.iccid || "—"}</span>
              <span className="text-white/60">IMSI</span>
              <span className="truncate">{s.imsi || "—"}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
export const SimView = () => <KindView<SimCard> kind="sim">{(rows) => <Sims rows={rows} />}</KindView>;

/* ── Apps ──────────────────────────────────────────────────────────── */
function Apps({ rows }: { rows: App[] }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [kind, setKind] = useState<"all" | "user" | "system">("user");
  const user = rows.filter((r) => !r.system).length;
  const filtered = useMemo(
    () => rows.filter((r) => (kind === "all" || (kind === "system") === r.system) && matches([r.name, r.package, r.version], q)),
    [rows, q, kind],
  );
  const columns: Column<App>[] = [
    {
      key: "name",
      header: t("col.app"),
      width: "1.3fr",
      render: (r) => (
        <span className="flex items-center gap-3">
          <span className={clsx("grid size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br text-[14px] font-bold text-white shadow", avatarColor(r.package))}>
            {(r.name || r.package.split(".").pop() || "?")[0].toUpperCase()}
          </span>
          <span className="truncate font-semibold">{r.name || r.package.split(".").pop()}</span>
        </span>
      ),
      sort: (r) => (r.name || r.package).toLowerCase(),
    },
    { key: "pkg", header: t("col.package"), width: "1.6fr", render: (r) => <span className="font-mono text-[12.5px] text-ink-2">{r.package}</span>, sort: (r) => r.package },
    { key: "ver", header: t("col.version"), width: "120px", render: (r) => <span className="tabular text-ink-2">{r.version}</span> },
    { key: "inst", header: t("col.installed"), width: "170px", render: (r) => <span className="tabular text-ink-2">{fmtDateTime(r.installed)}</span>, sort: (r) => r.installed ?? 0 },
    {
      key: "kind",
      header: t("col.kind"),
      width: "96px",
      render: (r) => (r.system ? <Badge tone="slate">{t("apps.system")}</Badge> : <Badge tone="green"><ShieldCheck className="size-3" /> {t("apps.user")}</Badge>),
    },
  ];
  return (
    <div className="card flex h-full min-h-0 flex-col gap-3 p-5">
      <Toolbar shown={filtered.length} total={rows.length}>
        <SearchBox value={q} onChange={setQ} />
        <Chip active={kind === "user"} onClick={() => setKind("user")} count={user}>
          <AppWindow className="size-3.5" /> {t("apps.user")}
        </Chip>
        <Chip active={kind === "system"} onClick={() => setKind("system")} count={rows.length - user}>
          {t("apps.system")}
        </Chip>
        <Chip active={kind === "all"} onClick={() => setKind("all")} count={rows.length}>
          {t("tb.all")}
        </Chip>
      </Toolbar>
      <DataTable rows={filtered} columns={columns} empty={<EmptySearch />} rowHeight={56} />
    </div>
  );
}
export const AppsView = () => <KindView<App> kind="apps">{(rows) => <Apps rows={rows} />}</KindView>;
