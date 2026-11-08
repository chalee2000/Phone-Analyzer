import clsx from "clsx";
import {
  BatteryCharging,
  ChevronLeft,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleX,
  Laptop,
  Lock,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Usb,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { AndroidIcon, IphoneIcon } from "../components/icons";
import { PhoneMockup } from "../components/PhoneMockup";
import { Badge, Button, Modal, Spinner } from "../components/ui";
import { call } from "../lib/bridge";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import type { DiagnosticCheck, Platform, ScannedDevice } from "../lib/types";
import { androidSteps, BRANDS, FRAME_MS, iosSteps, type Screen } from "./guides";

const ROW = 33;

/* ── Simulated phone screen ────────────────────────────────────────── */
function SimScreen({ screen, t0, ios }: { screen: Screen; t0: number; ios: boolean }) {
  // t0: ms elapsed inside this frame
  const { lang } = useI18n();
  const tapAt = 700;
  const tapping = screen.tap != null && t0 >= tapAt;
  const tapsDone = screen.taps ? Math.min(screen.taps, Math.floor((t0 - tapAt) / 210) + 1) : 0;
  let items = screen.items ?? [];
  let tap = screen.tap;
  if (tap != null && items.length > 10 && tap >= 9) {
    items = items.slice(tap - 8);
    tap = 8;
  }
  const showToast = screen.toast && (!screen.taps || tapsDone >= screen.taps) && t0 > (screen.taps ? tapAt + screen.taps * 210 : 500);
  const dialogTap = screen.dialog?.tapOk && t0 > 1500;
  return (
    <div className="absolute inset-0 flex flex-col bg-[#f4f6fa] text-[#0e1a33]">
      {/* status bar */}
      <div className="flex h-6 shrink-0 items-center justify-between px-5 pt-1 text-[9px] font-semibold text-[#334]">
        <span>14:27</span>
        <span className="flex items-center gap-1">
          {screen.usb && <Usb className="size-2.5" />}
          <BatteryCharging className="size-3" />
        </span>
      </div>
      {screen.title && (
        <div className="flex h-11 shrink-0 items-center gap-1.5 border-b border-black/5 bg-white px-3">
          {screen.back && <ChevronLeft className="size-4" />}
          <span className="truncate text-[13px] font-bold">{screen.title}</span>
        </div>
      )}
      {screen.items && (
        <div className="flex-1 overflow-hidden bg-white">
          {items.map((it, i) => {
            const active = tap === i && tapping;
            const on = it.toggle ? (it.on || (active && screen.toggleAfterTap && t0 > tapAt + 250)) : false;
            return (
              <div key={i} className={clsx("relative flex items-center gap-2.5 overflow-hidden border-b border-black/[0.04] px-3", active && "bg-gold-100/70")} style={{ height: ROW }}>
                {it.color && <span className="size-[18px] shrink-0 rounded-md" style={{ background: it.color }} />}
                <span className="min-w-0 flex-1 truncate text-[11px] font-medium">{it.label}</span>
                {it.value != null && <span className="text-[9.5px] text-[#667]">{it.value}</span>}
                {it.toggle && (
                  <span className={clsx("relative h-[14px] w-[26px] shrink-0 rounded-full transition-colors duration-300", on ? "bg-[#2f6bf3]" : "bg-[#c9cfda]")}>
                    <span className={clsx("absolute top-[2px] left-[2px] size-[10px] rounded-full bg-white transition-transform duration-300", on && "translate-x-3")} />
                  </span>
                )}
                {active &&
                  (screen.taps ? (
                    <span key={tapsDone} className="ripple" style={{ left: "60%", top: "50%", width: 34, height: 34 }} />
                  ) : (
                    t0 < tapAt + 900 && <span className="ripple" style={{ left: "60%", top: "50%", width: 34, height: 34 }} />
                  ))}
              </div>
            );
          })}
        </div>
      )}
      {screen.taps && tapping && tapsDone < screen.taps && (
        <div className="absolute inset-x-6 bottom-8 rounded-full bg-[#222]/85 px-3 py-1.5 text-center text-[9.5px] text-white">
          {lang === "th" ? `แตะอีก ${screen.taps - tapsDone} ครั้ง` : `${screen.taps - tapsDone} more taps`}
        </div>
      )}
      {(screen.usb || screen.lock || screen.pc) && !screen.items && (
        <div className={clsx("absolute inset-0 top-6 flex flex-col items-center justify-center", ios ? "bg-gradient-to-b from-[#1c2350] to-[#0b0f24] text-white" : "bg-gradient-to-b from-[#14295a] to-[#060f24] text-white")}>
          {screen.lock === "passcode" && (
            <>
              <Lock className="mb-3 size-5" />
              <div className="mb-4 text-[11px]">{ios ? "Enter Passcode" : ""}</div>
              <div className="flex gap-2.5">
                {Array.from({ length: 6 }).map((_, i) => (
                  <span key={i} className={clsx("size-2.5 rounded-full border border-white", t0 > 300 + i * 260 && "bg-white")} />
                ))}
              </div>
            </>
          )}
          {screen.lock === "trusted" && (
            <>
              <CircleCheck className="mb-3 size-12 text-emerald-400" />
              <div className="text-[12px] font-semibold">Trusted</div>
            </>
          )}
          {screen.pc && (
            <div className="flex flex-col items-center gap-3 px-4 text-center">
              <Laptop className="size-12 text-white/85" />
              <span className="rounded-xl bg-white/10 px-3 py-2 text-[10.5px] leading-snug">
                Apple Devices / iTunes
                <br />
                <span className="text-white/60">Microsoft Store</span>
              </span>
            </div>
          )}
          {screen.usb && !screen.lock && (
            <div className="flex flex-col items-center">
              <div className="font-display text-[34px] font-light">14:27</div>
              <Usb className="mt-6 size-6 text-gold-300" />
            </div>
          )}
          {screen.usb && (
            <div className="absolute -bottom-2 left-1/2 flex -translate-x-1/2 flex-col items-center" style={{ transform: `translate(-50%, ${t0 < 600 ? 30 - t0 / 20 : 0}px)` }}>
              <div className="h-5 w-6 rounded-t-md bg-[#2b3242]" />
            </div>
          )}
        </div>
      )}
      {screen.dialog && (
        <div className="absolute inset-0 flex items-end bg-black/40 p-2.5">
          <div className="w-full rounded-2xl bg-white p-3.5 shadow-xl">
            <div className="text-[12px] font-bold">{screen.dialog.title}</div>
            <div className="mt-1.5 text-[9.5px] leading-snug whitespace-pre-line text-[#556]">{screen.dialog.body}</div>
            {screen.dialog.check && (
              <div className="mt-2 flex items-center gap-1.5 text-[9.5px]">
                <span className={clsx("grid size-3 place-items-center rounded-[3px] border", t0 > 900 ? "border-[#2f6bf3] bg-[#2f6bf3]" : "border-[#99a]")}>
                  {t0 > 900 && <span className="text-[8px] leading-none text-white">✓</span>}
                </span>
                {screen.dialog.check}
              </div>
            )}
            <div className="mt-3 flex justify-end gap-4 text-[10.5px] font-bold text-[#2f6bf3]">
              <span className="opacity-70">{screen.dialog.cancel}</span>
              <span className={clsx("relative rounded px-1", dialogTap && "bg-[#2f6bf3]/10")}>
                {screen.dialog.ok}
                {dialogTap && t0 < 2400 && <span className="ripple" style={{ left: "50%", top: "50%", width: 30, height: 30 }} />}
              </span>
            </div>
          </div>
        </div>
      )}
      {showToast && <div className="absolute inset-x-5 bottom-7 rounded-full bg-[#222]/90 px-3 py-1.5 text-center text-[9.5px] font-semibold text-white shadow-lg">{screen.toast}</div>}
    </div>
  );
}

/* ── Dialog ────────────────────────────────────────────────────────── */
function StatusIcon({ status }: { status?: string }) {
  if (status === "ok") return <CircleCheck className="size-5 text-emerald-500" />;
  if (status === "warn") return <CircleAlert className="size-5 text-amber-500" />;
  if (status === "fail") return <CircleX className="size-5 text-rose-500" />;
  return <CircleDashed className="size-5 text-faint" />;
}

function Tip({ title, desc, status, dim, badge }: { title: ReactNode; desc?: ReactNode; status?: string; dim?: boolean; badge?: ReactNode }) {
  return (
    <div className={clsx("flex gap-3 rounded-xl px-2 py-2.5", dim && "opacity-45")}>
      <span className="mt-0.5 shrink-0">
        <StatusIcon status={status} />
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-[13.5px] font-semibold text-ink">
          {title} {badge}
        </div>
        {desc && <div className="mt-0.5 text-[12.5px] leading-relaxed text-muted">{desc}</div>}
      </div>
    </div>
  );
}

export function DiagnosticsDialog() {
  const { t, lang } = useI18n();
  const { dialogs, closeDialog, connect, setPlatform } = useStore();
  const cfg = dialogs.diag;
  const open = !!cfg;
  const [platform, setDiagPlatform] = useState<Platform>("android");
  const [brandId, setBrandId] = useState<string>(() => {
    try {
      return localStorage.getItem("spni.brand") || "xiaomi";
    } catch {
      return "xiaomi";
    }
  });
  const [step, setStep] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [big, setBig] = useState(false);
  const [checks, setChecks] = useState<DiagnosticCheck[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [restarting, setRestarting] = useState(false);

  useEffect(() => {
    if (cfg) {
      setDiagPlatform(cfg.platform);
      setStep(0);
      setElapsed(0);
      setPlaying(true);
    }
  }, [cfg]);

  const brand = BRANDS.find((b) => b.id === brandId) ?? BRANDS[1];
  const ios = platform === "ios";
  const steps = useMemo(() => (ios ? iosSteps(lang) : androidSteps(lang, brand)), [ios, lang, brand]);
  const durations = steps.map((s) => s.length * FRAME_MS);
  const total = durations.reduce((a, b) => a + b, 0);
  const before = durations.slice(0, step).reduce((a, b) => a + b, 0);

  useEffect(() => {
    if (!open || !playing) return;
    const id = window.setInterval(() => {
      setElapsed((e) => {
        const next = e + 100;
        if (next >= durations[step]) {
          if (step < steps.length - 1) {
            setStep((s) => s + 1);
            return 0;
          }
          setPlaying(false);
          return durations[step];
        }
        return next;
      });
    }, 100);
    return () => window.clearInterval(id);
  }, [open, playing, step, durations, steps.length]);

  const runChecks = useCallback(async () => {
    setChecking(true);
    try {
      setChecks(await call<DiagnosticCheck[]>("diagnostics", platform));
    } catch {
      setChecks([]);
    } finally {
      setChecking(false);
    }
  }, [platform]);

  useEffect(() => {
    if (open) void runChecks();
  }, [open, runChecks]);

  const frameIndex = Math.min(steps[step].length - 1, Math.floor(elapsed / FRAME_MS));
  const screen = steps[step][frameIndex];
  const t0 = elapsed - frameIndex * FRAME_MS;
  const fmt = (ms: number) => `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, "0")}`;
  const pickBrand = (id: string) => {
    setBrandId(id);
    try {
      localStorage.setItem("spni.brand", id);
    } catch {
      /* ignore */
    }
    setStep(0);
    setElapsed(0);
    setPlaying(true);
  };
  const recheck = async () => {
    await runChecks();
    const res = await call<{ devices: ScannedDevice[] }>("scan_devices", platform);
    const ready = res.devices.filter((d) => d.platform === platform && d.state === "ready" && !d.demo);
    if (ready.length) {
      closeDialog("diag");
      setPlatform(platform);
      await connect(ready[0].id);
    }
  };
  const restartAdb = async () => {
    setRestarting(true);
    try {
      await call("restart_adb");
      toast.success(t("diag.adbRestarted"));
      await runChecks();
    } finally {
      setRestarting(false);
    }
  };
  const status = (id: string) => checks?.find((c) => c.id === id)?.status;
  const stepNames = ios ? [t("diag.iosStep1"), t("diag.iosStep2"), t("diag.iosStep3")] : [t("diag.step1"), t("diag.step2"), t("diag.step3")];
  const title = cfg?.notFound ? (ios ? t("diag.notFoundIos") : t("diag.notFoundAndroid")) : ios ? t("diag.titleIos") : t("diag.titleAndroid");

  return (
    <Modal open={open} onClose={() => closeDialog("diag")} width={big ? 1320 : 1200} className="h-[min(860px,calc(100vh-48px))]">
      <div className="flex shrink-0 items-center gap-3 border-b border-line px-6 py-4" data-testid="diag-dialog">
        <span className={clsx("grid size-10 place-items-center rounded-xl", ios ? "bg-violet-50 text-violet-600 dark:bg-violet-500/15" : "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15")}>
          {ios ? <IphoneIcon className="size-5" /> : <AndroidIcon className="size-5 text-[#3DDC84]" />}
        </span>
        <h2 className="font-display text-[22px] font-semibold text-ink">{title}</h2>
        <div className="ml-auto flex rounded-xl bg-surface-3 p-1">
          {(["android", "ios"] as const).map((p) => (
            <button
              key={p}
              onClick={() => {
                setDiagPlatform(p);
                setStep(0);
                setElapsed(0);
                setPlaying(true);
              }}
              className={clsx("h-8 rounded-lg px-3.5 text-[13px] font-semibold", platform === p ? "bg-surface text-ink shadow" : "text-muted")}
            >
              {p === "ios" ? "iPhone" : "Android"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* brands */}
        {!ios && (
          <div className="flex w-[240px] shrink-0 flex-col border-r border-line bg-surface-2/60 p-4">
            <div className="mb-2 px-1 font-display text-[16px] font-semibold text-ink">{t("diag.brand")}</div>
            <div className="flex flex-col gap-0.5">
              {BRANDS.map((b) => (
                <button
                  key={b.id}
                  onClick={() => pickBrand(b.id)}
                  className={clsx(
                    "relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[14px] transition",
                    brandId === b.id ? "bg-surface font-semibold text-ink shadow-sm ring-1 ring-line" : "text-ink-2 hover:bg-surface/70",
                    b.id === "other" && "mt-2 border-t border-line pt-3",
                  )}
                >
                  {brandId === b.id && <span className="absolute top-2 bottom-2 left-0 w-[3px] rounded-full bg-gold-400" />}
                  <span className={clsx("grid size-[18px] place-items-center rounded-full border-2", brandId === b.id ? "border-navy-600 dark:border-gold-400" : "border-line-strong")}>
                    {brandId === b.id && <span className="size-2 rounded-full bg-navy-600 dark:bg-gold-400" />}
                  </span>
                  {b.name || t("diag.other")}
                </button>
              ))}
            </div>
            <p className="mt-auto px-1 text-[12px] leading-relaxed text-faint">{t("diag.brandHint")}</p>
          </div>
        )}

        {/* phone */}
        <div className="flex shrink-0 flex-col items-center gap-4 bg-gradient-to-b from-navy-50/60 to-transparent px-8 py-6 dark:from-navy-900/50">
          <div className="w-full rounded-2xl bg-gradient-to-r from-navy-800 to-navy-950 px-4 py-3 text-white shadow-lg">
            <div className="flex items-center gap-2">
              <span className="font-display text-[15px] font-semibold">{t("diag.step", { n: step + 1 })}</span>
              <span className="ml-auto max-w-40 truncate rounded-full bg-white/12 px-2.5 py-0.5 text-[11px]">{ios ? "iPhone" : brand.name || t("diag.other")}</span>
            </div>
            <div className="mt-0.5 flex items-center justify-between text-[13px] text-gold-300">
              {stepNames[step]}
              <button onClick={() => setPlaying((p) => !p)} className="grid size-7 place-items-center rounded-full bg-white/12 hover:bg-white/20">
                {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
              </button>
            </div>
          </div>
          <PhoneMockup platform={platform} width={big ? 280 : 232} screen={<SimScreen screen={screen} t0={t0} ios={ios} />} />
        </div>

        {/* guide */}
        <div className="flex min-w-0 flex-1 flex-col overflow-auto px-6 py-5">
          <p className="text-[13.5px] text-muted">{ios ? t("diag.introIos") : t("diag.intro")}</p>
          <h3 className="mt-2 font-display text-[19px] font-semibold text-ink">
            {t("diag.howto")}: <span className="text-navy-600 dark:text-gold-300">{ios ? "iPhone" : brand.name || t("diag.other")}</span>
          </h3>
          <div className="mt-3 flex items-center gap-2">
            <Button variant="primary" icon={playing ? <Pause className="size-4" /> : <Play className="size-4" />} onClick={() => setPlaying((p) => !p)} className="min-w-32">
              {playing ? t("diag.pause") : t("diag.play")}
            </Button>
            <Button
              variant="outline"
              icon={<RotateCcw className="size-4" />}
              onClick={() => {
                setStep(0);
                setElapsed(0);
                setPlaying(true);
              }}
            >
              {t("diag.restart")}
            </Button>
            <Button variant="outline" icon={big ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />} onClick={() => setBig((b) => !b)}>
              {big ? t("diag.shrink") : t("diag.expand")}
            </Button>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <div className="flex flex-1 gap-1">
              {durations.map((d, i) => (
                <div key={i} className="h-1.5 overflow-hidden rounded-full bg-surface-3" style={{ flex: d }}>
                  <div className="h-full bg-gradient-to-r from-navy-500 to-navy-700 dark:from-gold-300 dark:to-gold-500" style={{ width: i < step ? "100%" : i === step ? `${(elapsed / d) * 100}%` : "0%" }} />
                </div>
              ))}
            </div>
            <span className="tabular text-[12.5px] text-muted">
              {fmt(before + elapsed)} / {fmt(total)}
            </span>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {stepNames.map((n, i) => (
              <button
                key={i}
                onClick={() => {
                  setStep(i);
                  setElapsed(0);
                  setPlaying(true);
                }}
                className={clsx(
                  "relative rounded-xl border px-3 py-2 text-center transition",
                  step === i ? "border-navy-700 bg-navy-800 text-white dark:border-gold-400 dark:bg-gold-400 dark:text-navy-950" : "border-line bg-surface hover:bg-surface-2",
                )}
              >
                <div className="text-[13px] font-bold">{t("diag.step", { n: i + 1 })}</div>
                <div className={clsx("truncate text-[12px]", step === i ? "opacity-85" : "text-muted")}>{n}</div>
                {step === i && <span className="absolute right-4 bottom-0 left-4 h-[3px] rounded-full bg-gold-400 dark:bg-navy-900" />}
              </button>
            ))}
          </div>
          <p className="mt-3 text-[13px] text-ink-2">{t("diag.after")}</p>
          <p className="text-[12px] text-faint">{t("diag.disclaimer")}</p>

          <div className="mt-4 rounded-2xl border border-line bg-surface-2/50 p-3">
            <div className="mb-1 flex items-center gap-2 px-2 font-display text-[16px] font-semibold text-ink">
              {t("diag.checklist")}
              {checking && <Spinner className="size-4 text-muted" />}
            </div>
            {(checks ?? []).map((c) => (
              <Tip key={c.id} title={t(`chk.${c.id}`)} desc={c.detail && <span className="font-mono text-[11.5px]">{c.detail}</span>} status={c.status} />
            ))}
            {ios ? (
              <>
                <Tip title={t("tip.iosUnlock")} desc={t("tip.iosUnlockDesc")} />
                <Tip title={t("tip.iosTrust")} desc={t("tip.iosTrustDesc")} />
                <Tip title={t("tip.iosDriver")} desc={t("tip.iosDriverDesc")} status={status("apple_service")} />
                <Tip title={t("tip.cable")} desc={t("tip.cableDesc")} />
              </>
            ) : (
              <>
                <Tip title={t("tip.dev")} desc={t("tip.devDesc")} />
                <Tip title={t("tip.usb")} desc={<>{t("tip.usbDesc")} {brand.id === "xiaomi" && <span className="block">{t("tip.xiaomi")}</span>}</>} />
                <Tip title={t("tip.allow")} desc={t("tip.allowDesc")} />
                <Tip
                  title={t("tip.autoblocker")}
                  desc={t("tip.autoblockerDesc")}
                  dim={brand.id !== "samsung"}
                  badge={<Badge tone="gold">{t("tip.samsungOnly")}</Badge>}
                />
                <Tip title={t("tip.driver")} desc={t("tip.driverDesc")} status={status("usb_driver")} />
                <Tip title={t("tip.cable")} desc={t("tip.cableDesc")} />
              </>
            )}
          </div>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2 border-t border-line bg-surface-2 px-6 py-3.5">
        <Button variant="primary" icon={<Search className="size-4" />} onClick={() => void recheck()} loading={checking} data-testid="diag-recheck">
          {t("diag.recheck")}
        </Button>
        {!ios && (
          <Button variant="outline" icon={<RefreshCw className="size-4" />} onClick={() => void restartAdb()} loading={restarting}>
            {t("diag.restartAdb")}
          </Button>
        )}
        <Button variant="outline" className="ml-auto min-w-28" onClick={() => closeDialog("diag")}>
          {t("diag.close")}
        </Button>
      </div>
    </Modal>
  );
}
