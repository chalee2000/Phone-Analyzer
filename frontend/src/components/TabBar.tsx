import clsx from "clsx";
import { AppWindow, Globe, Image, Mic, MessageSquareText, MessagesSquare, NotebookPen, Phone, Smartphone, Users, Wifi, CreditCard } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { useI18n } from "../lib/i18n";
import { useStore, type Tab } from "../lib/store";

export const TAB_ICONS: Record<Tab, ReactNode> = {
  device: <Smartphone className="size-[18px]" />,
  calls: <Phone className="size-[18px]" />,
  contacts: <Users className="size-[18px]" />,
  sms: <MessageSquareText className="size-[18px]" />,
  chats: <MessagesSquare className="size-[18px]" />,
  web: <Globe className="size-[18px]" />,
  notes: <NotebookPen className="size-[18px]" />,
  voice: <Mic className="size-[18px]" />,
  wifi: <Wifi className="size-[18px]" />,
  sim: <CreditCard className="size-[18px]" />,
  photos: <Image className="size-[18px]" />,
  apps: <AppWindow className="size-[18px]" />,
};

const ORDER: Tab[] = ["device", "calls", "contacts", "sms", "chats", "web", "notes", "voice", "wifi", "sim", "photos", "apps"];

export function TabBar() {
  const { t } = useI18n();
  const { tab, setTab, state } = useStore();
  const unavailable = state.extraction?.unavailable ?? {};
  return (
    <nav className="mx-5 mt-3 flex shrink-0 items-end gap-0.5 overflow-x-auto rounded-2xl border border-line bg-surface-2/80 px-1.5 pt-1.5 backdrop-blur" role="tablist">
      {ORDER.map((key) => {
        const active = tab === key;
        const count = key === "device" ? undefined : state.counts[key];
        const off = key !== "device" && !!unavailable[key] && !count;
        return (
          <button
            key={key}
            role="tab"
            data-testid={`tab-${key}`}
            aria-selected={active}
            onClick={() => setTab(key)}
            className={clsx(
              "focus-ring relative flex h-11 shrink-0 items-center gap-1.5 rounded-t-xl px-3 text-[13.5px] font-semibold whitespace-nowrap transition-colors",
              active ? "text-navy-900 dark:text-white" : "text-muted hover:text-ink",
            )}
          >
            {active && (
              <motion.span
                layoutId="tab-bg"
                className="absolute inset-0 rounded-t-xl bg-surface shadow-[0_-2px_10px_-4px_rgba(16,32,72,0.15)]"
                transition={{ type: "spring", stiffness: 500, damping: 40 }}
              />
            )}
            <span className={clsx("relative", active ? "text-navy-600 dark:text-gold-300" : off ? "opacity-50" : "")}>{TAB_ICONS[key]}</span>
            <span className={clsx("relative", off && "opacity-60")}>{t(`tab.${key}`)}</span>
            {count != null && count > 0 && (
              <span
                className={clsx(
                  "tabular relative rounded-full px-1.5 text-[11.5px] leading-5 font-bold",
                  active ? "bg-gold-400 text-navy-950" : "bg-rose-50 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300",
                )}
              >
                {count.toLocaleString()}
              </span>
            )}
            {active && <motion.span layoutId="tab-line" className="absolute right-3 bottom-0 left-3 h-[3px] rounded-full bg-gold-400" />}
          </button>
        );
      })}
    </nav>
  );
}
