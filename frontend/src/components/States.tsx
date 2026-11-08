import { Download, Inbox, Lock, SearchX } from "lucide-react";
import type { ReactNode } from "react";
import { useI18n } from "../lib/i18n";
import { useRecords, useStore } from "../lib/store";
import type { Kind } from "../lib/types";
import { TAB_ICONS } from "./TabBar";
import { Button } from "./ui";

function Shell({ icon, title, sub, action, tone = "navy" }: { icon: ReactNode; title: ReactNode; sub?: ReactNode; action?: ReactNode; tone?: "navy" | "amber" }) {
  return (
    <div className="flex h-full min-h-72 flex-col items-center justify-center px-6 py-10 text-center">
      <div className="relative mb-5">
        <div className={`absolute -inset-4 rounded-full ${tone === "amber" ? "bg-amber-400/15" : "bg-navy-400/10 dark:bg-gold-400/10"} blur-md`} />
        <div
          className={`relative grid size-16 place-items-center rounded-3xl ${
            tone === "amber" ? "bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300" : "bg-navy-50 text-navy-600 dark:bg-navy-800 dark:text-gold-300"
          } [&_svg]:size-7`}
        >
          {icon}
        </div>
      </div>
      <h3 className="font-display text-[19px] font-semibold text-ink">{title}</h3>
      {sub && <p className="mt-1.5 max-w-lg text-[14px] leading-relaxed text-muted">{sub}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function EmptySearch() {
  const { t } = useI18n();
  return <Shell icon={<SearchX />} title={t("empty.search")} />;
}

/** Data for one category, with consistent empty / unavailable / loading states.
 *  `action` adds a button to those states (e.g. importing Messenger on the chats tab). */
export function KindView<T>({ kind, children, action }: { kind: Kind; children: (rows: T[]) => ReactNode; action?: ReactNode }) {
  const { t } = useI18n();
  const { state, openDialog } = useStore();
  const rows = useRecords<T>(kind);
  const connected = !!state.device && !state.device.offline;
  if (!state.extraction) {
    return (
      <div className="card h-full">
        <Shell
          icon={TAB_ICONS[kind]}
          title={t("empty.noData")}
          sub={t("empty.noDataSub")}
          action={
            (connected || action) && (
              <div className="flex flex-wrap items-center justify-center gap-2">
                {connected && (
                  <Button variant="gold" icon={<Download className="size-4" />} onClick={() => openDialog("extract")}>
                    {t("rb.extract")}
                  </Button>
                )}
                {action}
              </div>
            )
          }
        />
      </div>
    );
  }
  const unavailable = state.extraction.unavailable?.[kind];
  if (rows && rows.length === 0 && unavailable) {
    return (
      <div className="card h-full">
        <Shell
          tone="amber"
          icon={<Lock />}
          title={t("unavail.title")}
          sub={
            <>
              {t(`reason.${unavailable.reason}`)}
              {unavailable.detail && <span className="mt-2 block font-mono text-[12px] text-faint">{unavailable.detail}</span>}
            </>
          }
          action={action}
        />
      </div>
    );
  }
  if (!rows) {
    return (
      <div className="card flex h-full flex-col gap-3 p-5">
        <div className="skeleton h-10 w-80 rounded-xl" />
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="skeleton h-11 rounded-xl" style={{ opacity: 1 - i * 0.1 }} />
        ))}
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div className="card h-full">
        <Shell icon={<Inbox />} title={t("empty.none")} action={action} />
      </div>
    );
  }
  return <>{children(rows)}</>;
}
