import clsx from "clsx";
import { Image as ImageIcon, MessageCircle, Phone, Signal, Wifi } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { fmtLongDate } from "../lib/format";
import { useI18n } from "../lib/i18n";
import type { Platform } from "../lib/types";

const pad = (n: number) => String(n).padStart(2, "0");
const BASE_W = 180; // the lock screen is laid out at this width, then scaled

function useClock() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

function AndroidWallpaper() {
  return (
    <svg className="absolute inset-0 size-full" viewBox="0 0 200 420" preserveAspectRatio="xMidYMid slice" aria-hidden>
      <defs>
        <linearGradient id="wp-a" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#14295a" />
          <stop offset="1" stopColor="#060f24" />
        </linearGradient>
        <linearGradient id="wp-g" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#f8d77a" />
          <stop offset="1" stopColor="#b9850f" />
        </linearGradient>
      </defs>
      <rect width="200" height="420" fill="url(#wp-a)" />
      {[0, 1, 2].map((i) => (
        <path
          key={i}
          d={`M-20 ${300 + i * 26} C 40 ${250 + i * 26}, 90 ${330 + i * 26}, 150 ${250 + i * 26} S 230 ${190 + i * 26}, 240 ${200 + i * 26}`}
          stroke="url(#wp-g)"
          strokeWidth={14 - i * 3}
          strokeOpacity={0.85 - i * 0.22}
          fill="none"
          strokeLinecap="round"
        />
      ))}
    </svg>
  );
}

function IosWallpaper() {
  return (
    <div className="absolute inset-0 bg-[#0d1338]">
      <div className="absolute -top-10 -left-16 size-56 rounded-full bg-[#5b5bf0] opacity-70 blur-2xl" />
      <div className="absolute top-40 -right-20 size-56 rounded-full bg-[#d14fb0] opacity-60 blur-2xl" />
      <div className="absolute -bottom-10 left-0 size-56 rounded-full bg-[#f0a33b] opacity-55 blur-2xl" />
    </div>
  );
}

function DockIcon({ className, children }: { className: string; children: ReactNode }) {
  return <span className={clsx("grid size-9 place-items-center rounded-full text-white shadow-md", className)}>{children}</span>;
}

export function PhoneMockup({
  platform,
  battery,
  connected,
  width = 196,
  screen,
}: {
  platform: Platform;
  battery?: number | null;
  connected?: boolean;
  width?: number;
  screen?: ReactNode;
}) {
  const { lang } = useI18n();
  const now = useClock();
  const d = new Date(now);
  const ios = platform === "ios";
  const height = Math.round(width * 2.08);
  return (
    <div className="relative shrink-0" style={{ width, height }}>
      {connected && (
        <>
          <div className="animate-pulse-ring absolute -inset-5 rounded-[64px] border-2 border-gold-400/50" />
          <div className="absolute -inset-10 rounded-full bg-gold-400/10 blur-2xl" />
        </>
      )}
      {/* side buttons */}
      <span className="absolute top-[22%] -right-[3px] h-[12%] w-[4px] rounded-r bg-[#2a3140]" />
      <span className="absolute top-[38%] -right-[3px] h-[7%] w-[4px] rounded-r bg-[#2a3140]" />
      {ios && <span className="absolute top-[18%] -left-[3px] h-[6%] w-[4px] rounded-l bg-[#2a3140]" />}
      <div
        className="relative size-full rounded-[44px] bg-gradient-to-b from-[#3a4253] via-[#1b212c] to-[#0e1218] p-[8px] shadow-[0_30px_60px_-20px_rgba(8,19,41,0.55),inset_0_0_0_1px_rgba(255,255,255,0.08)]"
      >
        <div className="relative size-full overflow-hidden rounded-[37px] bg-black">
          {screen ?? (
            <div
              className="absolute top-0 left-0 origin-top-left"
              style={{ width: BASE_W, height: (height - 16) / ((width - 16) / BASE_W), transform: `scale(${(width - 16) / BASE_W})` }}
            >
              {ios ? <IosWallpaper /> : <AndroidWallpaper />}
              {/* status bar */}
              <div className="absolute inset-x-0 top-0 flex items-center justify-between px-5 pt-2.5 text-[9.5px] font-semibold text-white/90">
                <span className="tabular">{`${pad(d.getHours())}:${pad(d.getMinutes())}`}</span>
                <span className="flex items-center gap-1">
                  <Signal className="size-2.5" />
                  <Wifi className="size-2.5" />
                  <span className="relative h-[8px] w-[16px] rounded-[2px] border border-white/80">
                    <span className="absolute inset-[1px] rounded-[1px] bg-white" style={{ width: `${Math.max(8, battery ?? 70) * 0.13}px` }} />
                  </span>
                </span>
              </div>
              {ios ? (
                <span className="absolute top-2 left-1/2 h-[20px] w-[64px] -translate-x-1/2 rounded-full bg-black" />
              ) : (
                <span className="absolute top-[10px] left-1/2 size-[10px] -translate-x-1/2 rounded-full bg-black ring-2 ring-white/5" />
              )}
              {/* clock */}
              <div className={clsx("absolute inset-x-0 text-center text-white", ios ? "top-[17%]" : "top-[14%]")}>
                {ios && <div className="text-[11px] font-medium text-white/85">{fmtLongDate(now, lang)}</div>}
                <div className={clsx("tabular font-display leading-none", ios ? "text-[52px] font-semibold" : "text-[44px] font-light")}>
                  {`${pad(d.getHours())}:${pad(d.getMinutes())}`}
                </div>
                {!ios && <div className="mt-1 text-[10.5px] text-white/80">{fmtLongDate(now, lang)}</div>}
              </div>
              {/* dock */}
              <div className="absolute inset-x-0 bottom-[6%] flex justify-center gap-3">
                <DockIcon className="bg-gradient-to-b from-sky-400 to-blue-600">
                  <Phone className="size-4" />
                </DockIcon>
                <DockIcon className="bg-gradient-to-b from-emerald-400 to-green-600">
                  <MessageCircle className="size-4" />
                </DockIcon>
                <DockIcon className="bg-gradient-to-b from-amber-300 to-orange-500">
                  <ImageIcon className="size-4" />
                </DockIcon>
              </div>
              {ios && <span className="absolute bottom-[2%] left-1/2 h-[4px] w-[34%] -translate-x-1/2 rounded-full bg-white/80" />}
            </div>
          )}
          {/* glass reflection */}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/[0.10] via-transparent to-transparent" />
        </div>
      </div>
    </div>
  );
}
