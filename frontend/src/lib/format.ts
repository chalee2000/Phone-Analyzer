import type { Lang } from "./i18n";

const pad = (n: number) => String(n).padStart(2, "0");

export function fmtDateTime(ms: number | null | undefined): string {
  if (!ms) return "";
  const d = new Date(ms);
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function fmtDate(ms: number | null | undefined): string {
  if (!ms) return "";
  const d = new Date(ms);
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}

export function fmtTime(ms: number | null | undefined): string {
  if (!ms) return "";
  const d = new Date(ms);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fmtIso(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  return Number.isNaN(t) ? iso : fmtDateTime(t);
}

export function fmtLongDate(ms: number, lang: Lang): string {
  const locale = lang === "th" ? "th-TH-u-ca-gregory" : "en-GB";
  return new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short", year: "numeric" }).format(ms);
}

export function fmtDayHeader(ms: number, lang: Lang): string {
  const locale = lang === "th" ? "th-TH-u-ca-gregory" : "en-GB";
  return new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(ms);
}

export function fmtDuration(sec: number | null | undefined): string {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h ? `${h}:${pad(m)}:${pad(r)}` : `${m}:${pad(r)}`;
}

export function fmtHours(sec: number, lang: Lang): string {
  const h = Math.floor(sec / 3600);
  const m = Math.round((sec % 3600) / 60);
  if (lang === "th") return h ? `${h} ชม. ${m} นาที` : `${m} นาที`;
  return h ? `${h} h ${m} min` : `${m} min`;
}

export function fmtSize(bytes: number | null | undefined): string {
  if (bytes == null) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return i === 0 ? `${v} B` : `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`;
}

export function fmtNumber(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("en-US");
}

export function initials(name: string): string {
  const clean = name.replace(/^(พี่|น้อง|ลุง|ป้า|เจ๊|เฮีย|เสี่ย|ครู|ไอ้|นาย|นาง|นางสาว)\s*/u, "").trim();
  if (!clean) return "?";
  const first = Array.from(clean)[0];
  // Thai leading vowels (เ แ โ ใ ไ) are not a good initial: use the consonant after them.
  if (/[เ-ไ]/.test(first)) return Array.from(clean)[1] ?? first;
  const parts = clean.split(/\s+/);
  if (/^[A-Za-z]/.test(clean) && parts.length > 1) return (parts[0][0] + parts[1][0]).toUpperCase();
  return first.toUpperCase();
}

const AVATAR_COLORS = [
  "from-sky-500 to-blue-600",
  "from-emerald-500 to-teal-600",
  "from-amber-400 to-orange-500",
  "from-fuchsia-500 to-pink-600",
  "from-violet-500 to-indigo-600",
  "from-rose-500 to-red-600",
  "from-cyan-500 to-sky-600",
  "from-lime-500 to-green-600",
];

export function avatarColor(seed: string): string {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

export function matches(haystack: unknown[], needle: string): boolean {
  if (!needle) return true;
  const q = needle.toLowerCase();
  return haystack.some((v) => v != null && String(v).toLowerCase().includes(q));
}

export function fmtMonth(ms: number, lang: Lang): string {
  const locale = lang === "th" ? "th-TH-u-ca-gregory" : "en-GB";
  return new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(ms);
}
