import clsx from "clsx";
import { Camera, ChevronLeft, ChevronRight, Clock, ExternalLink, FileImage, Folder, Hash, HardDrive, ImageOff, MapPin, Maximize2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { CopyButton } from "../components/DevicePanel";
import { SearchBox, Toolbar } from "../components/DataTable";
import { EmptySearch, KindView } from "../components/States";
import { toast } from "sonner";
import { Button, Chip } from "../components/ui";
import { call } from "../lib/bridge";
import { fmtDateTime, fmtMonth, fmtSize, matches } from "../lib/format";
import { useI18n } from "../lib/i18n";
import type { Photo } from "../lib/types";
import { useMediaUrl } from "./MiscViews";

// Browsers cannot draw these; the JPEG thumbnail stands in for the original.
const NOT_DISPLAYABLE = /\.(heic|heif|dng)$/i;
let reported = false;

async function openInViewer(rel: string, failed = false) {
  try {
    const info = await call<{ path: string; exists: boolean }>("media_probe", rel, failed);
    if (info.exists) await call("open_file", info.path);
  } catch {
    /* the toast below already told the examiner */
  }
}

/** A case image that degrades to a clear "cannot display" tile (and tells support why). */
export function MediaImage({ rel, alt, className, lazy }: { rel: string; alt: string; className?: string; lazy?: boolean }) {
  const { t } = useI18n();
  const media = useMediaUrl();
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [rel]);
  if (failed)
    return (
      <span className={clsx("flex flex-col items-center justify-center gap-1 bg-surface-3 p-2 text-center text-[11px] text-muted", className)} data-testid="photo-broken">
        <ImageOff className="size-5 text-faint" />
        {t("photos.broken")}
      </span>
    );
  return (
    <img
      src={media(rel)}
      alt={alt}
      loading={lazy ? "lazy" : undefined}
      className={className}
      onError={() => {
        setFailed(true);
        if (reported) return;
        reported = true;
        void call<{ path: string; exists: boolean; log: string }>("media_probe", rel, true)
          .then((info) =>
            toast.warning(t("photos.brokenToast"), {
              description: info.log ? t("photos.brokenLog", { log: info.log }) : undefined,
              action: info.exists ? { label: t("photos.openFile"), onClick: () => void call("open_file", info.path) } : undefined,
              duration: 15000,
            }),
          )
          .catch(() => toast.warning(t("photos.brokenToast")));
      }}
    />
  );
}

function Meta({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 border-b border-line/70 py-2.5 last:border-0">
      <span className="mt-0.5 text-faint">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="text-[11.5px] text-muted">{label}</div>
        <div className="text-[13.5px] break-all text-ink" data-selectable>
          {children}
        </div>
      </div>
    </div>
  );
}

function Lightbox({ photos, index, onClose, onMove }: { photos: Photo[]; index: number; onClose: () => void; onMove: (i: number) => void }) {
  const { t } = useI18n();
  const p = photos[index];
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") onMove(Math.min(photos.length - 1, index + 1));
      if (e.key === "ArrowLeft") onMove(Math.max(0, index - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, photos.length, onClose, onMove]);
  return (
    <motion.div className="fixed inset-0 z-40 flex bg-navy-950/92 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="lightbox">
      <div className="relative flex min-w-0 flex-1 items-center justify-center p-10">
        <MediaImage rel={NOT_DISPLAYABLE.test(p.path) && p.thumb ? p.thumb : p.path} alt={p.name} className="max-h-full max-w-full rounded-xl object-contain shadow-2xl" />
        <button onClick={() => onMove(Math.max(0, index - 1))} disabled={index === 0} className="absolute left-4 grid size-12 place-items-center rounded-full bg-white/10 text-white hover:bg-white/20 disabled:opacity-30">
          <ChevronLeft className="size-6" />
        </button>
        <button
          onClick={() => onMove(Math.min(photos.length - 1, index + 1))}
          disabled={index === photos.length - 1}
          className="absolute right-4 grid size-12 place-items-center rounded-full bg-white/10 text-white hover:bg-white/20 disabled:opacity-30"
        >
          <ChevronRight className="size-6" />
        </button>
        <span className="tabular absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/40 px-3 py-1 text-[12px] text-white/80">
          {index + 1} / {photos.length}
        </span>
      </div>
      <aside className="flex w-[360px] shrink-0 flex-col bg-surface">
        <div className="flex items-center gap-2 border-b border-line px-5 py-4">
          <FileImage className="size-5 text-navy-500 dark:text-gold-300" />
          <span className="min-w-0 flex-1 truncate font-display text-[16px] font-semibold text-ink">{p.name}</span>
          <Button size="sm" variant="ghost" icon={<ExternalLink className="size-4" />} onClick={() => void openInViewer(p.path)} title={t("photos.openFile")} />
          <button onClick={onClose} className="grid size-9 place-items-center rounded-xl text-muted hover:bg-surface-3">
            <X className="size-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto px-5 py-2">
          <Meta icon={<Clock className="size-4" />} label={t("photos.taken")}>
            {fmtDateTime(p.taken)}
          </Meta>
          {(p.make || p.camera_model) && (
            <Meta icon={<Camera className="size-4" />} label={t("photos.camera")}>
              {p.make} {p.camera_model}
            </Meta>
          )}
          {p.width && (
            <Meta icon={<Maximize2 className="size-4" />} label={t("photos.resolution")}>
              {p.width} × {p.height}
            </Meta>
          )}
          <Meta icon={<HardDrive className="size-4" />} label={t("photos.size")}>
            {fmtSize(p.size)}
          </Meta>
          {p.lat != null && (
            <Meta icon={<MapPin className="size-4 text-rose-500" />} label={t("photos.coords")}>
              <span className="flex items-center gap-1 font-mono">
                {p.lat.toFixed(6)}, {p.lon?.toFixed(6)} <CopyButton value={`${p.lat}, ${p.lon}`} />
              </span>
            </Meta>
          )}
          <Meta icon={<Folder className="size-4" />} label={t("photos.source")}>
            <span className="font-mono text-[12px]">{p.source_path}</span>
          </Meta>
          <Meta icon={<Hash className="size-4 text-emerald-500" />} label="SHA-256">
            <span className="flex items-start gap-1 font-mono text-[11.5px]">
              {p.sha256} <CopyButton value={p.sha256} />
            </span>
          </Meta>
        </div>
      </aside>
    </motion.div>
  );
}

