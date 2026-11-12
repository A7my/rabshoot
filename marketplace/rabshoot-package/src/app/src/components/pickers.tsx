import { useQuery } from "@tanstack/react-query";
import { Hash, Lock, Mail, MessageCircle, Search, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import type { ConversationRef, SlackConversation, ThreadRef } from "../lib/types";
import { cn, formatDateTime, relativeTime } from "../lib/utils";
import { Alert, Badge, Button, Checkbox, Input, Spinner } from "./ui";

function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const { t } = useTranslation();
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute start-3 top-3 h-4 w-4 text-muted" />
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder || t("common.search")} className="ps-9" />
    </div>
  );
}

/* --------------------------------------------------------------- projects */

export function ProjectPicker({ connectionId, value, onChange }: {
  connectionId: string; value: "all" | string[]; onChange: (v: "all" | string[]) => void;
}) {
  const { t, i18n } = useTranslation();
  const [filter, setFilter] = useState("");
  const choosing = value !== "all";
  const { data, isLoading, error } = useQuery({
    queryKey: ["projects", connectionId], queryFn: () => api.codeProjects(connectionId), enabled: choosing, staleTime: 300_000,
  });
  const selected = new Set(choosing ? value : []);
  const shown = (data ?? []).filter((p) => p.name.toLowerCase().includes(filter.toLowerCase()));
  const toggle = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    onChange([...next]);
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2">
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input type="radio" checked={!choosing} onChange={() => onChange("all")} className="accent-primary" />
          {t("code.allActive")}
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input type="radio" checked={choosing} onChange={() => onChange([])} className="accent-primary" />
          {t("code.choose")}
          {choosing && <Badge tone="primary">{t("code.selectedCount", { count: selected.size })}</Badge>}
        </label>
      </div>
      {choosing && (
        <div className="rounded-lg border border-line bg-bg p-3">
          <SearchInput value={filter} onChange={setFilter} />
          <div className="mt-3 max-h-64 space-y-1 overflow-y-auto pe-1">
            {isLoading && <Spinner label={t("common.loading")} />}
            {error && <Alert kind="error">{(error as Error).message}</Alert>}
            {data && shown.length === 0 && <p className="text-sm text-muted">{t("code.noProjects")}</p>}
            {shown.map((p) => (
              <div key={p.id} className="rounded-md px-2 py-1.5 hover:bg-surface2">
                <Checkbox checked={selected.has(p.id)} onChange={() => toggle(p.id)}>
                  <span className="flex items-center justify-between gap-3">
                    <span className="ltr truncate">{p.name}</span>
                    <span className="shrink-0 text-xs text-muted">{relativeTime(p.last_activity_at, i18n.language)}</span>
                  </span>
                </Checkbox>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------- conversations */

const KIND_ICON = { channel: Hash, private: Lock, group: Users, dm: MessageCircle };

export function ConversationPicker({ connectionId, value, onChange }: {
  connectionId: string; value: ConversationRef[]; onChange: (v: ConversationRef[]) => void;
}) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["slackConversations", connectionId], queryFn: () => api.slackConversations(connectionId), staleTime: 300_000,
  });
  const selected = new Set(value.map((v) => v.id));
  const groups = useMemo(() => {
    const out: Record<SlackConversation["kind"], SlackConversation[]> = { channel: [], private: [], group: [], dm: [] };
    for (const c of data ?? []) if (c.name.toLowerCase().includes(filter.toLowerCase())) out[c.kind].push(c);
    return out;
  }, [data, filter]);
  const toggle = (c: SlackConversation) => {
    onChange(selected.has(c.id) ? value.filter((v) => v.id !== c.id) : [...value, { id: c.id, name: c.name }]);
  };
  const visible = Object.values(groups).flat();
  const allSelected = (items: SlackConversation[]) => items.length > 0 && items.every((c) => selected.has(c.id));
  const setMany = (items: SlackConversation[], on: boolean) => {
    const ids = new Set(items.map((c) => c.id));
    const rest = value.filter((v) => !ids.has(v.id));
    onChange(on ? [...rest, ...items.map((c) => ({ id: c.id, name: c.name }))] : rest);
  };
  const selectAll = (items: SlackConversation[]) => (
    <button type="button" className="text-xs font-medium text-primary hover:underline"
      onClick={() => setMany(items, !allSelected(items))}>
      {allSelected(items) ? t("slack.clearAll") : t("slack.selectAll")}
    </button>
  );
  return (
    <div className="rounded-lg border border-line bg-bg p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex-1"><SearchInput value={filter} onChange={setFilter} /></div>
        <Badge tone="primary">{t("slack.selectedCount", { count: value.length })}</Badge>
        {visible.length > 0 && selectAll(visible)}
      </div>
      {isLoading && <Spinner label={t("common.loading")} />}
      {error && <Alert kind="error">{(error as Error).message}</Alert>}
      {data && data.length === 0 && <p className="text-sm text-muted">{t("slack.noConversations")}</p>}
      <div className="max-h-80 space-y-4 overflow-y-auto pe-1">
        {(Object.keys(groups) as SlackConversation["kind"][]).map((kind) => groups[kind].length > 0 && (
          <div key={kind}>
            <div className="mb-1 flex items-center justify-between gap-2 pe-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                {t(`slack.kinds.${kind}`)} <span className="font-normal normal-case">({groups[kind].length})</span>
              </span>
              {selectAll(groups[kind])}
            </div>
            {groups[kind].map((c) => {
              const Icon = KIND_ICON[c.kind];
              return (
                <div key={c.id} className="rounded-md px-2 py-1.5 hover:bg-surface2">
                  <Checkbox checked={selected.has(c.id)} onChange={() => toggle(c)}>
                    <span className="flex items-center gap-2">
                      <Icon className="h-3.5 w-3.5 shrink-0 text-muted" />
                      <span className="truncate" dir="auto">{c.name.replace(/^#/, "")}</span>
                    </span>
                  </Checkbox>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- threads */

export function ThreadPicker({ connectionId, value, onChange }: {
  connectionId: string; value: ThreadRef | null; onChange: (v: ThreadRef) => void;
}) {
  const { t, i18n } = useTranslation();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const id = setTimeout(() => setDebounced(query), 450); return () => clearTimeout(id); }, [query]);
  const { data, isFetching, error, refetch } = useQuery({
    queryKey: ["threads", connectionId, debounced], queryFn: () => api.emailThreads(connectionId, debounced), staleTime: 120_000, retry: false,
  });
  return (
    <div className="space-y-3">
      {value && (value.subject || value.message_id) && (
        <div className="rounded-lg border border-primary/50 bg-primary/10 p-3">
          <div className="text-xs text-muted">{t("delivery.selected")}</div>
          <div className="mt-0.5 font-medium" dir="auto">{value.subject || value.message_id}</div>
          {value.participants?.length > 0 && (
            <div className="mt-2 text-xs text-muted">
              {t("delivery.willReceive")}: <span className="ltr text-ink/90">{value.participants.join(", ")}</span>
            </div>
          )}
        </div>
      )}
      <SearchInput value={query} onChange={setQuery} placeholder={t("delivery.searchThreads")} />
      <div className="max-h-80 space-y-1.5 overflow-y-auto pe-1">
        {isFetching && <Spinner label={t("common.loading")} />}
        {error && (
          <Alert kind="error">
            {(error as Error).message}
            <div className="mt-2"><Button size="sm" onClick={() => refetch()}>{t("common.retry")}</Button></div>
          </Alert>
        )}
        {!isFetching && data && data.length === 0 && <p className="text-sm text-muted">{t("delivery.noThreads")}</p>}
        {!isFetching && data?.map((th) => {
          const active = value && ((th.gm_thrid && th.gm_thrid === value.gm_thrid) || th.message_id === value.message_id);
          return (
            <button key={th.key} type="button"
              onClick={() => onChange({ subject: th.subject, message_id: th.message_id, gm_thrid: th.gm_thrid, participants: th.participants })}
              className={cn("block w-full rounded-lg border p-3 text-start transition-colors",
                active ? "border-primary bg-primary/10" : "border-line bg-surface2 hover:border-primary/50")}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <Mail className="h-4 w-4 shrink-0 text-muted" />
                  <span className="truncate text-sm font-medium" dir="auto">{th.subject}</span>
                </div>
                <span className="shrink-0 text-xs text-muted">{formatDateTime(th.last_date, i18n.language)}</span>
              </div>
              <div className="ltr mt-1 truncate ps-6 text-start text-xs text-muted">
                {th.participants.length ? <>{th.participants.slice(0, 5).join(", ")}{th.participants.length > 5 ? " …" : ""}</>
                  : <span className="text-warn">{t("delivery.onlyYou")}</span>}
              </div>
              <div className="mt-1 ps-6 text-xs text-muted">{t("delivery.messages", { count: th.count })}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
