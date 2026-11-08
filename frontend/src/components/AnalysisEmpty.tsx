import { FolderOpen, History } from "lucide-react";
import type { ReactNode } from "react";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import { Button } from "./ui";

export function AnalysisEmpty({ icon }: { icon: ReactNode }) {
  const { t } = useI18n();
  const { openDialog } = useStore();
  return (
    <div className="card flex h-full flex-col items-center justify-center p-10 text-center">
      <div className="relative mb-5">
        <div className="absolute -inset-5 rounded-full bg-gold-400/15 blur-md" />
        <div className="relative grid size-16 place-items-center rounded-3xl bg-navy-50 text-navy-600 dark:bg-navy-800 dark:text-gold-300 [&_svg]:size-7">{icon}</div>
      </div>
      <h3 className="font-display text-[20px] font-semibold text-ink">{t("an.noCase")}</h3>
      <p className="mt-1.5 max-w-lg text-[14px] text-muted">{t("an.noCaseSub")}</p>
      <div className="mt-5 flex gap-2">
        <Button variant="primary" icon={<FolderOpen className="size-4" />} onClick={() => openDialog("cases")}>
          {t("rb.cases")}
        </Button>
        <Button variant="outline" icon={<History className="size-4" />} onClick={() => openDialog("history")}>
          {t("rb.history")}
        </Button>
      </div>
    </div>
  );
}

export function Panel({ title, children, right, className = "" }: { title: ReactNode; children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <section className={`flex min-h-0 flex-col ${className}`}>
      <div className="flex items-center gap-2 px-4 pt-3.5 pb-2">
        <span className="h-3 w-1 rounded-full bg-gold-400" />
        <h4 className="text-[12.5px] font-bold tracking-wide text-ink-2">{title}</h4>
        <span className="ml-auto">{right}</span>
      </div>
      {children}
    </section>
  );
}
