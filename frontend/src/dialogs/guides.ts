/**
 * Brand-specific menu names for the animated "enable USB debugging" guide.
 * Names follow each vendor's Thai / English UI closely; they can differ a
 * little between models and OS versions (the dialog says so).
 */
import type { Lang } from "../lib/i18n";

type L = { th: string; en: string };

export interface BrandGuide {
  id: string;
  name: string;
  about: L;
  aboutSub?: L;
  build: L;
  devParent?: L;
  devOptions: L;
  extraToggles?: L[];
}

const l = (th: string, en: string): L => ({ th, en });

export const BRANDS: BrandGuide[] = [
  {
    id: "samsung",
    name: "Samsung",
    about: l("เกี่ยวกับโทรศัพท์", "About phone"),
    aboutSub: l("ข้อมูลซอฟต์แวร์", "Software information"),
    build: l("หมายเลขรุ่นสร้าง", "Build number"),
    devOptions: l("ตัวเลือกผู้พัฒนา", "Developer options"),
  },
  {
    id: "xiaomi",
    name: "Xiaomi / Redmi / POCO",
    about: l("เกี่ยวกับโทรศัพท์", "About phone"),
    build: l("เวอร์ชัน OS", "OS version"),
    devParent: l("การตั้งค่าเพิ่มเติม", "Additional settings"),
    devOptions: l("ตัวเลือกสำหรับนักพัฒนา", "Developer options"),
    extraToggles: [l("ติดตั้งผ่าน USB", "Install via USB"), l("การแก้ไขข้อบกพร่อง USB (การตั้งค่าความปลอดภัย)", "USB debugging (Security settings)")],
  },
  {
    id: "oppo",
    name: "OPPO / OnePlus",
    about: l("เกี่ยวกับอุปกรณ์", "About device"),
    aboutSub: l("เวอร์ชัน", "Version"),
    build: l("หมายเลขรุ่นสร้าง", "Build number"),
    devParent: l("การตั้งค่าเพิ่มเติม", "Additional settings"),
    devOptions: l("ตัวเลือกสำหรับนักพัฒนา", "Developer options"),
  },
  {
    id: "realme",
    name: "realme",
    about: l("เกี่ยวกับอุปกรณ์", "About device"),
    aboutSub: l("เวอร์ชัน", "Version"),
    build: l("หมายเลขรุ่นสร้าง", "Build number"),
    devParent: l("การตั้งค่าเพิ่มเติม", "Additional settings"),
    devOptions: l("ตัวเลือกสำหรับนักพัฒนา", "Developer options"),
  },
  {
    id: "vivo",
    name: "vivo / iQOO",
    about: l("เกี่ยวกับโทรศัพท์", "About phone"),
    aboutSub: l("ข้อมูลเวอร์ชัน", "Version information"),
    build: l("เวอร์ชันซอฟต์แวร์", "Software version"),
    devParent: l("การจัดการระบบ", "System management"),
    devOptions: l("ตัวเลือกสำหรับนักพัฒนา", "Developer options"),
  },
  {
    id: "huawei",
    name: "HUAWEI",
    about: l("เกี่ยวกับโทรศัพท์", "About phone"),
    build: l("หมายเลขรุ่นสร้าง", "Build number"),
    devParent: l("ระบบและการอัปเดต", "System & updates"),
    devOptions: l("ตัวเลือกนักพัฒนา", "Developer options"),
  },
  {
    id: "honor",
    name: "HONOR",
    about: l("เกี่ยวกับโทรศัพท์", "About phone"),
    build: l("หมายเลขรุ่นสร้าง", "Build number"),
    devParent: l("ระบบและการอัปเดต", "System & updates"),
    devOptions: l("ตัวเลือกนักพัฒนา", "Developer options"),
  },
  {
    id: "pixel",
    name: "Google Pixel",
    about: l("เกี่ยวกับโทรศัพท์", "About phone"),
    build: l("หมายเลขบิลด์", "Build number"),
    devParent: l("ระบบ", "System"),
    devOptions: l("ตัวเลือกสำหรับนักพัฒนาแอป", "Developer options"),
  },
  {
    id: "other",
    name: "",
    about: l("เกี่ยวกับโทรศัพท์", "About phone"),
    build: l("หมายเลขบิลด์", "Build number"),
    devParent: l("ระบบ", "System"),
    devOptions: l("ตัวเลือกสำหรับนักพัฒนา", "Developer options"),
  },
];

