import clsx from "clsx";
import { ChevronRight, CircleHelp, History, MessageCircle, Search, ShieldCheck, Sparkles, Usb } from "lucide-react";
import { motion } from "motion/react";
import { useEffect } from "react";
import { AndroidIcon, IphoneIcon } from "../components/icons";
import { PhoneMockup } from "../components/PhoneMockup";
import { Badge, Button } from "../components/ui";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";

function ConnectScreen() {
  const { lang } = useI18n();
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-b from-[#1b2335] to-[#0b0f18] text-white/80">
      <div className="mb-4 grid size-14 place-items-center rounded-full bg-white/5 ring-1 ring-white/10">
        <Usb className="size-7" />
      </div>
      <div className="text-center text-[11px] leading-snug text-white/60">
        {lang === "th" ? (
          <>
            เชื่อมต่อ
            <br />
            อุปกรณ์ของคุณ
          </>
        ) : (
          <>
            Connect
            <br />
            your device
          </>
        )}
      </div>
    </div>
  );
}

function Illustration() {
  return (
    <div className="relative flex h-full items-center justify-center overflow-hidden">
      <div className="absolute size-[460px] rounded-full bg-gradient-to-br from-navy-50 to-[#e6ecf7] dark:from-navy-900 dark:to-navy-950" />
      <div className="absolute size-[560px] rounded-full border border-navy-100/80 dark:border-navy-800/60" />
      <div className="absolute size-[660px] rounded-full border border-dashed border-navy-100/70 dark:border-navy-800/40" />
      <div className="animate-float relative -mt-10">
        <PhoneMockup platform="android" width={190} screen={<ConnectScreen />} />
        <div className="absolute top-full left-1/2 -translate-x-1/2">
          <div className="animate-plug flex flex-col items-center">
            <div className="grid h-12 w-9 place-items-center rounded-lg bg-gradient-to-b from-[#2b3242] to-[#11151d] text-white/70 shadow-lg">
              <Usb className="size-4" />
            </div>
            <div className="h-80 w-[10px] rounded-b-full bg-gradient-to-b from-[#1c2230] to-[#0d1118]" />
          </div>
        </div>
      </div>
      {[
        { label: "ADB", className: "top-[18%] left-[12%]" },
        { label: "SHA-256", className: "top-[26%] right-[10%]" },
        { label: "iOS backup", className: "bottom-[20%] left-[9%]" },
      ].map((b, i) => (
        <motion.div
          key={b.label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 + i * 0.15 }}
          className={clsx("absolute rounded-full border border-line bg-surface/90 px-3 py-1.5 text-[12px] font-semibold text-ink-2 shadow-[var(--shadow-card)] backdrop-blur", b.className)}
        >
          <ShieldCheck className="mr-1 inline size-3.5 text-emerald-500" />
          {b.label}
        </motion.div>
      ))}
    </div>
  );
}

