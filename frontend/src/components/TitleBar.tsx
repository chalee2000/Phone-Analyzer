import clsx from "clsx";
import { FolderOpen, Minus, Moon, Square, Sun, X } from "lucide-react";
import { call } from "../lib/bridge";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { LogoMark } from "./icons";
import { Tooltip } from "./ui";

function Waves() {
  return (
    <svg className="pointer-events-none absolute right-[22%] bottom-0 h-full w-[520px] opacity-[0.16]" viewBox="0 0 520 68" preserveAspectRatio="none" aria-hidden>
      {[0, 1, 2, 3].map((i) => (
        <path
          key={i}
          d={`M0 ${48 - i * 9} C 110 ${16 - i * 4}, 210 ${70 - i * 6}, 330 ${34 - i * 7} S 470 ${10 + i * 4}, 520 ${26 - i * 3}`}
          stroke="#F2C14E"
          strokeWidth={1.2 - i * 0.15}
          fill="none"
        />
      ))}
    </svg>
  );
}

export function TitleBar() {
  const { t, lang, setLang } = useI18n();
  const { info, state, theme, setTheme, deviceName, openDialog } = useStore();
  const device = state.device;
  const connected = device && !device.offline;
  const platformLabel = device?.info.platform === "ios" ? "iOS" : "Android";

  return (
    <header className="titlebar-pattern relative z-20 flex h-[68px] shrink-0 items-center text-white select-none">
      <div className="pywebview-drag-region absolute inset-0" onDoubleClick={() => void call("window_toggle_maximize")} />
      <Waves />
      <div className="pointer-events-none relative flex items-center gap-3.5 pl-5">
        <LogoMark className="size-11 drop-shadow-[0_4px_10px_rgba(224,168,46,0.35)]" />
        <div className="leading-tight">
          <div className="font-display text-[23px] font-semibold tracking-tight">
            Phone Analysis
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-[12px] text-white/65">
            <span>{t("app.subtitle")}</span>
            <span className="h-3 w-px bg-white/30" />
            <span className="tabular">v{info?.version ?? "4.0.0"}</span>
          </div>
        </div>
      </div>

      <div className="relative ml-auto flex items-center gap-2.5 pr-1.5">
        {state.case && (
          <button
            onClick={() => openDialog("cases")}
            className="focus-ring hidden max-w-56 items-center gap-2 rounded-full border border-white/12 bg-white/[0.06] px-3 py-1.5 text-[12.5px] text-white/85 hover:bg-white/10 xl:flex"
          >
            <FolderOpen className="size-4 shrink-0 text-gold-300" />
            <span className="truncate">{state.case.case_no || state.case.title}</span>
          </button>
        )}

        <div className="flex rounded-full border border-white/12 bg-white/[0.06] p-1">
          {(["th", "en"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={clsx(
                "focus-ring h-7 rounded-full px-3.5 text-[13px] font-semibold transition",
                lang === l ? "bg-gradient-to-b from-gold-300 to-gold-500 text-navy-950 shadow" : "text-white/75 hover:text-white",
              )}
            >
              {l === "th" ? "ไทย" : "EN"}
            </button>
          ))}
        </div>

        <Tooltip label={theme === "light" ? t("theme.dark") : t("theme.light")}>
          <button
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            className="focus-ring grid size-9 place-items-center rounded-full border border-white/12 bg-white/[0.06] text-white/85 hover:bg-white/12"
            aria-label="theme"
          >
            {theme === "light" ? <Moon className="size-4" /> : <Sun className="size-4 text-gold-300" />}
          </button>
        </Tooltip>

        <div
          className={clsx(
            "flex h-9 items-center gap-2 rounded-full border px-3.5 text-[13px] font-semibold",
            connected ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-50" : "border-white/12 bg-white/[0.06] text-white/75",
          )}
        >
          <span className="relative flex size-2.5">
            {connected && <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400 opacity-60" />}
            <span className={clsx("relative size-2.5 rounded-full", connected ? "bg-emerald-400" : device ? "bg-gold-400" : "bg-white/40")} />
          </span>
          <span className="max-w-64 truncate">
            {connected
              ? `${t("conn.connected")} · ${platformLabel}${device?.demo ? ` (${t("conn.demo")})` : ""}`
              : device
                ? `${t("conn.offline")} · ${deviceName}`
                : t("conn.none")}
          </span>
        </div>

        <div className="ml-1 flex items-center">
          <WinButton label={t("win.min")} onClick={() => void call("window_minimize")}>
            <Minus className="size-4" />
          </WinButton>
          <WinButton label={t("win.max")} onClick={() => void call("window_toggle_maximize")}>
            <Square className="size-3.5" />
          </WinButton>
          <WinButton label={t("win.close")} onClick={() => void call("window_close")} danger>
            <X className="size-4.5" />
          </WinButton>
        </div>
      </div>
    </header>
  );
}

function WinButton({ children, onClick, label, danger }: { children: React.ReactNode; onClick: () => void; label: string; danger?: boolean }) {
  return (
    <button
      aria-label={label}
      onClick={onClick}
      className={clsx("grid h-10 w-11 place-items-center rounded-lg text-white/70 transition", danger ? "hover:bg-rose-600 hover:text-white" : "hover:bg-white/10 hover:text-white")}
    >
      {children}
    </button>
  );
}
