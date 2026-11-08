/**
 * Renders the case's link chart offscreen as a print-friendly PNG for the
 * forensic report: white background, dark labels, strongest entities only.
 * Uses the examiner's saved layout when it covers the chart, else fcose.
 */
import type { ElementDefinition, LayoutOptions } from "cytoscape";
import { ENTITY_META, iconDataUri, type NetGraph } from "./analysis";
import { call } from "./bridge";
import cytoscape from "./cy";

const EDGE_COLORS: Record<string, string> = {
  comm: "#0284c7", chat: "#059669", own: "#d97706", sim: "#d97706", number: "#64748b", account: "#7c3aed",
  wifi: "#4f46e5", location: "#e11d48", member: "#0ea5e9", saved: "#94a3b8", manual: "#334155",
};

export async function renderNetworkPng(extractions: string[] | null, maxNodes = 80): Promise<string | null> {
  const graph = await call<NetGraph>("network_graph", {
    extractions, persons: true, hide_services: true, contacts_only: false, wifi: true, locations: false, min_weight: 1,
  });
  if (!graph.nodes.length) return null;
  const saved = await call<Record<string, { x: number; y: number }>>("network_load_layout").catch(() => ({}) as Record<string, { x: number; y: number }>);

  const devices = graph.nodes.filter((n) => n.type === "device");
  const rest = graph.nodes.filter((n) => n.type !== "device").sort((a, b) => b.metrics.strength - a.metrics.strength);
  const keep = [...devices, ...rest.slice(0, Math.max(10, maxNodes - devices.length))];
  const ids = new Set(keep.map((n) => n.id));
  const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const linked = new Set(edges.flatMap((e) => [e.source, e.target]));
  const nodes = keep.filter((n) => n.type === "device" || linked.has(n.id));

  const elements: ElementDefinition[] = [
    ...nodes.map((n) => {
      const meta = ENTITY_META[n.type] ?? ENTITY_META.other;
      const size = n.type === "device" ? 70 : Math.min(54, 24 + 7 * Math.log2(1 + n.metrics.strength));
      return {
        group: "nodes" as const,
        data: { id: n.id, label: n.label, type: n.type, color: meta.color, icon: iconDataUri(meta.icon), size },
        classes: n.common ? "common" : "",
      };
    }),
    ...edges.map((e) => ({
      group: "edges" as const,
      data: { id: e.id, source: e.source, target: e.target, color: EDGE_COLORS[e.type] ?? "#94a3b8", width: Math.min(8, 1.2 + Math.log2(e.weight) * 1.2) },
    })),
  ];

  // Node icons are data-URI images that cytoscape loads asynchronously; warm them up first.
  const icons = [...new Set(elements.filter((e) => e.group === "nodes").map((e) => e.data.icon as string))];
  await Promise.all(
    icons.map(
      (src) =>
        new Promise<void>((resolve) => {
          const img = new window.Image();
          img.onload = img.onerror = () => resolve();
          img.src = src;
        }),
    ),
  );

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;left:-20000px;top:0;width:1800px;height:1150px;";
  document.body.appendChild(host);
  try {
    const cy = cytoscape({
      container: host,
      elements,
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
            color: "#0f172a",
            "font-size": 12,
            "font-family": "IBM Plex Sans Thai, Leelawadee UI, sans-serif",
            "text-valign": "bottom",
            "text-margin-y": 5,
            "text-outline-color": "#ffffff",
            "text-outline-width": 3,
            "text-max-width": "150px",
            "text-wrap": "ellipsis",
            "border-width": 2,
            "border-color": "#ffffff",
          },
        },
        { selector: "node[type = 'device']", style: { "border-width": 5, "border-color": "#b45309", "font-size": 15, "font-weight": 700 } },
        { selector: "node.common", style: { "border-color": "#db2777", "border-width": 4 } },
        { selector: "edge", style: { width: "data(width)", "line-color": "data(color)", "curve-style": "bezier", opacity: 0.6 } },
      ],
    });
    const fromSaved = nodes.every((n) => saved[n.id]);
    const layout: LayoutOptions = fromSaved
      ? ({ name: "preset", positions: (n: cytoscape.NodeSingular) => saved[n.id()] } as LayoutOptions)
      : ({
          name: "fcose", quality: "proof", randomize: true, animate: false, nodeRepulsion: () => 9500, idealEdgeLength: () => 95,
          edgeElasticity: () => 0.35, gravity: 0.3, numIter: 2500, nodeSeparation: 90, packComponents: true,
        } as unknown as LayoutOptions);
    await new Promise<void>((resolve) => {
      const l = cy.layout(layout);
      l.one("layoutstop", () => resolve());
      l.run();
    });
    cy.fit(undefined, 40);
    // Give the renderer time to pull the icons into its own cache before drawing.
    await new Promise((r) => setTimeout(r, 450));
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    const png = cy.png({ full: true, scale: 2, bg: "#ffffff", maxWidth: 3600, maxHeight: 2400 });
    cy.destroy();
    return png;
  } finally {
    host.remove();
  }
}
