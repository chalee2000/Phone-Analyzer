export type Platform = "android" | "ios";

export type Kind =
  | "calls"
  | "contacts"
  | "sms"
  | "chats"
  | "web"
  | "notes"
  | "voice"
  | "wifi"
  | "sim"
  | "photos"
  | "apps";

export const ALL_KINDS: Kind[] = ["calls", "contacts", "sms", "chats", "web", "notes", "voice", "wifi", "sim", "photos", "apps"];

export interface DeviceInfo {
  platform: Platform;
  serial: string;
  brand: string;
  model: string;
  market_name: string;
  product: string;
  device_name: string;
  os_version: string;
  build_id: string;
  security_patch: string;
  fingerprint: string;
  cpu_abi: string;
  imei: string;
  imei2: string;
  phone_number: string;
  carrier: string;
  timezone: string;
  battery_level: number | null;
  battery_status: string;
  storage_total: number | null;
  storage_free: number | null;
  wifi_mac: string;
  bluetooth_mac: string;
  bluetooth_name: string;
  accounts: string[];
  extra: Record<string, string>;
  restricted: Record<string, string>;
}

export interface ScannedDevice {
  id: string;
  platform: Platform;
  serial: string;
  state: string; // ready | unauthorized | offline | not_trusted | locked
  brand: string;
  model: string;
  name: string;
  demo?: boolean;
}

export interface ConnectedDevice {
  id: string;
  info: DeviceInfo;
  demo?: boolean;
  offline?: boolean;
}

export interface CaseMeta {
  id: string;
  path: string;
  case_no?: string;
  title?: string;
  investigator?: string;
  unit?: string;
  note?: string;
  created?: string;
  extraction_count: number;
}

export interface Unavailable {
  reason: string;
  detail: string;
}

export interface ExtractionInfo {
  id: string;
  case_id: string;
  started: string;
  finished: string | null;
  status: string;
  platform: Platform;
  serial: string;
  model: string;
  method: string;
  examiner: string;
  device: DeviceInfo;
  unavailable: Partial<Record<Kind, Unavailable>>;
  summary: Partial<Record<Kind, number>>;
  case_no?: string;
  case_title?: string;
}

export interface AppInfo {
  version: string;
  demo: boolean;
  cases_root: string;
  media_base: string;
  platform: string;
  agent_available: boolean;
}

export interface AppState {
  device: ConnectedDevice | null;
  case: CaseMeta | null;
  extraction: ExtractionInfo | null;
  counts: Partial<Record<Kind, number>>;
  running: boolean;
}

export interface CallRecord {
  number: string;
  name: string;
  direction: string;
  timestamp: number | null;
  duration: number;
  sim: string;
  service: string;
  location: string;
}
export interface Contact {
  name: string;
  phones: string[];
  emails: string[];
  organization: string;
  note: string;
  account: string;
  starred: boolean;
}
export interface SmsMessage {
  address: string;
  body: string;
  direction: "in" | "out";
  timestamp: number | null;
  thread: string;
  contact_name: string;
  read: boolean;
  service: string;
  attachments: string[];
}
export interface ChatMessage {
  app: string;
  thread: string;
  sender: string;
  body: string;
  direction: "in" | "out";
  timestamp: number | null;
  attachment: string;
}
export interface WebVisit {
  url: string;
  title: string;
  timestamp: number | null;
  visit_count: number;
  browser: string;
}
export interface Note {
  title: string;
  body: string;
  folder: string;
  created: number | null;
  modified: number | null;
}
export interface VoiceMemo {
  title: string;
  path: string;
  duration: number | null;
  created: number | null;
  size: number | null;
  sha256: string;
}
export interface WifiNetwork {
  ssid: string;
  security: string;
  bssid: string;
  last_connected: number | null;
  hidden: boolean;
}
export interface SimCard {
  slot: string;
  iccid: string;
  imsi: string;
  number: string;
  carrier: string;
  country: string;
  display_name: string;
  active: boolean;
  last_seen: number | null;
}
export interface Photo {
  name: string;
  path: string;
  thumb: string;
  size: number | null;
  taken: number | null;
  modified: number | null;
  width: number | null;
  height: number | null;
  make: string;
  camera_model: string;
  lat: number | null;
  lon: number | null;
  album: string;
  sha256: string;
  source_path: string;
}
export interface App {
  package: string;
  name: string;
  version: string;
  installed: number | null;
  updated: number | null;
  system: boolean;
  installer: string;
}

export interface DiagnosticCheck {
  id: string;
  status: "ok" | "warn" | "fail" | "info";
  detail: string;
}

export interface StepEvent {
  job: string;
  kind: Kind;
  status: "running" | "done" | "unavailable" | "error";
  progress?: number;
  count?: number;
  message?: string;
  reason?: string;
  detail?: string;
}
