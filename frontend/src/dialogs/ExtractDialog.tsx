import clsx from "clsx";
import { Check, Download, FolderPlus, KeyRound, Lock, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { TAB_ICONS } from "../components/TabBar";
import { Badge, Button, Field, Input, Modal, ModalHeader, Switch } from "../components/ui";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { ALL_KINDS, type Kind } from "../lib/types";

const ANDROID_ROOT_ONLY: Kind[] = ["chats", "web"];
const ANDROID_NONE: Kind[] = ["notes"];

function readPref(key: string, fallback = "") {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

export function ExtractDialog() {
  const { t } = useI18n();
  const { dialogs, closeDialog, state, startExtraction, info, openDialog, deviceName } = useStore();
  const open = dialogs.extract;
  const ios = state.device?.info.platform === "ios";
  const isDemo = !!state.device?.demo;
  const encrypted = state.device?.info.extra?.backup_encrypted === "1";
  const disabledKinds = ios ? [] : [...ANDROID_ROOT_ONLY, ...ANDROID_NONE];
  const [kinds, setKinds] = useState<Kind[]>(ALL_KINDS);
  const [agent, setAgent] = useState(true);
  const [tempEnc, setTempEnc] = useState(true);
  const [password, setPassword] = useState("");
  const [maxPhotos, setMaxPhotos] = useState(0);
  const [examiner, setExaminer] = useState(() => readPref("spni.examiner"));

  useEffect(() => {
    if (open) setKinds(ALL_KINDS.filter((k) => !disabledKinds.includes(k)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, ios]);

  const toggle = (k: Kind) => setKinds((ks) => (ks.includes(k) ? ks.filter((x) => x !== k) : [...ks, k]));
  const start = async () => {
    try {
      localStorage.setItem("spni.examiner", examiner);
    } catch {
      /* ignore */
    }
    closeDialog("extract");
    await startExtraction({
      kinds,
      examiner,
      max_photos: maxPhotos,
      android_allow_agent: agent,
      ios_allow_temp_encryption: tempEnc,
      ios_backup_password: password,
    });
  };

  return (
    <Modal open={open} onClose={() => closeDialog("extract")} width={820}>
      <ModalHeader icon={<Download className="size-5" />} tone="gold" title={t("ex.title", { device: deviceName })} sub={t("ex.sub")} onClose={() => closeDialog("extract")} />
      <div className="min-h-0 overflow-auto px-6 py-5">
        <div className="mb-2.5 flex items-center justify-between">
          <span className="text-[13px] font-semibold text-ink-2">{t("ex.kinds")}</span>
          <button className="text-[12.5px] font-semibold text-navy-600 hover:underline dark:text-gold-300" onClick={() => setKinds(ALL_KINDS.filter((k) => !disabledKinds.includes(k)))}>
            {t("ex.selectAll")}
          </button>
        </div>
        <div className="grid grid-cols-3 gap-2.5 lg:grid-cols-4">
          {ALL_KINDS.map((k) => {
            const off = disabledKinds.includes(k);
            const on = kinds.includes(k) && !off;
            return (
              <button
                key={k}
                disabled={off}
                onClick={() => toggle(k)}
                className={clsx(
                  "focus-ring relative flex items-center gap-2.5 rounded-2xl border-2 px-3 py-2.5 text-left transition",
                  on ? "border-navy-600 bg-navy-50/60 dark:border-gold-400 dark:bg-gold-400/10" : "border-line hover:bg-surface-2",
                  off && "cursor-not-allowed opacity-50",
                )}
              >
                <span className={clsx("grid size-8 place-items-center rounded-lg", on ? "bg-navy-700 text-white dark:bg-gold-400 dark:text-navy-950" : "bg-surface-3 text-muted")}>{TAB_ICONS[k]}</span>
                <span className="min-w-0">
                  <span className="block truncate text-[13.5px] font-semibold text-ink">{t(`tab.${k}`)}</span>
                  {off && <span className="block text-[11px] text-muted">{ANDROID_NONE.includes(k) ? t("ex.notAndroid") : t("ex.rootOnly")}</span>}
                </span>
                {on && <Check className="absolute top-2 right-2 size-4 text-navy-600 dark:text-gold-300" />}
              </button>
            );
          })}
        </div>

        <div className="mt-6 mb-2.5 text-[13px] font-semibold text-ink-2">{t("ex.options")}</div>
        <div className="flex flex-col gap-2.5">
          {!ios && (
            <div className="flex gap-4 rounded-2xl border border-line bg-surface-2 p-4">
              <ShieldCheck className="mt-0.5 size-5 shrink-0 text-emerald-500" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-[14px] font-semibold text-ink">
                  {t("ex.agent")} <Badge tone="blue">Android 10+</Badge>
                </div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-muted">{t("ex.agentDesc")}</p>
                {info && !info.agent_available && !isDemo && <p className="mt-1 text-[12px] font-semibold text-amber-600">{t("ex.agentMissing")}</p>}
              </div>
              <Switch checked={agent} onChange={setAgent} />
            </div>
          )}
          {ios && !encrypted && (
            <div className="flex gap-4 rounded-2xl border border-line bg-surface-2 p-4">
              <Lock className="mt-0.5 size-5 shrink-0 text-navy-500 dark:text-gold-300" />
              <div className="min-w-0 flex-1">
                <div className="text-[14px] font-semibold text-ink">{t("ex.tempEnc")}</div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-muted">{t("ex.tempEncDesc")}</p>
              </div>
              <Switch checked={tempEnc} onChange={setTempEnc} />
            </div>
          )}
          {ios && encrypted && (
            <div className="rounded-2xl border border-gold-200 bg-gold-50/60 p-4 dark:border-gold-500/30 dark:bg-gold-500/10">
              <Field label={t("ex.password")} hint={t("ex.passwordDesc")}>
                <Input type="password" icon={<KeyRound className="size-4" />} value={password} onChange={(e) => setPassword(e.target.value)} />
              </Field>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("ex.examiner")}>
              <Input value={examiner} onChange={(e) => setExaminer(e.target.value)} placeholder="ร.ต.อ. …" />
            </Field>
            <Field label={t("ex.photos")}>
              <div className="flex h-10 gap-1 rounded-xl bg-surface-3 p-1">
                {[0, 500, 100].map((n) => (
                  <button
                    key={n}
                    onClick={() => setMaxPhotos(n)}
                    className={clsx("flex-1 rounded-lg text-[13px] font-semibold transition", maxPhotos === n ? "bg-surface text-ink shadow" : "text-muted hover:text-ink")}
                  >
                    {n === 0 ? t("ex.photosAll") : t("ex.photosLatest", { n })}
                  </button>
                ))}
              </div>
            </Field>
          </div>
          <div className="flex items-center gap-3 rounded-2xl border border-dashed border-line-strong px-4 py-3 text-[13px]">
            <span className="text-muted">{t("ex.case")}:</span>
            {state.case ? (
              <span className="font-semibold text-ink">{state.case.case_no || state.case.title}</span>
            ) : (
              <>
                <span className="text-muted">{t("ex.autoCase")}</span>
                <Button size="sm" variant="soft" className="ml-auto" icon={<FolderPlus className="size-4" />} onClick={() => openDialog("cases")}>
                  {t("ex.createCase")}
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center justify-end gap-2 border-t border-line bg-surface-2 px-6 py-4">
        <Button variant="ghost" onClick={() => closeDialog("extract")}>
          {t("common.cancel")}
        </Button>
        <Button variant="gold" size="lg" icon={<Download className="size-5" />} disabled={!kinds.length} onClick={() => void start()} data-testid="start-extraction">
          {t("ex.start")}
        </Button>
      </div>
    </Modal>
  );
}
