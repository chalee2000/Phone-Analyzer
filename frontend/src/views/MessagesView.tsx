import { useVirtualizer } from "@tanstack/react-virtual";
import clsx from "clsx";
import { Lock, MessageSquareText, Paperclip } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { SearchBox } from "../components/DataTable";
import { EmptySearch, KindView } from "../components/States";
import { Badge, Button, Chip } from "../components/ui";
import { MessengerMark } from "../dialogs/MessengerImportDialog";
import { fmtDate, fmtDayHeader, fmtTime, matches } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { useStore } from "../lib/store";
import type { ChatMessage, SmsMessage } from "../lib/types";
import { Avatar } from "./CallsView";
import { useMediaUrl } from "./MiscViews";
import { MediaImage } from "./PhotosView";

interface Msg {
  key: string;
  thread: string;
  title: string;
  subtitle: string;
  app?: string;
  sender?: string;
  body: string;
  out: boolean;
  ts: number;
  service?: string;
  attachment?: string;
  unread?: boolean;
  encrypted?: boolean;
}

interface Thread {
  key: string;
  title: string;
  subtitle: string;
  app?: string;
  messages: Msg[];
  last: Msg;
  group: boolean;
  encrypted: boolean;
}

const APP_TONE: Record<string, string> = { LINE: "green", WhatsApp: "blue", Messenger: "violet" };
const IMAGE_RE = /\.(jpe?g|png|gif|webp|bmp)$/i;
const VIDEO_RE = /\.(mp4|mov|m4v|webm)$/i;
const AUDIO_RE = /\.(m4a|aac|mp3|wav|ogg|opus)$/i;

function buildThreads(msgs: Msg[]): Thread[] {
  const map = new Map<string, Thread>();
  for (const m of msgs) {
    let th = map.get(m.thread);
    if (!th) {
      th = { key: m.thread, title: m.title, subtitle: m.subtitle, app: m.app, messages: [], last: m, group: false, encrypted: false };
      map.set(m.thread, th);
    }
    th.messages.push(m);
    if (m.encrypted) th.encrypted = true;
    if (m.ts > th.last.ts) th.last = m;
  }
  for (const th of map.values()) {
    th.messages.sort((a, b) => a.ts - b.ts);
    const senders = new Set(th.messages.filter((m) => !m.out).map((m) => m.sender));
    th.group = senders.size > 1;
  }
  return [...map.values()].sort((a, b) => b.last.ts - a.last.ts);
}

