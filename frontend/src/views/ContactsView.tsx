import { Star } from "lucide-react";
import { useMemo, useState } from "react";
import { DataTable, SearchBox, Toolbar, type Column } from "../components/DataTable";
import { EmptySearch, KindView } from "../components/States";
import { Badge } from "../components/ui";
import { matches } from "../lib/format";
import { useI18n } from "../lib/i18n";
import type { Contact } from "../lib/types";
import { Avatar } from "./CallsView";

function Contacts({ rows }: { rows: Contact[] }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const filtered = useMemo(() => rows.filter((r) => matches([r.name, ...r.phones, ...r.emails, r.organization, r.note], q)), [rows, q]);
  const columns: Column<Contact>[] = [
    {
      key: "name",
      header: t("col.name"),
      width: "1.5fr",
      render: (r) => (
        <span className="flex items-center gap-3">
          <Avatar name={r.name} size={34} />
          <span className="truncate font-semibold">{r.name}</span>
          {r.starred && <Star className="size-3.5 shrink-0 fill-gold-400 text-gold-400" />}
        </span>
      ),
      sort: (r) => r.name,
    },
    {
      key: "phones",
      header: t("col.phones"),
      width: "1.4fr",
      render: (r) => (
        <span className="flex gap-1.5">
          {r.phones.map((p) => (
            <span key={p} className="tabular rounded-md bg-surface-3 px-1.5 py-0.5 font-mono text-[12.5px]">
              {p}
            </span>
          ))}
        </span>
      ),
      sort: (r) => r.phones[0] ?? "",
    },
    { key: "email", header: t("col.email"), width: "1.2fr", render: (r) => <span className="text-ink-2">{r.emails.join(", ")}</span> },
    { key: "org", header: t("col.org"), width: "1fr", render: (r) => <span className="text-ink-2">{r.organization}</span>, sort: (r) => r.organization },
    { key: "acc", header: t("col.account"), width: "130px", render: (r) => r.account && <Badge tone="navy">{r.account}</Badge> },
  ];
  return (
    <div className="card flex h-full min-h-0 flex-col gap-3 p-5">
      <Toolbar shown={filtered.length} total={rows.length}>
        <SearchBox value={q} onChange={setQ} />
      </Toolbar>
      <DataTable rows={filtered} columns={columns} empty={<EmptySearch />} rowHeight={56} testId="contacts-table" />
    </div>
  );
}

export function ContactsView() {
  return <KindView<Contact> kind="contacts">{(rows) => <Contacts rows={rows} />}</KindView>;
}
