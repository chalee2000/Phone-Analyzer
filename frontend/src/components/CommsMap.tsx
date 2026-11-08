import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Globe, Map as MapIcon, Pause, Play, SkipBack } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import provinces from "../assets/thailand-provinces.json";
import type { CommRow, GeoPoint } from "../lib/analysis";
import { fmtDateTime } from "../lib/format";
import { useI18n } from "../lib/i18n";

export interface MapPoint {
  id: string;
  lat: number;
  lon: number;
  ts: number | null;
  color: string;
  azimuth?: number | null;
  site?: string;
  label: string;
  kind: "cell" | "photo";
}

/** Points to draw for the current query result: cell sites from CDR rows + photo GPS. */
export function toMapPoints(rows: CommRow[], geo: GeoPoint[], colorOf: (device: string) => string): MapPoint[] {
  const out: MapPoint[] = [];
  for (const r of rows) {
    if (r.lat != null && r.lon != null) {
      out.push({ id: r.id, lat: r.lat, lon: r.lon, ts: r.ts, color: colorOf(r.device), azimuth: r.azimuth, site: r.site, label: `${r.name || r.number} · ${r.site || r.cell || ""}`, kind: "cell" });
    }
  }
  for (const g of geo) out.push({ id: g.id, lat: g.lat, lon: g.lon, ts: g.ts, color: colorOf(g.device), label: g.label, kind: "photo" });
  return out.sort((a, b) => (a.ts ?? 0) - (b.ts ?? 0));
}

/** Wedge polygon for a cell sector: centre, azimuth (deg, 0 = north), beam width, radius (m). */
function sector(lat: number, lon: number, azimuth: number, radius: number, beam = 120): L.LatLngExpression[] {
  const pts: L.LatLngExpression[] = [[lat, lon]];
  const r = radius / 111_320;
  for (let a = azimuth - beam / 2; a <= azimuth + beam / 2; a += 6) {
    const rad = (a * Math.PI) / 180;
    pts.push([lat + r * Math.cos(rad), lon + (r * Math.sin(rad)) / Math.cos((lat * Math.PI) / 180)]);
  }
  pts.push([lat, lon]);
  return pts;
}

