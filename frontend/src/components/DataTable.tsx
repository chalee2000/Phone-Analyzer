import { useVirtualizer } from "@tanstack/react-virtual";
import clsx from "clsx";
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { useI18n } from "../lib/i18n";
import { Input } from "./ui";

export interface Column<T> {
  key: string;
  header: ReactNode;
  width: string; // CSS grid track, e.g. "1.2fr" or "120px"
  render: (row: T, index: number) => ReactNode;
  sort?: (row: T) => string | number;
  align?: "left" | "right" | "center";
}

export function DataTable<T>({
  rows,
  columns,
  rowHeight = 52,
  onRowClick,
  initialSort,
  empty,
  testId,
}: {
  rows: T[];
  columns: Column<T>[];
  rowHeight?: number;
  onRowClick?: (row: T) => void;
  initialSort?: { key: string; dir: "asc" | "desc" };
  empty?: ReactNode;
  testId?: string;
}) {
  const [sort, setSort] = useState(initialSort);
  const parentRef = useRef<HTMLDivElement>(null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sort) return rows;
    const get = col.sort;
    const copy = [...rows];
    copy.sort((a, b) => {
      const va = get(a);
      const vb = get(b);
      const r = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb), "th");
      return sort.dir === "asc" ? r : -r;
    });
    return copy;
  }, [rows, columns, sort]);

  const virtualizer = useVirtualizer({ count: sorted.length, getScrollElement: () => parentRef.current, estimateSize: () => rowHeight, overscan: 12 });
  const template = columns.map((c) => c.width).join(" ");

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-line" data-testid={testId}>
      <div className="grid shrink-0 items-center gap-3 border-b border-line bg-surface-2 px-4 text-[12.5px] font-semibold text-muted" style={{ gridTemplateColumns: template, height: 42 }}>
        {columns.map((c) => (
          <button
            key={c.key}
            disabled={!c.sort}
            onClick={() => setSort((s) => (s?.key === c.key ? { key: c.key, dir: s.dir === "asc" ? "desc" : "asc" } : { key: c.key, dir: "asc" }))}
            className={clsx("group flex items-center gap-1 truncate disabled:cursor-default", c.align === "right" && "justify-end", c.align === "center" && "justify-center")}
          >
            {c.header}
            {c.sort &&
              (sort?.key === c.key ? (
                sort.dir === "asc" ? <ArrowUp className="size-3.5 text-navy-500 dark:text-gold-300" /> : <ArrowDown className="size-3.5 text-navy-500 dark:text-gold-300" />
              ) : (
                <ArrowUpDown className="size-3 opacity-0 transition group-hover:opacity-60" />
              ))}
          </button>
        ))}
      </div>
      <div ref={parentRef} className="min-h-0 flex-1 overflow-auto bg-surface">
        {sorted.length === 0 ? (
          empty
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map((v) => {
              const row = sorted[v.index];
              return (
                <div
                  key={v.key}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={clsx(
                    "absolute inset-x-0 grid items-center gap-3 border-b border-line/70 px-4 text-[13.5px] text-ink transition-colors hover:bg-row-hover",
                    v.index % 2 === 1 && "bg-surface-2/40",
                    onRowClick && "cursor-pointer",
                  )}
                  style={{ gridTemplateColumns: template, height: v.size, transform: `translateY(${v.start}px)` }}
                >
                  {columns.map((c) => (
                    <div key={c.key} className={clsx("min-w-0 truncate", c.align === "right" && "text-right", c.align === "center" && "text-center")}>
                      {c.render(row, v.index)}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export function SearchBox({ value, onChange, className }: { value: string; onChange: (v: string) => void; className?: string }) {
  const { t } = useI18n();
  return (
    <Input
      className={clsx("w-72", className)}
      icon={<Search className="size-4" />}
      placeholder={t("tb.search")}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      data-testid="search"
    />
  );
}

export function Toolbar({ children, shown, total }: { children?: ReactNode; shown?: number; total?: number }) {
  const { t } = useI18n();
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-2.5">
      {children}
      {shown != null && total != null && (
        <span className="tabular ml-auto text-[12.5px] text-muted">{t("tb.showing", { n: shown.toLocaleString(), total: total.toLocaleString() })}</span>
      )}
    </div>
  );
}