function Photos({ rows }: { rows: Photo[] }) {
  const { t, lang } = useI18n();
  const [q, setQ] = useState("");
  const [album, setAlbum] = useState("all");
  const [gpsOnly, setGpsOnly] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const albums = useMemo(() => {
    const m = new Map<string, number>();
    rows.forEach((r) => m.set(r.album, (m.get(r.album) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);
  const filtered = useMemo(
    () => rows.filter((r) => (album === "all" || r.album === album) && (!gpsOnly || r.lat != null) && matches([r.name, r.album, r.camera_model], q)),
    [rows, album, gpsOnly, q],
  );
  const groups = useMemo(() => {
    const out: { label: string; items: { p: Photo; i: number }[] }[] = [];
    filtered.forEach((p, i) => {
      const month = p.taken ? fmtMonth(p.taken, lang) : "—";
      if (!out.length || out[out.length - 1].label !== month) out.push({ label: month, items: [] });
      out[out.length - 1].items.push({ p, i });
    });
    return out;
  }, [filtered, lang]);
  const withGps = rows.filter((r) => r.lat != null).length;

  return (
    <div className="card flex h-full min-h-0 flex-col gap-4 p-5">
      <Toolbar shown={filtered.length} total={rows.length}>
        <SearchBox value={q} onChange={setQ} />
        <Chip active={album === "all"} onClick={() => setAlbum("all")} count={rows.length}>
          {t("tb.all")}
        </Chip>
        {albums.slice(0, 6).map(([a, n]) => (
          <Chip key={a} active={album === a} onClick={() => setAlbum(a)} count={n}>
            {a}
          </Chip>
        ))}
        {withGps > 0 && (
          <Chip active={gpsOnly} onClick={() => setGpsOnly((v) => !v)} count={withGps}>
            <MapPin className="size-3.5" /> {t("photos.gps")}
          </Chip>
        )}
      </Toolbar>
      <div className="min-h-0 flex-1 overflow-auto pr-1" data-testid="photo-grid">
        {filtered.length === 0 && <EmptySearch />}
        {groups.map((g) => (
          <section key={g.label} className="mb-5">
            <h4 className="sticky top-0 z-10 mb-2 bg-surface/90 py-1 font-display text-[15px] font-semibold text-ink backdrop-blur">{g.label}</h4>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2.5">
              {g.items.map(({ p, i }) => (
                <button
                  key={p.sha256 + i}
                  onClick={() => setOpen(i)}
                  className="group focus-ring relative aspect-square overflow-hidden rounded-xl bg-surface-3"
                >
                  <MediaImage rel={p.thumb || p.path} alt={p.name} lazy className="size-full object-cover transition duration-300 group-hover:scale-105" />
                  <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-2 pt-6 pb-1.5 text-left text-[11px] text-white opacity-0 transition group-hover:opacity-100">
                    <span className="tabular block">{fmtDateTime(p.taken)}</span>
                  </span>
                  {p.lat != null && (
                    <span className={clsx("absolute top-1.5 right-1.5 grid size-6 place-items-center rounded-full bg-black/45 text-white")}>
                      <MapPin className="size-3.5" />
                    </span>
                  )}
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>
      <AnimatePresence>{open != null && <Lightbox photos={filtered} index={open} onClose={() => setOpen(null)} onMove={setOpen} />}</AnimatePresence>
    </div>
  );
}

export function PhotosView() {
  return <KindView<Photo> kind="photos">{(rows) => <Photos rows={rows} />}</KindView>;
}
