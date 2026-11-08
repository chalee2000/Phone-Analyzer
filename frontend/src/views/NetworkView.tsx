import { useVirtualizer } from "@tanstack/react-virtual";
import clsx from "clsx";
import cytoscape, { type Core, type ElementDefinition, type LayoutOptions } from "cytoscape";
import fcose from "cytoscape-fcose";
import {
  Circle,
  Crosshair,
  Download,
  Eye,
  EyeOff,
  Focus,
  ImageDown,
  Layers,
  Link as LinkIcon,
  Maximize2,
  Network,
  Orbit,
  Redo2,
  Route,
  Save,
  Search,
  Shuffle,
  Trash2,
  Undo2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { AnalysisEmpty, Panel } from "../components/AnalysisEmpty";
import { CopyButton } from "../components/DevicePanel";
import { Badge, Button, Field, Input, Modal, ModalHeader, Spinner, Switch, Tooltip } from "../components/ui";
import { DEVICE_COLORS, ENTITY_META, iconDataUri, iconSvg, type NetEdge, type NetGraph, type NetNode } from "../lib/analysis";
import { call } from "../lib/bridge";
import { fmtDateTime, fmtDuration } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";

cytoscape.use(fcose);

const COMMUNITY_COLORS = ["#38bdf8", "#f2c14e", "#34d399", "#f472b6", "#a78bfa", "#fb923c", "#22d3ee", "#facc15", "#4ade80", "#f87171", "#818cf8", "#2dd4bf", "#e879f9", "#a3e635"];
const EDGE_COLORS: Record<string, string> = {
  comm: "#38bdf8", chat: "#34d399", own: "#f2c14e", sim: "#f59e0b", number: "#64748b", account: "#a78bfa",
  wifi: "#818cf8", location: "#fb7185", member: "#0ea5e9", saved: "#475569", manual: "#e2e8f0",
};
const PALETTE = ["person", "phone", "vehicle", "address", "bank", "organization", "location", "event"];

interface Options {
  extractions: string[] | null;
  persons: boolean;
  hide_services: boolean;
  contacts_only: boolean;
  wifi: boolean;
  locations: boolean;
  min_weight: number;
}

type ColorBy = "type" | "community" | "device";

function nodeSize(n: NetNode) {
  if (n.type === "device") return 66;
  return Math.min(56, 22 + 7 * Math.log2(1 + n.metrics.strength));
}

function TypeIcon({ type, size = 16 }: { type: string; size?: number }) {
  const meta = ENTITY_META[type] ?? ENTITY_META.other;
  return (
    <span className="grid shrink-0 place-items-center rounded-full" style={{ width: size + 10, height: size + 10, background: meta.color }}>
      <span style={{ width: size, height: size }} dangerouslySetInnerHTML={{ __html: iconSvg(meta.icon, "#fff", size, 2.2) }} />
    </span>
  );
}

function ToolButton({ icon, label, onClick, disabled, active }: { icon: ReactNode; label: string; onClick: () => void; disabled?: boolean; active?: boolean }) {
  return (
    <Tooltip label={label}>
      <button
        onClick={onClick}
        disabled={disabled}
        className={clsx(
          "focus-ring flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-[12.5px] font-semibold transition disabled:opacity-35",
          active ? "bg-gold-400 text-navy-950" : "text-slate-200 hover:bg-white/10",
        )}
      >
        {icon}
        <span className="hidden 2xl:inline">{label}</span>
      </button>
    </Tooltip>
  );
}

export function NetworkView() {
  const { state } = useStore();
  if (!state.case || !state.case.extraction_count) return <AnalysisEmpty icon={<Network />} />;
  return <NetworkWorkspace />;
}

function NetworkWorkspace() {
  const { t } = useI18n();
  const { state, exportNetwork, errorText } = useStore();
  const [options, setOptions] = useState<Options>({ extractions: null, persons: true, hide_services: true, contacts_only: false, wifi: true, locations: true, min_weight: 1 });
  const [graph, setGraph] = useState<NetGraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [commonOnly, setCommonOnly] = useState(false);
  const [colorBy, setColorBy] = useState<ColorBy>("type");
  const [hidden, setHidden] = useState<string[]>([]);
  const [history, setHistory] = useState<{ past: string[][]; future: string[][] }>({ past: [], future: [] });
  const [selected, setSelected] = useState<string[]>([]);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [rightTab, setRightTab] = useState<"list" | "details" | "insights">("insights");
  const [query, setQuery] = useState("");
  const [matchIndex, setMatchIndex] = useState(0);
  const [layout, setLayout] = useState<"organic" | "radial" | "grouped" | "circle">("organic");
  const [addType, setAddType] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const container = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const savedPositions = useRef<Record<string, { x: number; y: number }> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setGraph(await call<NetGraph>("network_graph", options));
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setLoading(false);
    }
  }, [options, errorText]);

  useEffect(() => {
    void load();
  }, [load, state.case?.id, state.case?.extraction_count]);

  useEffect(() => {
    void call<Record<string, { x: number; y: number }>>("network_load_layout").then((p) => {
      savedPositions.current = p && Object.keys(p).length ? p : null;
    });
  }, [state.case?.id]);

  const nodesById = useMemo(() => new Map((graph?.nodes ?? []).map((n) => [n.id, n])), [graph]);
  const visibleNodes = useMemo(() => {
    if (!graph) return [];
    const hid = new Set(hidden);
    return graph.nodes.filter((n) => !hiddenTypes.has(n.type) && !hid.has(n.id) && (!commonOnly || n.common || n.type === "device"));
  }, [graph, hiddenTypes, hidden, commonOnly]);
  const visibleIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes]);
  const visibleEdges = useMemo(() => (graph?.edges ?? []).filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target)), [graph, visibleIds]);

  const colorOf = useCallback(
    (n: NetNode) => {
      if (colorBy === "community") return COMMUNITY_COLORS[n.metrics.community % COMMUNITY_COLORS.length];
      if (colorBy === "device") {
        if (n.common) return "#f472b6";
        const d = graph?.devices.find((x) => x.id === n.devices[0]);
        return d ? DEVICE_COLORS[d.index % DEVICE_COLORS.length] : "#64748b";
      }
      return (ENTITY_META[n.type] ?? ENTITY_META.other).color;
    },
    [colorBy, graph],
  );

  // ── cytoscape lifecycle ─────────────────────────────────────────────
  useEffect(() => {
    if (!container.current) return;
    const cy = cytoscape({
      container: container.current,
      minZoom: 0.05,
      maxZoom: 3,
      boxSelectionEnabled: true,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            "background-image": "data(icon)",
            "background-width": "56%",
            "background-height": "56%",
            width: "data(size)",
            height: "data(size)",
            label: "data(label)",
            color: "#cbd5e1",
            "font-size": 10.5,
            "font-family": "IBM Plex Sans Thai, Leelawadee UI, sans-serif",
            "text-valign": "bottom",
            "text-margin-y": 5,
            "text-outline-color": "#081129",
            "text-outline-width": 2.5,
            "text-max-width": "130px",
            "text-wrap": "ellipsis",
            "border-width": 2,
            "border-color": "#0b1636",
            "min-zoomed-font-size": 7,
          },
        },
        { selector: "node[type = 'device']", style: { "border-width": 5, "border-color": "#f2c14e", "font-size": 13, "font-weight": 600, color: "#fde68a" } },
        { selector: "node.common", style: { "border-color": "#f472b6", "border-width": 3.5 } },
        { selector: "node.tagged", style: { "border-color": "#fde047", "border-width": 4, "border-style": "double" } },
        { selector: "node:selected", style: { "border-color": "#ffffff", "border-width": 4, "overlay-color": "#f2c14e", "overlay-opacity": 0.2, "overlay-padding": 6 } },
        {
          selector: "edge",
          style: {
            width: "data(width)",
            "line-color": "data(color)",
            "curve-style": "bezier",
            opacity: 0.55,
            "font-size": 9.5,
            color: "#e2e8f0",
            "text-rotation": "autorotate",
            "text-background-color": "#081129",
            "text-background-opacity": 0.85,
            "text-background-padding": "2px",
            "font-family": "IBM Plex Sans Thai, sans-serif",
          },
        },
        { selector: "edge[type = 'manual']", style: { "line-style": "dashed", label: "data(label)", opacity: 0.9 } },
        { selector: "edge:selected", style: { "line-color": "#f2c14e", opacity: 1, label: "data(label)", "z-index": 30 } },
        { selector: ".faded", style: { opacity: 0.08, "text-opacity": 0.05 } },
        { selector: "edge.lit", style: { opacity: 0.95, label: "data(label)", "z-index": 20 } },
        { selector: "node.match", style: { "border-color": "#22d3ee", "border-width": 6 } },
        { selector: ".path", style: { "line-color": "#22d3ee", "border-color": "#22d3ee", "border-width": 6, width: 7, opacity: 1, "z-index": 40, label: "data(label)" } },
      ],
    });
    cy.on("select unselect", () => setSelected(cy.$(":selected").map((e) => e.id())));
    cy.on("tap", "node, edge", (evt) => {
      const el = evt.target;
      setFocusId(el.id());
      setRightTab("details");
      cy.elements().removeClass("path");
      const hood = el.isNode() ? el.closedNeighborhood() : el.union(el.connectedNodes());
      cy.elements().addClass("faded");
      hood.removeClass("faded");
      hood.edges().addClass("lit");
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass("faded lit path");
        setFocusId(null);
      }
    });
    cy.on("zoom", () => setZoom(cy.zoom()));
    cyRef.current = cy;
    (window as unknown as { __cy?: Core }).__cy = cy; // used by UI tests
    return () => cy.destroy();
  }, []);

  const runLayout = useCallback(
    (name: typeof layout, animate = true) => {
      const cy = cyRef.current;
      if (!cy || !cy.nodes().length) return;
      let opts: LayoutOptions;
      if (name === "radial") {
        opts = {
          name: "concentric",
          concentric: (n: cytoscape.NodeSingular) => (n.data("type") === "device" ? 1e6 : n.data("strength")),
          levelWidth: () => 6,
          minNodeSpacing: 18,
          animate,
        } as LayoutOptions;
      } else if (name === "circle") {
        opts = { name: "circle", sort: (a: cytoscape.NodeSingular, b: cytoscape.NodeSingular) => a.data("community") - b.data("community"), animate } as LayoutOptions;
      } else if (name === "grouped") {
        const groups = new Map<number, cytoscape.NodeSingular[]>();
        cy.nodes().forEach((n) => {
          const c = n.data("community") as number;
          groups.set(c, [...(groups.get(c) ?? []), n]);
        });
        const list = [...groups.values()].sort((a, b) => b.length - a.length);
        const cols = Math.ceil(Math.sqrt(list.length));
        const cell = Math.max(320, Math.sqrt(Math.max(...list.map((g) => g.length))) * 110);
        const pos: Record<string, { x: number; y: number }> = {};
        list.forEach((members, gi) => {
          const cx = (gi % cols) * cell;
          const cyy = Math.floor(gi / cols) * cell;
          members.sort((a, b) => b.data("strength") - a.data("strength"));
          members.forEach((n, i) => {
            if (i === 0) return void (pos[n.id()] = { x: cx, y: cyy });
            const ring = Math.ceil((Math.sqrt(1 + (4 * i) / 3) - 1) / 2);
            const inRing = 6 * ring;
            const idx = i - (3 * ring * (ring - 1) + 1);
            const ang = (2 * Math.PI * idx) / inRing;
            pos[n.id()] = { x: cx + Math.cos(ang) * ring * 70, y: cyy + Math.sin(ang) * ring * 70 };
          });
        });
        opts = { name: "preset", positions: (n: cytoscape.NodeSingular) => pos[n.id()], animate } as LayoutOptions;
      } else {
        opts = {
          name: "fcose",
          quality: "default",
          randomize: true,
          animate,
          animationDuration: 650,
          nodeRepulsion: () => 9000,
          idealEdgeLength: () => 85,
          edgeElasticity: () => 0.35,
          gravity: 0.3,
          numIter: 2500,
          nodeSeparation: 90,
          packComponents: true,
        } as unknown as LayoutOptions;
      }
      cy.layout(opts).run();
      setLayout(name);
    },
    [],
  );

  // Push the visible graph into cytoscape.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !graph) return;
    const prev = new Map(cy.nodes().map((n) => [n.id(), { ...n.position() }]));
    const elements: ElementDefinition[] = [
      ...visibleNodes.map((n) => {
        const meta = ENTITY_META[n.type] ?? ENTITY_META.other;
        return {
          group: "nodes" as const,
          data: {
            id: n.id,
            label: n.label + (n.type === "phone" && n.sub && n.sub !== n.label ? `\n${n.sub}` : ""),
            type: n.type,
            color: colorOf(n),
            icon: iconDataUri(meta.icon),
            size: nodeSize(n),
            strength: n.metrics.strength,
            community: n.metrics.community,
          },
          classes: [n.common ? "common" : "", n.tags?.length || n.note ? "tagged" : ""].join(" "),
        };
      }),
      ...visibleEdges.map((e) => ({
        group: "edges" as const,
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          type: e.type,
          label: e.label || t(`edge.${e.type}`),
          color: EDGE_COLORS[e.type] ?? "#64748b",
          width: Math.min(9, 1.2 + Math.log2(e.weight) * 1.3),
        },
      })),
    ];
    cy.batch(() => {
      cy.elements().remove();
      cy.add(elements);
    });
    cy.style().selector("node").style("text-wrap", "wrap").update();
    const saved = savedPositions.current;
    const known = cy.nodes().filter((n) => prev.has(n.id()) || !!saved?.[n.id()]);
    if (known.length >= cy.nodes().length * 0.6) {
      cy.nodes().forEach((n) => {
        const p = prev.get(n.id()) ?? saved?.[n.id()];
        if (p) n.position(p);
      });
      const fresh = cy.nodes().filter((n) => !prev.has(n.id()) && !saved?.[n.id()]);
      fresh.forEach((n) => {
        const nb = n.neighborhood("node").filter((x) => x.id() !== n.id())[0];
        const base = nb ? nb.position() : { x: 0, y: 0 };
        n.position({ x: base.x + (Math.random() - 0.5) * 160, y: base.y + (Math.random() - 0.5) * 160 });
      });
      if (!prev.size) cy.fit(undefined, 40);
    } else {
      runLayout(layout, false);
      cy.fit(undefined, 40);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, visibleNodes, visibleEdges, colorOf, t]);

  // search
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return visibleNodes.filter((n) => [n.label, n.sub, n.props.number, ...(n.props.names ?? [])].some((v) => v && String(v).toLowerCase().includes(q))).map((n) => n.id);
  }, [query, visibleNodes]);
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("match");
    matches.forEach((id) => cy.getElementById(id).addClass("match"));
    if (matches.length) {
      const el = cy.getElementById(matches[Math.min(matchIndex, matches.length - 1)]);
      cy.animate({ center: { eles: el }, zoom: Math.max(cy.zoom(), 0.9) }, { duration: 300 });
    }
  }, [matches, matchIndex]);

  // ── actions ─────────────────────────────────────────────────────────
  const pushHidden = (next: string[]) => {
    setHistory((h) => ({ past: [...h.past, hidden], future: [] }));
    setHidden(next);
  };
  const selectNode = (id: string) => {
    const cy = cyRef.current;
    if (!cy) return;
    const el = cy.getElementById(id);
    if (!el.length) return;
    cy.$(":selected").unselect();
    el.select();
    el.emit("tap");
    cy.animate({ center: { eles: el }, zoom: Math.max(cy.zoom(), 1) }, { duration: 350 });
  };
  const selectMany = (ids: string[]) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.$(":selected").unselect();
    const els = cy.collection(ids.map((id) => cy.getElementById(id)).filter((e) => e.length) as never);
    els.select();
    cy.elements().addClass("faded");
    els.closedNeighborhood().removeClass("faded");
    if (els.length) cy.animate({ fit: { eles: els.closedNeighborhood(), padding: 60 } }, { duration: 400 });
  };
  const findPath = () => {
    const cy = cyRef.current;
    const nodes = cy?.$("node:selected");
    if (!cy || !nodes || nodes.length !== 2) return toast(t("net.pathHint"));
    const res = cy.elements().dijkstra({ root: nodes[0] });
    const path = res.pathTo(nodes[1]);
    if (!path.length || res.distanceTo(nodes[1]) === Infinity) return toast.warning(t("net.noPath"));
    cy.elements().removeClass("path").addClass("faded");
    path.removeClass("faded").addClass("path");
    toast.success(t("net.pathFound", { n: path.edges().length }));
  };
  const exportPng = async () => {
    const cy = cyRef.current;
    if (!cy) return;
    const data = cy.png({ full: true, scale: 2, bg: "#081129", maxWidth: 8000, maxHeight: 8000 });
    try {
      const res = await call<{ path: string; name: string }>("save_chart_image", data, "Network");
      toast.success(t("export.done", { name: res.name }), { action: { label: t("export.open"), onClick: () => void call("reveal", res.path) } });
    } catch (e) {
      toast.error(errorText(e));
    }
  };
  const positions = () => Object.fromEntries((cyRef.current?.nodes() ?? []).map((n) => [n.id(), n.position()]));
  const saveLayout = async () => {
    await call("network_save_layout", positions());
    savedPositions.current = positions();
    toast.success(t("net.layoutSaved"));
  };
  const linkSelected = async () => {
    const nodes = cyRef.current?.$("node:selected");
    if (!nodes || nodes.length !== 2) return toast(t("net.pathHint"));
    const label = window.prompt(t("net.linkLabel")) ?? "";
    await call("network_add_link", nodes[0].id(), nodes[1].id(), label);
    void load();
  };

  const typeCounts = useMemo(() => {
    const total: Record<string, number> = {};
    const shown: Record<string, number> = {};
    (graph?.nodes ?? []).forEach((n) => (total[n.type] = (total[n.type] ?? 0) + 1));
    visibleNodes.forEach((n) => (shown[n.type] = (shown[n.type] ?? 0) + 1));
    return { total, shown };
  }, [graph, visibleNodes]);

  const focus = focusId ? nodesById.get(focusId) ?? graph?.edges.find((e) => e.id === focusId) : undefined;

  return (
    <div className="flex h-full min-h-0 gap-3" data-testid="network-view">
      {/* ── left: explore + palette ─────────────────────────────── */}
      <aside className="card flex w-[262px] shrink-0 flex-col overflow-hidden">
        <div className="min-h-0 flex-1 overflow-y-auto pb-3">
          <Panel title={t("an.devices")}>
            <div className="flex flex-col gap-1 px-3">
              {graph?.devices.map((d) => {
                const on = !options.extractions || options.extractions.includes(d.id);
                return (
                  <button
                    key={d.id}
                    onClick={() => {
                      const all = graph.devices.map((x) => x.id);
                      const cur = options.extractions ?? all;
                      const next = on ? cur.filter((x) => x !== d.id) : [...cur, d.id];
                      setOptions({ ...options, extractions: next.length === all.length ? null : next.length ? next : cur });
                    }}
                    className={clsx("flex items-center gap-2 rounded-xl border px-2.5 py-2 text-left text-[12.5px] transition", on ? "border-line bg-surface-2" : "border-dashed border-line opacity-50")}
                  >
                    <span className="size-3 shrink-0 rounded-full" style={{ background: DEVICE_COLORS[d.index % DEVICE_COLORS.length] }} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold text-ink">{d.label}</span>
                      <span className="block truncate font-mono text-[11px] text-muted">{d.number || d.serial}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </Panel>
          <Panel title={t("net.explore")} right={<span className="tabular text-[11.5px] text-muted">{t("net.entities")} {visibleNodes.length}/{graph?.nodes.length ?? 0}</span>}>
            <div className="flex flex-col px-3">
              {Object.keys(typeCounts.total)
                .sort((a, b) => (typeCounts.total[b] ?? 0) - (typeCounts.total[a] ?? 0))
                .map((type) => {
                  const total = typeCounts.total[type] ?? 0;
                  const shown = typeCounts.shown[type] ?? 0;
                  const off = hiddenTypes.has(type);
                  return (
                    <button
                      key={type}
                      onClick={() => {
                        const next = new Set(hiddenTypes);
                        if (off) next.delete(type);
                        else next.add(type);
                        setHiddenTypes(next);
                      }}
                      className={clsx("group rounded-lg px-1.5 py-1.5 text-left hover:bg-surface-2", off && "opacity-45")}
                    >
                      <span className="flex items-center gap-2 text-[12.5px]">
                        <TypeIcon type={type} size={12} />
                        <span className="flex-1 truncate text-ink-2">{t(`type.${type}`)}</span>
                        <span className="tabular text-[11.5px] text-muted">
                          {shown} / {total}
                        </span>
                      </span>
                      <span className="mt-1 ml-8 block h-1 overflow-hidden rounded-full bg-surface-3">
                        <span className="block h-full rounded-full" style={{ width: `${(shown / Math.max(1, total)) * 100}%`, background: (ENTITY_META[type] ?? ENTITY_META.other).color }} />
                      </span>
                    </button>
                  );
                })}
              <div className="tabular mt-1 px-1.5 text-[11.5px] text-muted">
                {t("net.links")}: {visibleEdges.length} / {graph?.edges.length ?? 0}
              </div>
            </div>
          </Panel>
          <Panel title={t("ex.options")}>
            <div className="flex flex-col gap-2.5 px-4 text-[12.5px] text-ink-2">
              <label className="flex flex-col gap-1">
                <span className="flex justify-between">
                  {t("net.minWeight", { n: options.min_weight })}
                </span>
                <input type="range" min={1} max={20} value={options.min_weight} onChange={(e) => setOptions({ ...options, min_weight: Number(e.target.value) })} className="accent-[#dca22a]" />
              </label>
              {(
                [
                  ["persons", t("net.persons")],
                  ["hide_services", t("net.services")],
                  ["contacts_only", t("net.contactsOnly")],
                  ["wifi", t("net.wifi")],
                  ["locations", t("net.locations")],
                ] as [keyof Options, string][]
              ).map(([k, label]) => (
                <label key={k} className="flex items-center justify-between gap-2">
                  <span>{label}</span>
                  <Switch checked={!!options[k]} onChange={(v) => setOptions({ ...options, [k]: v })} />
                </label>
              ))}
              <label className="flex items-center justify-between gap-2">
                <span>{t("net.commonOnly")}</span>
                <Switch checked={commonOnly} onChange={setCommonOnly} />
              </label>
              <div>
                <div className="mb-1">{t("net.colorBy")}</div>
                <div className="flex rounded-xl bg-surface-3 p-1">
                  {(["type", "community", "device"] as ColorBy[]).map((c) => (
                    <button key={c} onClick={() => setColorBy(c)} className={clsx("flex-1 rounded-lg py-1 text-[12px] font-semibold", colorBy === c ? "bg-surface text-ink shadow" : "text-muted")}>
                      {t(c === "type" ? "net.colorType" : c === "community" ? "net.colorCommunity" : "net.colorDevice")}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </Panel>
          <Panel title={t("net.palette")}>
            <p className="px-4 pb-2 text-[11.5px] leading-snug text-faint">{t("net.paletteHint")}</p>
            <div className="grid grid-cols-4 gap-1 px-3">
              {PALETTE.map((type) => (
                <button key={type} onClick={() => setAddType(type)} className="flex flex-col items-center gap-1 rounded-xl py-2 text-[10.5px] text-ink-2 hover:bg-surface-2" data-testid={`palette-${type}`}>
                  <TypeIcon type={type} size={14} />
                  <span className="w-full truncate text-center">{t(`type.${type}`)}</span>
                </button>
              ))}
            </div>
          </Panel>
        </div>
      </aside>

      {/* ── centre: chart ───────────────────────────────────────── */}
      <section className="relative flex min-w-0 flex-1 flex-col overflow-hidden rounded-[1.15rem] border border-navy-800 bg-[#081129] shadow-[var(--shadow-card)]">
        <div className="flex shrink-0 flex-wrap items-center gap-0.5 border-b border-white/10 bg-[#0b1636] px-2 py-1.5">
          <span className="mr-1 flex items-center gap-1 rounded-lg bg-white/5 p-0.5">
            <ToolButton icon={<Shuffle className="size-4" />} label={t("net.layout.organic")} onClick={() => runLayout("organic")} active={layout === "organic"} />
            <ToolButton icon={<Orbit className="size-4" />} label={t("net.layout.radial")} onClick={() => runLayout("radial")} active={layout === "radial"} />
            <ToolButton icon={<Layers className="size-4" />} label={t("net.layout.grouped")} onClick={() => runLayout("grouped")} active={layout === "grouped"} />
            <ToolButton icon={<Circle className="size-4" />} label={t("net.layout.circle")} onClick={() => runLayout("circle")} active={layout === "circle"} />
          </span>
          <ToolButton icon={<Focus className="size-4" />} label={t("net.focus")} disabled={!selected.length} onClick={() => {
            const cy = cyRef.current!;
            const keep = new Set(cy.$(":selected").closedNeighborhood().nodes().map((n) => n.id()));
            pushHidden(visibleNodes.filter((n) => !keep.has(n.id)).map((n) => n.id).concat(hidden));
          }} />
          <ToolButton icon={<EyeOff className="size-4" />} label={t("net.hide")} disabled={!selected.length} onClick={() => pushHidden([...hidden, ...selected.filter((id) => nodesById.has(id))])} />
          <ToolButton icon={<Eye className="size-4" />} label={t("net.showAll")} disabled={!hidden.length} onClick={() => pushHidden([])} />
          <ToolButton icon={<Crosshair className="size-4" />} label={t("net.attached")} disabled={!selected.length} onClick={() => cyRef.current?.$(":selected").closedNeighborhood().select()} />
          <ToolButton icon={<Route className="size-4" />} label={t("net.path")} disabled={selected.filter((id) => nodesById.has(id)).length !== 2} onClick={findPath} />
          <ToolButton icon={<LinkIcon className="size-4" />} label={t("net.addLink")} disabled={selected.filter((id) => nodesById.has(id)).length !== 2} onClick={() => void linkSelected()} />
          <ToolButton icon={<Undo2 className="size-4" />} label={t("net.undo")} disabled={!history.past.length} onClick={() => {
            setHistory((h) => ({ past: h.past.slice(0, -1), future: [hidden, ...h.future] }));
            setHidden(history.past[history.past.length - 1]);
          }} />
          <ToolButton icon={<Redo2 className="size-4" />} label={t("net.redo")} disabled={!history.future.length} onClick={() => {
            setHistory((h) => ({ past: [...h.past, hidden], future: h.future.slice(1) }));
            setHidden(history.future[0]);
          }} />
          <span className="ml-auto flex items-center gap-0.5">
            <ToolButton icon={<Save className="size-4" />} label={t("net.saveLayout")} onClick={() => void saveLayout()} />
            <ToolButton icon={<ImageDown className="size-4" />} label={t("net.png")} onClick={() => void exportPng()} />
            <ExportMenu onPick={(fmt) => void exportNetwork(fmt, options as unknown as Record<string, unknown>, positions())} />
          </span>
        </div>
        <div className="relative min-h-0 flex-1">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,rgba(148,163,184,0.12)_1px,transparent_0)] [background-size:24px_24px]">
            {/* cytoscape sets position:relative on its container, so it gets its own box */}
            <div ref={container} className="h-full w-full" data-testid="network-canvas" />
          </div>
          {loading && (
            <div className="absolute inset-0 grid place-items-center bg-[#081129]/60">
              <span className="flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-[13px] text-white">
                <Spinner className="size-4" /> {t("an.loading")}
              </span>
            </div>
          )}
          <Legend />
        </div>
        <div className="flex shrink-0 items-center gap-2 border-t border-white/10 bg-[#0b1636] px-3 py-1.5 text-[12px] text-slate-300">
          <label className="flex h-8 w-64 items-center gap-2 rounded-lg bg-white/5 px-2.5">
            <Search className="size-3.5 text-slate-400" />
            <input value={query} onChange={(e) => (setQuery(e.target.value), setMatchIndex(0))} placeholder={t("net.find")} className="min-w-0 flex-1 bg-transparent text-[12.5px] text-white outline-none placeholder:text-slate-500" data-testid="network-find" />
          </label>
          <span className="tabular text-slate-400">
            {matches.length ? `${Math.min(matchIndex, matches.length - 1) + 1} / ${matches.length}` : query ? "0" : ""}
          </span>
          {matches.length > 1 && (
            <button className="rounded px-1.5 hover:bg-white/10" onClick={() => setMatchIndex((i) => (i + 1) % matches.length)}>
              ›
            </button>
          )}
          <span className="tabular ml-auto text-slate-400">{t("net.count", { n: visibleNodes.length, e: visibleEdges.length })}</span>
          <button className="rounded p-1 hover:bg-white/10" onClick={() => cyRef.current?.zoom({ level: cyRef.current.zoom() / 1.25, renderedPosition: { x: (container.current?.clientWidth ?? 0) / 2, y: (container.current?.clientHeight ?? 0) / 2 } })}>
            <ZoomOut className="size-4" />
          </button>
          <span className="tabular w-11 text-center">{Math.round(zoom * 100)}%</span>
          <button className="rounded p-1 hover:bg-white/10" onClick={() => cyRef.current?.zoom({ level: cyRef.current.zoom() * 1.25, renderedPosition: { x: (container.current?.clientWidth ?? 0) / 2, y: (container.current?.clientHeight ?? 0) / 2 } })}>
            <ZoomIn className="size-4" />
          </button>
          <button className="rounded p-1 hover:bg-white/10" onClick={() => cyRef.current?.fit(undefined, 40)}>
            <Maximize2 className="size-4" />
          </button>
        </div>
      </section>

      {/* ── right: list / details / insights ───────────────────── */}
      <aside className="card flex w-[360px] shrink-0 flex-col overflow-hidden 2xl:w-[400px]">
        <div className="flex shrink-0 gap-1 border-b border-line p-2">
          {(["insights", "list", "details"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setRightTab(k)}
              className={clsx("flex-1 rounded-xl py-2 text-[13px] font-semibold transition", rightTab === k ? "bg-navy-800 text-white dark:bg-gold-400 dark:text-navy-950" : "text-muted hover:bg-surface-2")}
              data-testid={`net-tab-${k}`}
            >
              {t(`net.${k}`)}
            </button>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          {rightTab === "list" && <NodeList nodes={visibleNodes} graph={graph} selected={selected} onPick={selectNode} />}
          {rightTab === "insights" && graph && <Insights graph={graph} nodesById={nodesById} onPick={selectNode} onPickMany={selectMany} />}
          {rightTab === "details" && (
            <Details
              item={focus}
              graph={graph}
              nodesById={nodesById}
              onChanged={() => void load()}
              onPick={selectNode}
            />
          )}
        </div>
      </aside>

      <AddEntityDialog
        type={addType}
        selected={selected.filter((id) => nodesById.has(id))}
        onClose={() => setAddType(null)}
        onAdded={(id) => {
          setAddType(null);
          void load().then(() => window.setTimeout(() => selectNode(id), 300));
        }}
      />
    </div>
  );
}

function ExportMenu({ onPick }: { onPick: (fmt: "anx" | "xlsx" | "graphml") => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <span className="relative">
      <ToolButton icon={<Download className="size-4" />} label={t("net.export")} onClick={() => setOpen((o) => !o)} />
      {open && (
        <div className="absolute top-full right-0 z-20 mt-1 w-52 rounded-xl border border-line bg-surface p-1 shadow-[var(--shadow-pop)]" onMouseLeave={() => setOpen(false)}>
          {(
            [
              ["anx", t("net.i2")],
              ["xlsx", "Excel"],
              ["graphml", t("net.graphml")],
            ] as const
          ).map(([fmt, label]) => (
            <button
              key={fmt}
              className="w-full rounded-lg px-3 py-2 text-left text-[13px] text-ink hover:bg-surface-2"
              onClick={() => {
                setOpen(false);
                onPick(fmt);
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}

function Legend() {
  const { t } = useI18n();
  const items: [string, string][] = [
    ["comm", EDGE_COLORS.comm],
    ["chat", EDGE_COLORS.chat],
    ["wifi", EDGE_COLORS.wifi],
    ["location", EDGE_COLORS.location],
    ["manual", EDGE_COLORS.manual],
  ];
  return (
    <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-x-3 gap-y-1 rounded-xl bg-[#0b1636]/85 px-3 py-2 text-[11px] text-slate-300 backdrop-blur">
      {items.map(([k, c]) => (
        <span key={k} className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded" style={{ background: c }} /> {t(`edge.${k}`)}
        </span>
      ))}
      <span className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-full border-2 border-[#f472b6]" /> {t("net.common")}
      </span>
    </div>
  );
}

function NodeList({ nodes, graph, selected, onPick }: { nodes: NetNode[]; graph: NetGraph | null; selected: string[]; onPick: (id: string) => void }) {
  const { t } = useI18n();
  const [type, setType] = useState("all");
  const sorted = useMemo(() => nodes.filter((n) => type === "all" || n.type === type).sort((a, b) => b.metrics.strength - a.metrics.strength), [nodes, type]);
  const ref = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({ count: sorted.length, getScrollElement: () => ref.current, estimateSize: () => 52, overscan: 10 });
  const types = [...new Set(nodes.map((n) => n.type))];
  const maxB = Math.max(0.0001, ...nodes.map((n) => n.metrics.betweenness));
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-wrap gap-1 px-3 py-2">
        {["all", ...types].map((ty) => (
          <button key={ty} onClick={() => setType(ty)} className={clsx("rounded-full px-2.5 py-1 text-[11.5px] font-semibold", type === ty ? "bg-navy-800 text-white dark:bg-gold-400 dark:text-navy-950" : "bg-surface-3 text-muted")}>
            {ty === "all" ? t("tb.all") : t(`type.${ty}`)}
          </button>
        ))}
      </div>
      <div ref={ref} className="min-h-0 flex-1 overflow-auto" data-testid="network-list">
        <div style={{ height: v.getTotalSize(), position: "relative" }}>
          {v.getVirtualItems().map((it) => {
            const n = sorted[it.index];
            return (
              <button
                key={n.id}
                onClick={() => onPick(n.id)}
                className={clsx("absolute inset-x-2 flex items-center gap-2.5 rounded-xl px-2 text-left hover:bg-surface-2", selected.includes(n.id) && "bg-navy-50 dark:bg-navy-800/60")}
                style={{ height: it.size - 2, transform: `translateY(${it.start}px)` }}
              >
                <TypeIcon type={n.type} size={13} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold text-ink">{n.label}</span>
                  <span className="flex items-center gap-1 truncate text-[11px] text-muted">
                    {n.devices.map((d) => {
                      const dev = graph?.devices.find((x) => x.id === d);
                      return <span key={d} className="size-2 rounded-full" style={{ background: DEVICE_COLORS[(dev?.index ?? 0) % DEVICE_COLORS.length] }} />;
                    })}
                    {n.sub || t(`type.${n.type}`)}
                  </span>
                </span>
                <span className="w-16 text-right">
                  <span className="tabular block text-[12px] font-bold text-ink">{n.metrics.strength}</span>
                  <span className="mt-0.5 block h-1 overflow-hidden rounded-full bg-surface-3">
                    <span className="block h-full rounded-full bg-gold-400" style={{ width: `${(n.metrics.betweenness / maxB) * 100}%` }} />
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function NodeChip({ node, onPick, right }: { node?: NetNode; onPick: (id: string) => void; right?: ReactNode }) {
  if (!node) return null;
  return (
    <button onClick={() => onPick(node.id)} className="flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left hover:bg-surface-2">
      <TypeIcon type={node.type} size={12} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-semibold text-ink">{node.label}</span>
        {node.sub && <span className="block truncate text-[11px] text-muted">{node.sub}</span>}
      </span>
      {right}
    </button>
  );
}

function Insights({ graph, nodesById, onPick, onPickMany }: { graph: NetGraph; nodesById: Map<string, NetNode>; onPick: (id: string) => void; onPickMany: (ids: string[]) => void }) {
  const { t } = useI18n();
  const label = (id: string) => graph.devices.find((d) => `dev:${d.id}` === id || d.id === id)?.label ?? id;
  return (
    <div className="h-full overflow-y-auto pb-4" data-testid="network-insights">
      <Panel title={t("net.common")}>
        <div className="px-3">
          {graph.devices.length < 2 || !graph.insights.common.length ? (
            <p className="px-1 text-[12.5px] text-muted">{t("net.commonNone")}</p>
          ) : (
            <>
              {graph.insights.device_pairs.map((p) => (
                <button key={p.a + p.b} onClick={() => onPickMany(p.shared)} className="mb-2 w-full rounded-xl border border-pink-300/40 bg-pink-50 px-3 py-2 text-left text-[12.5px] font-semibold text-pink-700 dark:bg-pink-500/10 dark:text-pink-300">
                  {t("net.sharedBetween", { a: label(p.a), b: label(p.b), n: p.shared.length })}
                </button>
              ))}
              {graph.insights.common.slice(0, 12).map((id) => (
                <NodeChip key={id} node={nodesById.get(id)} onPick={onPick} right={<Badge tone="red">{nodesById.get(id)?.devices.length}</Badge>} />
              ))}
            </>
          )}
        </div>
      </Panel>
      <Panel title={t("net.keyPlayers")}>
        <div className="px-3">
          {graph.insights.key_players.map((id, i) => (
            <NodeChip key={id} node={nodesById.get(id)} onPick={onPick} right={<span className="tabular text-[12px] font-bold text-muted">#{i + 1} · {nodesById.get(id)?.metrics.strength}</span>} />
          ))}
        </div>
      </Panel>
      <Panel title={t("net.brokers")}>
        <div className="px-3">
          {graph.insights.brokers.map((id) => (
            <NodeChip key={id} node={nodesById.get(id)} onPick={onPick} right={<span className="tabular text-[12px] text-muted">{nodesById.get(id)?.metrics.betweenness.toFixed(3)}</span>} />
          ))}
        </div>
      </Panel>
      <Panel title={t("net.communities")}>
        <div className="grid grid-cols-2 gap-2 px-3">
          {graph.insights.communities.map((c) => (
            <button key={c.id} onClick={() => onPickMany(graph.nodes.filter((n) => n.metrics.community === c.id).map((n) => n.id))} className="rounded-xl border border-line px-2.5 py-2 text-left hover:bg-surface-2">
              <span className="flex items-center gap-1.5 text-[12px] font-bold text-ink">
                <span className="size-2.5 rounded-full" style={{ background: COMMUNITY_COLORS[c.id % COMMUNITY_COLORS.length] }} /> #{c.id + 1}
                <span className="ml-auto text-[11px] font-medium text-muted">{t("net.members", { n: c.size })}</span>
              </span>
              <span className="mt-0.5 block truncate text-[11.5px] text-muted">{c.lead}</span>
            </button>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Details({ item, graph, nodesById, onChanged, onPick }: { item?: NetNode | NetEdge; graph: NetGraph | null; nodesById: Map<string, NetNode>; onChanged: () => void; onPick: (id: string) => void }) {
  const { t } = useI18n();
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [tags, setTags] = useState("");
  const [evidence, setEvidence] = useState<any[] | null>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const isNode = !!item && "metrics" in item;
  useEffect(() => {
    setEvidence(null);
    if (!item) return;
    if (isNode) {
      const n = item as NetNode;
      setLabel(n.orig_label ? n.label : "");
      setNote(n.note ?? "");
      setTags((n.tags ?? []).join(", "));
    }
    void call<unknown[]>("network_evidence", item.id).then((r) => setEvidence(r as never[]));
  }, [item, isNode]);
  if (!item) return <p className="p-5 text-[13px] text-muted">{t("net.selectHint")}</p>;
  const devLabel = (id: string) => graph?.devices.find((d) => d.id === id)?.label ?? id;

  return (
    <div className="h-full overflow-y-auto pb-4" data-testid="network-details">
      {isNode ? (
        (() => {
          const n = item as NetNode;
          return (
            <>
              <div className="flex items-start gap-3 border-b border-line px-4 py-4">
                <TypeIcon type={n.type} size={18} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-display text-[17px] font-semibold text-ink" data-selectable>
                    {n.label}
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    <Badge tone="navy">{t(`type.${n.type}`)}</Badge>
                    {n.common && <Badge tone="red">{t("net.common")}</Badge>}
                    {n.manual && <Badge tone="gold">{t("tl.examiner")}</Badge>}
                  </div>
                </div>
                {n.props.number && <CopyButton value={n.props.number} />}
              </div>
              <div className="grid grid-cols-4 gap-1 px-4 py-3 text-center">
                {(
                  [
                    ["net.degree", n.metrics.degree],
                    ["net.strength", n.metrics.strength],
                    ["net.betweenness", n.metrics.betweenness.toFixed(3)],
                    ["net.community", `#${n.metrics.community + 1}`],
                  ] as [string, string | number][]
                ).map(([k, v]) => (
                  <div key={k} className="rounded-xl bg-surface-2 py-2">
                    <div className="tabular font-display text-[15px] font-bold text-ink">{v}</div>
                    <div className="truncate px-1 text-[10.5px] text-muted">{t(k)}</div>
                  </div>
                ))}
              </div>
              <div className="flex flex-col gap-1 px-4 text-[12.5px]">
                {n.orig_label && (
                  <div>
                    <span className="text-muted">{t("net.original")}: </span>
                    <span className="font-mono">{n.orig_label}</span>
                  </div>
                )}
                {(n.props.names ?? []).length > 0 && (
                  <div>
                    <span className="text-muted">{t("net.names")}: </span>
                    {(n.props.names as string[]).join(", ")}
                  </div>
                )}
                <div className={clsx("flex flex-wrap items-center gap-1", n.type === "device" && "hidden")}>
                  <span className="text-muted">{t("net.foundIn")}:</span>
                  {n.devices.map((d) => (
                    <Badge key={d} tone="slate">
                      {devLabel(d)}
                    </Badge>
                  ))}
                </div>
              </div>
              <Panel title={t("net.annotate")}>
                <div className="flex flex-col gap-2 px-4">
                  <Field label={t("net.label")}>
                    <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={n.orig_label ?? n.label} data-testid="annotate-label" />
                  </Field>
                  <Field label={t("net.note")}>
                    <Input value={note} onChange={(e) => setNote(e.target.value)} />
                  </Field>
                  <Field label={t("net.tags")}>
                    <Input value={tags} onChange={(e) => setTags(e.target.value)} />
                  </Field>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={async () => {
                        await call("network_annotate", n.id, label, note, tags.split(",").map((s) => s.trim()).filter(Boolean));
                        toast.success(t("net.saved"));
                        onChanged();
                      }}
                      data-testid="annotate-save"
                    >
                      {t("net.save")}
                    </Button>
                    {n.manual && (
                      <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" />} onClick={async () => (await call("network_delete_manual", n.id), onChanged())}>
                        {t("net.delete")}
                      </Button>
                    )}
                  </div>
                </div>
              </Panel>
            </>
          );
        })()
      ) : (
        (() => {
          const e = item as NetEdge;
          const s = e.stats;
          return (
            <>
              <div className="border-b border-line px-4 py-4">
                <Badge tone="navy">{t(`edge.${e.type}`)}</Badge>
                <div className="mt-2 flex flex-col gap-1">
                  <NodeChip node={nodesById.get(e.source)} onPick={onPick} />
                  <NodeChip node={nodesById.get(e.target)} onPick={onPick} />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-1 px-4 py-3 text-center">
                {(
                  [
                    ["dir.outgoing", s.calls_out ?? 0],
                    ["dir.incoming", s.calls_in ?? 0],
                    ["dir.missed", s.missed ?? 0],
                    ["net.sms", (s.sms_in ?? 0) + (s.sms_out ?? 0)],
                    ["tab.chats", s.chats ?? 0],
                    ["tl.duration", fmtDuration(s.duration ?? 0)],
                  ] as [string, string | number][]
                ).map(([k, v]) => (
                  <div key={k} className="rounded-xl bg-surface-2 py-2">
                    <div className="tabular font-display text-[15px] font-bold text-ink">{v}</div>
                    <div className="truncate text-[10.5px] text-muted">{t(k)}</div>
                  </div>
                ))}
              </div>
              <div className="px-4 text-[12px] text-muted">
                {t("net.first")}: {fmtDateTime(s.first)} · {t("net.last")}: {fmtDateTime(s.last)}
              </div>
              {e.manual_id && (
                <div className="px-4 pt-2">
                  <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" />} onClick={async () => (await call("network_delete_manual", `mlink:${e.manual_id}`), onChanged())}>
                    {t("net.delete")}
                  </Button>
                </div>
              )}
            </>
          );
        })()
      )}
      <Panel title={t("net.evidence")} right={evidence ? <span className="tabular text-[11.5px] text-muted">{evidence.length}</span> : undefined}>
        <div className="flex flex-col gap-1 px-3">
          {!evidence && <div className="skeleton mx-1 h-10 rounded-xl" />}
          {evidence?.length === 0 && <p className="px-1 text-[12.5px] text-muted">{t("net.noEvidence")}</p>}
          {evidence?.slice(0, 120).map((r) => (
            <div key={r.id} className="rounded-xl border border-line px-3 py-2 text-[12px]">
              <div className="flex items-center gap-2">
                <Badge tone={r.kind === "call" ? "blue" : r.kind === "sms" ? "gold" : r.kind === "photo" ? "red" : "green"}>{t(`kind.${r.kind}`) === `kind.${r.kind}` ? t(`tl.kind.${r.kind}`) : t(`kind.${r.kind}`)}</Badge>
                {r.dir && <span className="text-muted">{t(`dir.${r.dir}`)}</span>}
                <span className="tabular ml-auto text-faint">{fmtDateTime(r.ts)}</span>
              </div>
              {r.kind === "call" && <div className="tabular mt-0.5 text-ink-2">{fmtDuration(r.duration)} {r.site ? `· ${r.site}` : ""}</div>}
              {(r.body || r.label) && <div className="mt-0.5 line-clamp-2 text-ink-2">{r.body || r.label}</div>}
              <div className="mt-0.5 truncate text-[11px] text-faint">{devLabel(r.device)}</div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function AddEntityDialog({ type, selected, onClose, onAdded }: { type: string | null; selected: string[]; onClose: () => void; onAdded: (id: string) => void }) {
  const { t } = useI18n();
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [linkLabel, setLinkLabel] = useState("");
  const [kind, setKind] = useState("person");
  useEffect(() => {
    if (type) {
      setKind(type);
      setLabel("");
      setNote("");
      setLinkLabel("");
    }
  }, [type]);
  return (
    <Modal open={!!type} onClose={onClose} width={520}>
      <ModalHeader icon={<TypeIcon type={kind} size={16} />} title={t("net.addEntity")} sub={t("net.paletteHint")} onClose={onClose} />
      <div className="flex flex-col gap-3 px-6 py-5">
        <div className="grid grid-cols-4 gap-1.5">
          {PALETTE.map((ty) => (
            <button key={ty} onClick={() => setKind(ty)} className={clsx("flex flex-col items-center gap-1 rounded-xl border-2 py-2 text-[11px]", kind === ty ? "border-navy-600 dark:border-gold-400" : "border-transparent hover:bg-surface-2")}>
              <TypeIcon type={ty} size={13} />
              {t(`type.${ty}`)}
            </button>
          ))}
        </div>
        <Field label={t("net.label")}>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} autoFocus data-testid="entity-label" />
        </Field>
        <Field label={t("net.note")}>
          <Input value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {selected.length > 0 && (
          <Field label={t("net.linkTo", { n: selected.length })}>
            <Input value={linkLabel} onChange={(e) => setLinkLabel(e.target.value)} placeholder={t("net.linkLabel")} />
          </Field>
        )}
      </div>
      <div className="flex justify-end gap-2 border-t border-line bg-surface-2 px-6 py-4">
        <Button variant="ghost" onClick={onClose}>
          {t("common.cancel")}
        </Button>
        <Button
          variant="primary"
          disabled={!label.trim()}
          onClick={async () => {
            const res = await call<{ node_id: string }>("network_add_entity", { type: kind, label, note }, selected, linkLabel);
            onAdded(res.node_id);
          }}
          data-testid="entity-add"
        >
          {t("net.add")}
        </Button>
      </div>
    </Modal>
  );
}