export function CommsMap({ points, focusId, onPick }: { points: MapPoint[]; focusId: string | null; onPick: (id: string) => void }) {
  const { t } = useI18n();
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const playLayer = useRef<L.LayerGroup | null>(null);
  const base = useRef<{ online: L.TileLayer; offline: L.GeoJSON } | null>(null);
  const [online, setOnline] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [zoom, setZoom] = useState(10);

  useEffect(() => {
    if (!el.current) return;
    const m = L.map(el.current, { zoomControl: true, attributionControl: true, preferCanvas: true }).setView([13.75, 100.55], 10);
    const offline = L.geoJSON(provinces as GeoJSON.FeatureCollection, {
      style: { color: "#3b5ea8", weight: 1, fillColor: "#13254d", fillOpacity: 0.55 },
      onEachFeature: (f, l) => l.bindTooltip(String(f.properties?.name ?? ""), { sticky: true, className: "map-tip" }),
    });
    const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" });
    offline.addTo(m);
    m.attributionControl.addAttribution("Natural Earth");
    base.current = { online: tiles, offline };
    layer.current = L.layerGroup().addTo(m);
    playLayer.current = L.layerGroup().addTo(m);
    map.current = m;
    m.on("zoomend", () => setZoom(m.getZoom()));
    const ro = new ResizeObserver(() => m.invalidateSize());
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      m.remove();
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    const b = base.current;
    if (!m || !b) return;
    if (online) {
      b.offline.remove();
      b.online.addTo(m);
    } else {
      b.online.remove();
      b.offline.addTo(m);
    }
  }, [online]);

  // Aggregate cell sites so each sector is drawn once, sized by its count.
  const sites = useMemo(() => {
    const m = new Map<string, MapPoint & { n: number }>();
    for (const p of points) {
      const key = p.kind === "cell" ? `${p.lat.toFixed(3)},${p.lon.toFixed(3)},${p.azimuth ?? "x"},${p.color}` : p.id;
      const cur = m.get(key);
      if (cur) cur.n++;
      else m.set(key, { ...p, n: 1 });
    }
    return [...m.values()];
  }, [points]);

  // Draw sites; sector size is in screen pixels so wedges stay readable at any zoom.
  useEffect(() => {
    const m = map.current;
    const g = layer.current;
    if (!m || !g) return;
    g.clearLayers();
    const metersPerPx = (40075016 * Math.cos((m.getCenter().lat * Math.PI) / 180)) / 2 ** (zoom + 8);
    for (const s of sites) {
      if (s.kind === "cell") {
        const radius = (22 + Math.min(30, Math.sqrt(s.n) * 4)) * metersPerPx;
        if (s.azimuth != null) {
          L.polygon(sector(s.lat, s.lon, s.azimuth, radius), { color: s.color, weight: 1.5, fillColor: s.color, fillOpacity: 0.28 })
            .bindTooltip(`${s.site ?? ""} · ${s.azimuth}° · ${s.n}`)
            .on("click", () => onPick(s.id))
            .addTo(g);
        }
        L.circleMarker([s.lat, s.lon], { radius: 4, color: "#0b1636", weight: 1, fillColor: s.color, fillOpacity: 1 }).addTo(g);
      } else {
        L.circleMarker([s.lat, s.lon], { radius: 6, color: "#fff", weight: 2, fillColor: s.color, fillOpacity: 0.95 })
          .bindTooltip(`📷 ${s.label}`)
          .on("click", () => onPick(s.id))
          .addTo(g);
      }
    }
  }, [sites, zoom, onPick]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    // Frame the cell sites when there are any (photos may be spread over the whole country).
    const frame = sites.some((s) => s.kind === "cell") ? sites.filter((s) => s.kind === "cell") : sites;
    if (frame.length) {
      const bounds = L.latLngBounds(frame.map((s) => [s.lat, s.lon] as L.LatLngTuple));
      m.fitBounds(bounds.pad(0.25), { maxZoom: 14 });
      setZoom(m.getZoom());
    }
    setCursor(0);
    setPlaying(false);
  }, [sites]);

  // Playback: walk through located events in time order.
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => setCursor((c) => (c + 1 >= points.length ? (setPlaying(false), c) : c + 1)), 450);
    return () => window.clearInterval(id);
  }, [playing, points.length]);

  useEffect(() => {
    const g = playLayer.current;
    if (!g) return;
    g.clearLayers();
    if (!points.length || (!playing && cursor === 0)) return;
    const trail = points.slice(Math.max(0, cursor - 12), cursor + 1);
    L.polyline(trail.map((p) => [p.lat, p.lon] as L.LatLngTuple), { color: "#f2c14e", weight: 3, opacity: 0.85, dashArray: "6 6" }).addTo(g);
    const p = points[cursor];
    L.circleMarker([p.lat, p.lon], { radius: 10, color: "#f2c14e", weight: 3, fillColor: p.color, fillOpacity: 1 }).addTo(g);
    map.current?.panTo([p.lat, p.lon], { animate: true });
  }, [cursor, playing, points]);

  useEffect(() => {
    if (!focusId || !map.current) return;
    const p = points.find((x) => x.id === focusId);
    if (p) {
      map.current.setView([p.lat, p.lon], Math.max(map.current.getZoom(), 14), { animate: true });
      const g = playLayer.current!;
      g.clearLayers();
      L.circleMarker([p.lat, p.lon], { radius: 11, color: "#22d3ee", weight: 3, fillOpacity: 0 }).addTo(g);
    }
  }, [focusId, points]);

  const current = points[cursor];
  return (
    <div className="relative isolate h-full w-full overflow-hidden rounded-b-[1.15rem] bg-[#0a1430]">
      <div className="absolute inset-0">
        <div ref={el} className="h-full w-full" data-testid="comms-map" />
      </div>
      <div className="absolute top-3 right-3 z-[500] flex gap-1 rounded-xl bg-[#0b1636]/90 p-1 text-[12px] text-white shadow-lg backdrop-blur">
        <button onClick={() => setOnline(false)} className={`flex items-center gap-1 rounded-lg px-2.5 py-1 ${!online ? "bg-gold-400 text-navy-950" : "hover:bg-white/10"}`}>
          <MapIcon className="size-3.5" /> Offline
        </button>
        <button onClick={() => setOnline(true)} className={`flex items-center gap-1 rounded-lg px-2.5 py-1 ${online ? "bg-gold-400 text-navy-950" : "hover:bg-white/10"}`}>
          <Globe className="size-3.5" /> OSM
        </button>
      </div>
      <div className="absolute right-3 bottom-3 left-3 z-[500] flex items-center gap-3 rounded-xl bg-[#0b1636]/90 px-3 py-2 text-[12px] text-white shadow-lg backdrop-blur">
        <button onClick={() => (setCursor(0), setPlaying(false))} className="rounded-lg p-1 hover:bg-white/10" title={t("diag.restart")}>
          <SkipBack className="size-4" />
        </button>
        <button onClick={() => setPlaying((p) => !p)} disabled={!points.length} className="flex items-center gap-1.5 rounded-lg bg-gold-400 px-3 py-1 font-semibold text-navy-950 disabled:opacity-40" data-testid="map-play">
          {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} {playing ? t("cm.pause") : t("cm.play")}
        </button>
        <input type="range" min={0} max={Math.max(0, points.length - 1)} value={cursor} onChange={(e) => setCursor(Number(e.target.value))} className="flex-1 accent-[#dca22a]" />
        <span className="tabular w-56 truncate text-right text-slate-300">{points.length ? `${fmtDateTime(current?.ts)} · ${cursor + 1}/${points.length}` : t("cm.noGeo")}</span>
      </div>
    </div>
  );
}
