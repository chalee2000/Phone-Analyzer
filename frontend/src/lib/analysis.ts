/** Types and helpers shared by the network, timeline and call-analysis views. */
import {
  AppWindow,
  Building2,
  Car,
  CreditCard,
  Flag,
  Globe,
  House,
  Image,
  Landmark,
  Mail,
  MapPin,
  MessageSquareText,
  MessagesSquare,
  Mic,
  NotebookPen,
  Phone,
  Smartphone,
  User,
  Wifi,
  Shapes,
  Headset,
} from "lucide";

export type IconNode = [tag: string, attrs: Record<string, string | number | undefined>][];

export const DEVICE_COLORS = ["#38bdf8", "#f2c14e", "#34d399", "#f472b6", "#a78bfa", "#fb923c", "#22d3ee", "#facc15"];

export interface CaseDevice {
  id: string;
  index: number;
  label: string;
  number: string;
  platform: string;
  brand?: string;
  serial?: string;
  method?: string;
}

export interface NetNode {
  id: string;
  type: string;
  label: string;
  sub: string;
  devices: string[];
  props: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  metrics: { degree: number; strength: number; betweenness: number; community: number };
  common: boolean;
  manual?: boolean;
  note?: string;
  tags?: string[];
  orig_label?: string;
}

export interface NetEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  weight: number;
  label: string;
  stats: Record<string, number>;
  manual_id?: string;
}

export interface NetGraph {
  nodes: NetNode[];
  edges: NetEdge[];
  devices: CaseDevice[];
  counts: Record<string, number>;
  insights: {
    key_players: string[];
    brokers: string[];
    common: string[];
    communities: { id: number; size: number; members: string[]; lead: string }[];
    device_pairs: { a: string; b: string; shared: string[] }[];
  };
}

export interface TimelineEvent {
  id: string;
  ts: number;
  lane: "people" | "objects" | "locations" | "events";
  kind: string;
  name: string;
  number: string;
  detail: string;
  device: string;
  extra: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  bookmark?: string;
  manual?: boolean;
}

export interface CommRow {
  id: string;
  device: string;
  kind: "call" | "sms" | "chat";
  ts: number | null;
  dir: string;
  number: string;
  name: string;
  saved: boolean;
  duration: number;
  service: string;
  body: string;
  sender?: string;
  location?: string;
  cell?: string;
  cell_end?: string;
  site?: string;
  lat: number | null;
  lon: number | null;
  azimuth?: number | null;
}

export interface ContactSummary {
  key: string;
  number: string;
  name: string;
  kind: "phone" | "chat";
  app: string;
  is_phone: boolean;
  saved: boolean;
  calls_in: number;
  calls_out: number;
  missed: number;
  sms_in: number;
  sms_out: number;
  chats: number;
  duration: number;
  first: number | null;
  last: number | null;
  night: number;
  total: number;
  devices: string[];
  active_days: number;
}

export interface GeoPoint {
  id: string;
  device: string;
  kind: string;
  ts: number | null;
  lat: number;
  lon: number;
  label: string;
  thumb: string;
}

export const ENTITY_META: Record<string, { color: string; icon: IconNode }> = {
  device: { color: "#e0a82e", icon: Smartphone },
  phone: { color: "#3b82f6", icon: Phone },
  person: { color: "#14b8a6", icon: User },
  chat: { color: "#22c55e", icon: MessagesSquare },
  account: { color: "#8b5cf6", icon: Mail },
  sim: { color: "#f59e0b", icon: CreditCard },
  wifi: { color: "#6366f1", icon: Wifi },
  location: { color: "#f43f5e", icon: MapPin },
  organization: { color: "#0ea5e9", icon: Building2 },
  service: { color: "#64748b", icon: Headset },
  vehicle: { color: "#f97316", icon: Car },
  address: { color: "#ec4899", icon: House },
  bank: { color: "#10b981", icon: Landmark },
  event: { color: "#eab308", icon: Flag },
  other: { color: "#94a3b8", icon: Shapes },
};

export const KIND_ICON: Record<string, IconNode> = {
  call: Phone,
  sms: MessageSquareText,
  chat: MessagesSquare,
  photo: Image,
  web: Globe,
  note: NotebookPen,
  voice: Mic,
  wifi: Wifi,
  app: AppWindow,
  sim: CreditCard,
  extraction: Smartphone,
  manual: Flag,
};

/** Render a lucide icon node to an SVG string (for canvas/graph images). */
export function iconSvg(icon: IconNode, color = "#ffffff", size = 24, stroke = 2): string {
  const body = icon
    .map(([tag, attrs]) => {
      const a = Object.entries(attrs)
        .map(([k, v]) => `${k}="${String(v)}"`)
        .join(" ");
      return `<${tag} ${a}/>`;
    })
    .join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
}

export function iconDataUri(icon: IconNode, color = "#ffffff"): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(iconSvg(icon, color))}`;
}

export function mediaUrlFor(base: string | undefined, caseId: string | undefined, extId: string, rel: string): string {
  if (!base || !caseId || !rel || !extId) return "";
  return `${base}/${encodeURIComponent(caseId)}/extractions/${encodeURIComponent(extId)}/${rel.split("/").map(encodeURIComponent).join("/")}`;
}

export function deviceColor(devices: CaseDevice[], id: string): string {
  const d = devices.find((x) => x.id === id);
  return DEVICE_COLORS[(d?.index ?? 0) % DEVICE_COLORS.length];
}

export function downloadBase64(name: string, dataUrl: string) {
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = name;
  a.click();
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}
