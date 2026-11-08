import clsx from "clsx";
import { X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";

type Variant = "primary" | "gold" | "ghost" | "outline" | "danger" | "soft";

export function Button({
  variant = "outline",
  size = "md",
  icon,
  loading,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg"; icon?: ReactNode; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={clsx(
        "focus-ring inline-flex items-center justify-center gap-2 rounded-xl font-semibold whitespace-nowrap transition-all duration-150 select-none",
        "disabled:cursor-not-allowed disabled:opacity-50 active:translate-y-px",
        size === "sm" && "h-8 px-3 text-[13px]",
        size === "md" && "h-10 px-4 text-sm",
        size === "lg" && "h-12 px-6 text-[15px]",
        variant === "primary" &&
          "bg-gradient-to-b from-navy-600 to-navy-800 text-white shadow-[0_6px_16px_-6px_rgba(18,40,90,0.7)] hover:from-navy-500 hover:to-navy-700",
        variant === "gold" &&
          "bg-gradient-to-b from-gold-300 to-gold-500 text-navy-950 shadow-[0_8px_20px_-8px_rgba(220,162,42,0.9)] hover:from-gold-200 hover:to-gold-400",
        variant === "outline" && "border border-line-strong bg-surface text-ink hover:bg-surface-2",
        variant === "ghost" && "text-ink-2 hover:bg-surface-3",
        variant === "soft" && "bg-navy-50 text-navy-700 hover:bg-navy-100 dark:bg-navy-800/60 dark:text-navy-100 dark:hover:bg-navy-700/70",
        variant === "danger" && "bg-rose-600 text-white hover:bg-rose-500",
        className,
      )}
    >
      {loading ? <Spinner className="size-4" /> : icon}
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={clsx("animate-spin", className)} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Badge({ tone = "slate", children, className }: { tone?: string; children: ReactNode; className?: string }) {
  const tones: Record<string, string> = {
    slate: "bg-surface-3 text-ink-2",
    navy: "bg-navy-50 text-navy-700 dark:bg-navy-800/70 dark:text-navy-100",
    gold: "bg-gold-50 text-gold-700 ring-1 ring-gold-200 dark:bg-gold-500/15 dark:text-gold-300 dark:ring-gold-500/30",
    green: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
    red: "bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
    amber: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
    blue: "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
    violet: "bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  };
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-semibold whitespace-nowrap", tones[tone], className)}>
      {children}
    </span>
  );
}

export function Tooltip({ label, children, side = "bottom", className }: { label?: ReactNode; children: ReactNode; side?: "bottom" | "top"; className?: string }) {
  if (!label) return <>{children}</>;
  return (
    <span className={clsx("group/tt relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className={clsx(
          "pointer-events-none absolute left-1/2 z-50 w-max max-w-64 -translate-x-1/2 rounded-lg bg-navy-950/95 px-2.5 py-1.5 text-center text-[12px] leading-snug font-medium text-white opacity-0 shadow-lg transition-all delay-300 duration-150 group-hover/tt:opacity-100",
          side === "bottom" ? "top-full mt-2 translate-y-1 group-hover/tt:translate-y-0" : "bottom-full mb-2 -translate-y-1 group-hover/tt:translate-y-0",
        )}
      >
        {label}
      </span>
    </span>
  );
}

export function Modal({
  open,
  onClose,
  children,
  width = 720,
  className,
  dismissable = true,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  width?: number | string;
  className?: string;
  dismissable?: boolean;
}) {
  useEffect(() => {
    if (!open || !dismissable) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, dismissable]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-40 flex items-center justify-center p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div className="absolute inset-0 bg-navy-950/45 backdrop-blur-[3px]" onClick={dismissable ? onClose : undefined} />
          <motion.div
            role="dialog"
            aria-modal="true"
            className={clsx("relative flex max-h-full flex-col overflow-hidden rounded-[22px] border border-line bg-surface shadow-[var(--shadow-pop)]", className)}
            style={{ width, maxWidth: "100%" }}
            initial={{ opacity: 0, y: 18, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function ModalHeader({ icon, title, sub, onClose, tone = "navy" }: { icon?: ReactNode; title: ReactNode; sub?: ReactNode; onClose?: () => void; tone?: "navy" | "gold" }) {
  return (
    <div className="relative flex items-start gap-4 border-b border-line px-6 pt-5 pb-4">
      {icon && (
        <div
          className={clsx(
            "grid size-11 shrink-0 place-items-center rounded-2xl",
            tone === "navy" ? "bg-gradient-to-br from-navy-600 to-navy-900 text-white" : "bg-gradient-to-br from-gold-300 to-gold-500 text-navy-950",
          )}
        >
          {icon}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <h2 className="font-display text-[21px] leading-tight font-semibold text-ink">{title}</h2>
        {sub && <p className="mt-1 text-[13.5px] text-muted">{sub}</p>}
      </div>
      {onClose && (
        <button onClick={onClose} className="focus-ring -mt-1 -mr-2 grid size-9 place-items-center rounded-xl text-muted hover:bg-surface-3 hover:text-ink" aria-label="close">
          <X className="size-5" />
        </button>
      )}
      <span className="absolute bottom-[-1px] left-6 h-[3px] w-14 rounded-full bg-gold-400" />
    </div>
  );
}

export function Switch({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        "focus-ring relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-40",
        checked ? "bg-gradient-to-r from-navy-600 to-navy-500 dark:from-gold-500 dark:to-gold-400" : "bg-line-strong",
      )}
    >
      <span className={clsx("absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition-transform", checked && "translate-x-5")} />
    </button>
  );
}

export function Input({ className, icon, ...rest }: InputHTMLAttributes<HTMLInputElement> & { icon?: ReactNode }) {
  return (
    <label className={clsx("focus-within:ring-[3px] focus-within:ring-[var(--ring)] flex h-10 items-center gap-2 rounded-xl border border-line-strong bg-surface px-3 transition", className)}>
      {icon && <span className="text-faint">{icon}</span>}
      <input {...rest} className="h-full min-w-0 flex-1 bg-transparent text-[14px] text-ink outline-none placeholder:text-faint" />
    </label>
  );
}

export function Field({ label, hint, children }: { label: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[13px] font-semibold text-ink-2">{label}</span>
      {children}
      {hint && <span className="text-[12px] text-muted">{hint}</span>}
    </div>
  );
}

export function ProgressBar({ value, className, tone = "navy" }: { value: number; className?: string; tone?: "navy" | "gold" | "green" }) {
  return (
    <div className={clsx("h-1.5 overflow-hidden rounded-full bg-surface-3", className)}>
      <div
        className={clsx(
          "h-full rounded-full transition-[width] duration-300",
          tone === "navy" && "bg-gradient-to-r from-navy-500 to-navy-700 dark:from-navy-300 dark:to-navy-400",
          tone === "gold" && "bg-gradient-to-r from-gold-300 to-gold-500",
          tone === "green" && "bg-gradient-to-r from-emerald-400 to-emerald-600",
        )}
        style={{ width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` }}
      />
    </div>
  );
}

export function Chip({ active, onClick, children, count }: { active: boolean; onClick: () => void; children: ReactNode; count?: number }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "focus-ring inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-semibold transition",
        active
          ? "border-navy-700 bg-navy-800 text-white dark:border-gold-400 dark:bg-gold-400 dark:text-navy-950"
          : "border-line-strong bg-surface text-ink-2 hover:bg-surface-2",
      )}
    >
      {children}
      {count != null && <span className={clsx("tabular text-[11.5px]", active ? "opacity-80" : "text-faint")}>{count.toLocaleString()}</span>}
    </button>
  );
}