export function ConnectView() {
  const { t } = useI18n();
  const { platform, setPlatform, scan, scanning, openDialog, detected, connect, info } = useStore();

  useEffect(() => {
    void scan({ silent: true });
    const id = window.setInterval(() => void scan({ silent: true }), 5000);
    return () => window.clearInterval(id);
  }, [scan]);

  const card = (p: "android" | "ios", icon: React.ReactNode, title: string, desc: string) => (
    <button
      onClick={() => setPlatform(p)}
      className={clsx(
        "focus-ring flex flex-1 items-center gap-3 rounded-2xl border-2 p-3.5 text-left transition",
        platform === p ? "border-navy-600 bg-navy-50/70 dark:border-gold-400 dark:bg-gold-400/10" : "border-line hover:border-line-strong hover:bg-surface-2",
      )}
    >
      <span className={clsx("grid size-11 place-items-center rounded-xl", platform === p ? "bg-navy-800 text-white dark:bg-gold-400 dark:text-navy-950" : "bg-surface-3 text-ink-2")}>
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-[15px] font-bold text-ink">{title}</span>
        <span className="block truncate text-[12px] text-muted">{desc}</span>
      </span>
      <span className={clsx("ml-auto size-4.5 shrink-0 rounded-full border-2", platform === p ? "border-[6px] border-navy-700 dark:border-gold-400" : "border-line-strong")} />
    </button>
  );

  return (
    <div className="card grid h-full grid-cols-[0.75fr_1fr] overflow-hidden 2xl:grid-cols-[1.05fr_1fr]" data-testid="connect-view">
      <Illustration />
      <div className="flex min-w-0 flex-col overflow-y-auto py-8 pr-10 pl-4 2xl:pr-14 2xl:pl-6">
        <div className="my-auto">
        <Badge tone="gold" className="mb-4 w-fit">
          <Usb className="size-3.5" /> USB
        </Badge>
        <h1 className="font-display text-[36px] leading-[1.1] font-bold tracking-tight text-ink 2xl:text-[44px]">{t("connect.title")}</h1>
        <p className="mt-3 text-[16px] text-muted">{t("connect.sub", { platform: platform === "ios" ? "iOS" : "Android" })}</p>

        <div className="mt-6 flex max-w-xl flex-col gap-3 xl:flex-row">
          {card("android", <AndroidIcon className="size-6" />, "Android", t("connect.androidDesc"))}
          {card("ios", <IphoneIcon className="size-6" />, "iPhone (iOS)", t("connect.iosDesc"))}
        </div>

        <div className="mt-7 flex items-center gap-4">
          <Button variant="gold" size="lg" className="h-14 px-9 text-[17px]" icon={<Search className="size-5" />} loading={scanning} onClick={() => void scan()} data-testid="scan-big">
            {scanning ? t("connect.scanning") : t("rb.scan")}
          </Button>
          <button onClick={() => openDialog("history")} className="flex items-center gap-1.5 text-[13.5px] font-semibold text-muted hover:text-ink">
            <History className="size-4" /> {t("connect.openCase")}
          </button>
          <button onClick={() => openDialog("messenger")} className="flex items-center gap-1.5 text-[13.5px] font-semibold text-muted hover:text-ink" data-testid="connect-messenger">
            <MessageCircle className="size-4" /> {t("ms.open")}
          </button>
        </div>

        <p className="mt-6 max-w-xl text-[14px] text-muted">{platform === "ios" ? t("connect.iosHint") : t("connect.androidHint")}</p>
        <button
          onClick={() => openDialog("diag", { platform, notFound: false })}
          className="mt-1.5 flex w-fit items-center gap-1.5 text-[14px] font-semibold text-navy-600 hover:underline dark:text-gold-300"
        >
          <CircleHelp className="size-4" />
          {platform === "ios" ? t("connect.howIos") : t("connect.howAndroid")}
        </button>

        {detected.length > 0 && (
          <div className="mt-7 max-w-xl">
            <div className="mb-2 text-[12.5px] font-semibold text-muted">{t("connect.detected")}</div>
            <div className="flex flex-col gap-2">
              {detected.map((d) => (
                <motion.div
                  key={d.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-3 rounded-2xl border border-line bg-surface-2 p-3"
                >
                  <span className="grid size-10 place-items-center rounded-xl bg-surface text-ink-2 shadow-sm">
                    {d.platform === "ios" ? <IphoneIcon className="size-5" /> : <AndroidIcon className="size-5 text-[#3DDC84]" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 truncate text-[14.5px] font-bold text-ink">
                      {d.brand && d.platform === "android" ? `${d.brand} ` : ""}
                      {d.model || d.serial}
                      {d.demo && (
                        <Badge tone="gold">
                          <Sparkles className="size-3" /> {t("conn.demo")}
                        </Badge>
                      )}
                    </div>
                    <div className="truncate text-[12px] text-muted">
                      {d.state === "ready" ? (
                        <span className="text-emerald-600 dark:text-emerald-400">● {t("state.ready")}</span>
                      ) : (
                        <span className="text-amber-600 dark:text-amber-400">● {t(`state.${d.state}`)}</span>
                      )}{" "}
                      · <span className="font-mono">{d.serial}</span>
                    </div>
                  </div>
                  <Button size="sm" variant={d.state === "ready" ? "primary" : "outline"} disabled={d.state !== "ready"} onClick={() => void connect(d.id)} data-testid={`connect-${d.id}`}>
                    {t("connect.connect")} <ChevronRight className="size-4" />
                  </Button>
                </motion.div>
              ))}
            </div>
          </div>
        )}
        {info?.demo && detected.length === 0 && <p className="mt-6 text-[12.5px] text-faint">{t("connect.demoHint")}</p>}
        </div>
      </div>
    </div>
  );
}