export interface Item {
  label: string;
  color?: string;
  value?: string;
  toggle?: boolean;
  on?: boolean;
}

export interface Screen {
  title: string;
  back?: boolean;
  items?: Item[];
  tap?: number; // index of the tapped item
  taps?: number; // repeated taps on the same item
  toggleAfterTap?: boolean;
  toast?: string;
  dialog?: { title: string; body: string; check?: string; ok: string; cancel: string; tapOk?: boolean };
  usb?: boolean;
  lock?: "passcode" | "trusted";
  pc?: boolean;
}

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#f43f5e", "#14b8a6", "#ec4899", "#64748b", "#6366f1", "#eab308", "#0ea5e9", "#22c55e"];

function settingsList(lang: Lang, b: BrandGuide, extra?: string): Item[] {
  const th = lang === "th";
  const base = th
    ? ["การเชื่อมต่อ", "เสียงและการสั่น", "การแจ้งเตือน", "การแสดงผล", "วอลล์เปเปอร์", "หน้าจอล็อก", "ความปลอดภัย", "บัญชี", "แบตเตอรี่", "แอป"]
    : ["Connections", "Sounds & vibration", "Notifications", "Display", "Wallpaper", "Lock screen", "Security", "Accounts", "Battery", "Apps"];
  const items = [b.about[lang], ...base];
  if (extra) items.push(extra);
  return items.map((label, i) => ({ label, color: COLORS[i % COLORS.length] }));
}