function ThreadList({ threads, active, onPick }: { threads: Thread[]; active?: string; onPick: (k: string) => void }) {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({ count: threads.length, getScrollElement: () => ref.current, estimateSize: () => 74, overscan: 8 });
  return (
    <div ref={ref} className="min-h-0 flex-1 overflow-auto" data-testid="thread-list">
      {threads.length === 0 ? (
        <EmptySearch />
      ) : (
        <div style={{ height: v.getTotalSize(), position: "relative" }}>
          {v.getVirtualItems().map((it) => {
            const th = threads[it.index];
            const sel = th.key === active;
            return (
              <button
                key={th.key}
                onClick={() => onPick(th.key)}
                className={clsx(
                  "absolute inset-x-2 flex items-center gap-3 rounded-2xl px-3 text-left transition-colors",
                  sel ? "bg-navy-50 ring-1 ring-navy-100 dark:bg-navy-800/70 dark:ring-navy-700" : "hover:bg-surface-2",
                )}
                style={{ height: it.size - 4, transform: `translateY(${it.start + 2}px)` }}
              >
                <Avatar name={th.title} size={42} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-[14px] font-semibold text-ink">{th.title}</span>
                    {th.app && <Badge tone={APP_TONE[th.app] ?? "slate"}>{th.app}</Badge>}
                    {th.encrypted && <Lock className="size-3.5 shrink-0 text-violet-500" aria-label="E2EE" />}
                    <span className="tabular ml-auto shrink-0 text-[11.5px] text-faint">{fmtDate(th.last.ts)}</span>
                  </span>
                  <span className="mt-0.5 flex items-center gap-2">
                    <span className="truncate text-[12.5px] text-muted">
                      {th.last.out && <span className="text-faint">{t("msg.me")}: </span>}
                      {th.last.body}
                    </span>
                    <span className="tabular ml-auto shrink-0 rounded-full bg-surface-3 px-1.5 text-[11px] font-semibold text-muted">{th.messages.length}</span>
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** A file from the extraction shown inline: photo, video or voice clip; otherwise a paperclip line. */
function Attachment({ rel, out, small }: { rel: string; out: boolean; small?: boolean }) {
  const media = useMediaUrl();
  const src = rel.includes("/") ? media(rel) : "";
  const name = rel.split("/").pop() ?? rel;
  if (src && IMAGE_RE.test(rel))
    return (
      <a href={src} target="_blank" rel="noreferrer" className="mb-1.5 block">
        <MediaImage rel={rel} alt={name} lazy className={clsx("max-w-full rounded-xl object-cover", small ? "max-h-28" : "max-h-64")} />
      </a>
    );
  if (src && VIDEO_RE.test(rel)) return <video src={src} controls preload="metadata" className="mb-1.5 max-h-64 max-w-full rounded-xl" />;
  if (src && AUDIO_RE.test(rel)) return <audio src={src} controls preload="none" className="mb-1.5 max-w-full" />;
  return (
    <span className={clsx("mb-1 flex items-center gap-1 text-[12px]", out ? "text-white/70" : "text-muted")}>
      <Paperclip className="size-3.5" /> {name}
    </span>
  );
}

function Conversation({ thread }: { thread: Thread }) {
  const { t, lang } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [thread.key]);
  let lastDay = "";
  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <div className="flex items-center gap-3 border-b border-line px-6 py-3.5">
        <Avatar name={thread.title} size={42} />
        <div className="min-w-0">
          <div className="flex items-center gap-2 truncate font-display text-[17px] font-semibold text-ink">
            {thread.title}
            {thread.app && <Badge tone={APP_TONE[thread.app] ?? "slate"}>{thread.app}</Badge>}
            {thread.encrypted && (
              <Badge tone="violet">
                <Lock className="size-3" /> {t("msg.e2ee")}
              </Badge>
            )}
          </div>
          <div className="tabular truncate font-mono text-[12px] text-muted" data-selectable>
            {thread.subtitle}
          </div>
        </div>
        <span className="ml-auto text-[12.5px] text-muted">{t("msg.messages", { n: thread.messages.length.toLocaleString() })}</span>
      </div>
      <div
        ref={ref}
        className="min-h-0 flex-1 overflow-auto bg-[radial-gradient(circle_at_1px_1px,var(--border)_1px,transparent_0)] [background-size:22px_22px] px-6 py-4"
        data-selectable
        data-testid="conversation"
      >
        {thread.messages.map((m) => {
          const day = fmtDate(m.ts);
          const sep = day !== lastDay;
          lastDay = day;
          return (
            <div key={m.key}>
              {sep && (
                <div className="my-4 flex justify-center">
                  <span className="rounded-full border border-line bg-surface px-3 py-1 text-[11.5px] font-semibold text-muted shadow-sm">{fmtDayHeader(m.ts, lang)}</span>
                </div>
              )}
              <div className={clsx("mb-2 flex", m.out ? "justify-end" : "justify-start")}>
                <div className={clsx("max-w-[68%]", m.out && "items-end")}>
                  {thread.group && !m.out && m.sender && <div className="mb-0.5 ml-3 text-[11.5px] font-semibold text-navy-500 dark:text-gold-300">{m.sender}</div>}
                  <div
                    className={clsx(
                      "rounded-[20px] px-4 py-2.5 text-[14px] leading-relaxed break-words whitespace-pre-wrap shadow-sm",
                      m.out
                        ? "rounded-br-md bg-gradient-to-br from-navy-600 to-navy-800 text-white"
                        : "rounded-bl-md border border-[var(--bubble-in-border)] bg-[var(--bubble-in)] text-ink",
                    )}
                  >
                    {m.attachment && <Attachment rel={m.attachment} out={m.out} small={m.body.startsWith("[สติกเกอร์]")} />}
                    {!(m.attachment?.includes("/") && /^\[[^\]]+\]$/.test(m.body)) && m.body}
                  </div>
                  <div className={clsx("mt-1 flex items-center gap-1.5 px-2 text-[11px] text-faint", m.out && "justify-end")}>
                    <span className="tabular">{fmtTime(m.ts)}</span>
                    {m.service && m.service !== "SMS" && <span className="font-semibold text-sky-500">{m.service}</span>}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Messages({ msgs, total, toolbar }: { msgs: Msg[]; total: number; toolbar?: ReactNode }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [app, setApp] = useState<string | null>(null);
  const threads = useMemo(() => buildThreads(msgs), [msgs]);
  const apps = useMemo(() => {
    const c = new Map<string, number>();
    threads.forEach((th) => th.app && c.set(th.app, (c.get(th.app) ?? 0) + 1));
    return [...c.entries()].sort((a, b) => b[1] - a[1]);
  }, [threads]);
  const shown = useMemo(
    () =>
      threads.filter(
        (th) => (!app || th.app === app) && (!q || matches([th.title, th.subtitle], q) || th.messages.some((m) => matches([m.body, m.sender], q))),
      ),
    [threads, q, app],
  );
  const [active, setActive] = useState<string | undefined>(threads[0]?.key);
  useEffect(() => {
    if (!active && threads[0]) setActive(threads[0].key);
  }, [threads, active]);
  const current = threads.find((th) => th.key === active);
  return (
    <div className="card flex h-full min-h-0 overflow-hidden">
      <div className="flex w-[350px] shrink-0 flex-col border-r border-line">
        <div className="flex flex-col gap-2 p-4 pb-2">
          <div className="flex items-baseline justify-between">
            <h3 className="font-display text-[17px] font-semibold text-ink">{t("msg.threads")}</h3>
            <span className="tabular text-[12px] text-muted">
              {shown.length.toLocaleString()} · {total.toLocaleString()} {t("stat.sms")}
            </span>
          </div>
          {toolbar}
          <SearchBox value={q} onChange={setQ} className="w-full" />
          {apps.length > 1 && (
            <div className="flex flex-wrap gap-1.5" data-testid="chat-apps">
              <Chip active={!app} onClick={() => setApp(null)} count={threads.length}>
                {t("msg.allApps")}
              </Chip>
              {apps.map(([a, n]) => (
                <Chip key={a} active={app === a} onClick={() => setApp(a)} count={n}>
                  {a}
                </Chip>
              ))}
            </div>
          )}
        </div>
        <ThreadList threads={shown} active={active} onPick={setActive} />
      </div>
      {current ? (
        <Conversation thread={current} />
      ) : (
        <div className="grid flex-1 place-items-center text-muted">
          <span className="flex flex-col items-center gap-2">
            <MessageSquareText className="size-8 text-faint" />
            {t("msg.select")}
          </span>
        </div>
      )}
    </div>
  );
}

export function SmsView() {
  return (
    <KindView<SmsMessage> kind="sms">
      {(rows) => (
        <Messages
          total={rows.length}
          msgs={rows.map((r, i) => ({
            key: String(i),
            thread: r.thread || r.address,
            title: r.contact_name || r.address,
            subtitle: r.address,
            body: r.body,
            out: r.direction === "out",
            ts: r.timestamp ?? 0,
            service: r.service,
            attachment: r.attachments?.join(", "),
          }))}
        />
      )}
    </KindView>
  );
}

function MessengerButton({ compact }: { compact?: boolean }) {
  const { t } = useI18n();
  const { openDialog } = useStore();
  if (compact)
    return (
      <button
        onClick={() => openDialog("messenger")}
        data-testid="chats-messenger"
        className="focus-ring flex h-9 items-center gap-2 rounded-xl border border-line-strong bg-surface px-2.5 text-left text-[13px] font-semibold text-ink-2 transition hover:bg-surface-2"
      >
        <MessengerMark className="size-6 rounded-lg shadow-none" icon="size-3.5" />
        {t("ms.open")}
      </button>
    );
  return (
    <Button variant="outline" icon={<MessengerMark className="size-5 rounded-md shadow-none" icon="size-3" />} onClick={() => openDialog("messenger")} data-testid="chats-messenger">
      {t("ms.open")}
    </Button>
  );
}

export function ChatsView() {
  return (
    <KindView<ChatMessage> kind="chats" action={<MessengerButton />}>
      {(rows) => (
        <Messages
          toolbar={<MessengerButton compact />}
          total={rows.length}
          msgs={rows.map((r, i) => ({
            key: String(i),
            thread: `${r.app}:${r.thread}`,
            title: r.thread,
            subtitle: r.app,
            app: r.app,
            sender: r.sender,
            body: r.body,
            out: r.direction === "out",
            ts: r.timestamp ?? 0,
            // Real files (a path inside the extraction) are shown inline; bare names only beside text.
            attachment: r.attachment && (r.attachment.includes("/") || !r.body.startsWith("[")) ? r.attachment : undefined,
            encrypted: r.encrypted,
          }))}
        />
      )}
    </KindView>
  );
}