export function androidSteps(lang: Lang, b: BrandGuide): Screen[][] {
  const th = lang === "th";
  const settings = th ? "การตั้งค่า" : "Settings";
  const usbDebug = th ? "การแก้ไขข้อบกพร่อง USB" : "USB debugging";
  // Step 1 — developer mode
  const s1: Screen[] = [{ title: settings, items: settingsList(lang, b), tap: 0 }];
  const aboutItems: Item[] = (th
    ? [["ชื่ออุปกรณ์", "Phone"], ["รุ่น", "25028RN03A"], ["หน่วยความจำ", "128 GB"], ["โปรเซสเซอร์", "8 cores"], ["RAM", "8 GB"]]
    : [["Device name", "Phone"], ["Model", "25028RN03A"], ["Storage", "128 GB"], ["Processor", "8 cores"], ["RAM", "8 GB"]]
  ).map(([label, value]) => ({ label, value }));
  const status = { label: th ? "สถานะ" : "Status" };
  const legal = { label: th ? "ข้อมูลทางกฎหมาย" : "Legal information" };
  const devToast = th ? "คุณเป็นนักพัฒนาแล้ว!" : "You are now a developer!";
  if (b.aboutSub) {
    s1.push({ title: b.about[lang], back: true, items: [...aboutItems, { label: b.aboutSub[lang] }, status, legal], tap: 5 });
    s1.push({
      title: b.aboutSub[lang],
      back: true,
      items: [
        { label: th ? "เวอร์ชัน Android" : "Android version", value: "15" },
        { label: th ? "แพตช์ความปลอดภัย" : "Security patch", value: "2025-09" },
        { label: th ? "เวอร์ชันเบสแบนด์" : "Baseband version", value: "M2.1" },
        { label: b.build[lang], value: "AP3A.2409" },
        { label: th ? "เวอร์ชันเคอร์เนล" : "Kernel version", value: "6.1" },
      ],
      tap: 3,
      taps: 7,
      toast: devToast,
    });
  } else {
    s1.push({
      title: b.about[lang],
      back: true,
      items: [...aboutItems, { label: b.build[lang], value: "OS2.0.208" }, { label: "Android", value: "15" }, status, legal],
      tap: 5,
      taps: 7,
      toast: devToast,
    });
  }
  // Step 2 — USB debugging
  const s2: Screen[] = [];
  if (b.devParent) {
    s2.push({ title: settings, items: settingsList(lang, b, b.devParent[lang]), tap: 11 });
    const parentItems = (th
      ? ["วันที่และเวลา", "ภาษาและการป้อนข้อมูล", "การสำรองข้อมูล", "การเข้าถึง", "ทางลัดปุ่มกด"]
      : ["Date & time", "Languages & input", "Backup", "Accessibility", "Button shortcuts"]
    ).map((label) => ({ label }));
    const after = (th ? ["รีเซ็ตค่า", "การอัปเดตระบบ"] : ["Reset options", "System update"]).map((label) => ({ label }));
    s2.push({ title: b.devParent[lang], back: true, items: [...parentItems, { label: b.devOptions[lang] }, ...after], tap: 5 });
  } else {
    s2.push({ title: settings, items: settingsList(lang, b, b.devOptions[lang]), tap: 11 });
  }
  const devItems: Item[] = [
    { label: b.devOptions[lang], toggle: true, on: true },
    { label: th ? "เปิดหน้าจอค้างไว้" : "Stay awake", toggle: true, on: false },
    { label: usbDebug, toggle: true, on: false },
    ...(b.extraToggles ?? []).map((x) => ({ label: x[lang], toggle: true, on: false })),
    { label: th ? "ยกเลิกการให้สิทธิ์แก้ไขข้อบกพร่อง USB" : "Revoke USB debugging authorizations" },
    { label: th ? "ตัวเลือกการกำหนดค่า USB" : "Default USB configuration", value: "MTP" },
    { label: th ? "การแก้ไขข้อบกพร่องไร้สาย" : "Wireless debugging", toggle: true, on: false },
  ];
  s2.push({ title: b.devOptions[lang], back: true, items: devItems, tap: 2, toggleAfterTap: true });
  s2.push({
    title: b.devOptions[lang],
    back: true,
    items: devItems,
    dialog: {
      title: th ? "อนุญาตการแก้ไขข้อบกพร่อง USB?" : "Allow USB debugging?",
      body: th ? "การแก้ไขข้อบกพร่อง USB มีไว้เพื่อการพัฒนาเท่านั้น" : "USB debugging is intended for development purposes only.",
      ok: th ? "ตกลง" : "OK",
      cancel: th ? "ยกเลิก" : "Cancel",
      tapOk: true,
    },
  });
  if (b.extraToggles?.length) {
    s2.push({ title: b.devOptions[lang], back: true, items: devItems.map((it, i) => (i === 2 ? { ...it, on: true } : it)), tap: 3, toggleAfterTap: true });
  }
  // Step 3 — plug in and allow
  const s3: Screen[] = [
    { title: "", usb: true },
    {
      title: "",
      usb: true,
      dialog: {
        title: th ? "อนุญาตการแก้ไขข้อบกพร่อง USB หรือไม่" : "Allow USB debugging?",
        body: th ? "ลายนิ้วมือคีย์ RSA ของคอมพิวเตอร์:\n4F:2A:91:…:C7:0E" : "The computer's RSA key fingerprint is:\n4F:2A:91:…:C7:0E",
        check: th ? "อนุญาตจากคอมพิวเตอร์นี้เสมอ" : "Always allow from this computer",
        ok: th ? "อนุญาต" : "Allow",
        cancel: th ? "ไม่อนุญาต" : "Deny",
        tapOk: true,
      },
    },
    { title: "", usb: true, toast: th ? "เชื่อมต่อการแก้ไขข้อบกพร่อง USB แล้ว" : "USB debugging connected" },
  ];
  return [s1, s2, s3];
}

export function iosSteps(lang: Lang): Screen[][] {
  const th = lang === "th";
  return [
    [{ title: "", lock: "passcode" }, { title: "", lock: "passcode", toast: th ? "ปลดล็อกแล้ว" : "Unlocked" }],
    [
      {
        title: "",
        usb: true,
        dialog: {
          title: th ? "เชื่อถือคอมพิวเตอร์เครื่องนี้หรือไม่" : "Trust This Computer?",
          body: th ? "การตั้งค่าและข้อมูลของคุณจะเข้าถึงได้จากคอมพิวเตอร์เครื่องนี้เมื่อเชื่อมต่อแล้ว" : "Your settings and data will be accessible from this computer when connected.",
          ok: th ? "เชื่อถือ" : "Trust",
          cancel: th ? "ไม่เชื่อถือ" : "Don't Trust",
          tapOk: true,
        },
      },
      { title: "", usb: true, lock: "passcode" },
      { title: "", usb: true, lock: "trusted" },
    ],
    [{ title: "", pc: true }, { title: "", pc: true, toast: "Apple Mobile Device Service ✓" }],
  ];
}

export const FRAME_MS = 2600;
