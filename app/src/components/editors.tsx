import { useQuery } from "@tanstack/react-query";
import { CalendarClock, MessagesSquare, Plus, Repeat, Send, Trash2, Users } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import type { CodeSource, Profile, ScheduleMode } from "../lib/types";
import { cn, compactDays, DAY_PRESETS, DAYS, dayIn, expandDays, msUntil, timezones } from "../lib/utils";
import { CodeConnect, ConnectionPicker, ConnectionRow, SlackConnect, useConnections } from "./connect";
import { ConversationPicker, ProjectPicker, ThreadPicker } from "./pickers";
import { Alert, Button, Checkbox, EmailChips, Input, Label, Select, Switch, Textarea } from "./ui";

export type Update = (patch: Partial<Profile>) => void;

/* --------------------------------------------------------------- delivery */

export function DeliveryEditor({ profile, update }: { profile: Profile; update: Update }) {
  const { t } = useTranslation();
  const d = profile.delivery;
  const { data: connections } = useConnections();
  const sender = connections?.find((c) => c.id === profile.sender_connection_id);
  const imapOk = sender?.meta.imap_ok !== false;
  const { data: contacts } = useQuery({
    queryKey: ["contacts", sender?.id], queryFn: () => api.emailContacts(sender!.id), enabled: !!sender && imapOk,
    staleTime: 600_000, retry: false,
  });
  const suggestions = (contacts ?? []).map((c) => c.email);
  const set = (patch: Partial<Profile["delivery"]>) => update({ delivery: { ...d, ...patch } });

  const modes = [
    { key: "recipients" as const, icon: Users, title: t("delivery.modeRecipients"), hint: t("delivery.modeRecipientsHint") },
    { key: "thread" as const, icon: MessagesSquare, title: t("delivery.modeThread"), hint: t("delivery.modeThreadHint") },
  ];

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2">
        {modes.map((m) => (
          <button key={m.key} type="button" onClick={() => set({ mode: m.key })}
            className={cn("rounded-xl border p-4 text-start transition-all",
              d.mode === m.key ? "border-primary bg-primary/10 shadow-glow" : "border-line bg-surface2 hover:border-primary/50")}>
            <m.icon className="h-5 w-5 text-primary" />
            <div className="mt-2 font-semibold">{m.title}</div>
            <div className="text-xs text-muted">{m.hint}</div>
          </button>
        ))}
      </div>

      {d.mode === "recipients" && (
        <div className="space-y-4">
          <div><Label required>{t("delivery.to")}</Label>
            <EmailChips value={d.to} onChange={(to) => set({ to })} placeholder={t("delivery.addEmail")} suggestions={suggestions} /></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div><Label>{t("delivery.cc")}</Label>
              <EmailChips value={d.cc} onChange={(cc) => set({ cc })} placeholder={t("delivery.addEmail")} suggestions={suggestions} /></div>
            <div><Label>{t("delivery.bcc")}</Label>
              <EmailChips value={d.bcc} onChange={(bcc) => set({ bcc })} placeholder={t("delivery.addEmail")} suggestions={suggestions} /></div>
          </div>
          {suggestions.length > 0 && (
            <div>
              <div className="mb-2 text-xs text-muted">{t("delivery.suggestions")}</div>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.filter((s) => !d.to.includes(s) && !d.cc.includes(s)).slice(0, 8).map((s) => (
                  <button key={s} type="button" onClick={() => set({ to: [...d.to, s] })}
                    className="ltr inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-muted hover:border-primary/60 hover:text-ink">
                    <Plus className="h-3 w-3" />{s}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div><Label hint={t("delivery.subjectHint")}>{t("delivery.subject")}</Label>
            <Input className="ltr" value={d.subject} onChange={(e) => set({ subject: e.target.value })} /></div>
        </div>
      )}

      {d.mode === "thread" && (
        sender && !imapOk ? <Alert kind="warn">{t("delivery.threadNeedsImap")}</Alert>
          : sender ? (
            <div className="space-y-4">
              <ThreadPicker connectionId={sender.id} value={d.thread}
                onChange={(thread) => set({ thread })} />
              {d.thread && !d.thread.participants?.length && !d.to.length && !d.cc.length && (
                <Alert kind="warn">{t("delivery.onlyYouWarn", { me: sender.meta.address })}</Alert>
              )}
              <Switch checked={d.reply_all} onChange={(reply_all) => set({ reply_all })} label={t("delivery.replyAll")} />
              <div><Label>{t("delivery.extraRecipients")}</Label>
                <div className="grid gap-4 sm:grid-cols-2">
                  <EmailChips value={d.to} onChange={(to) => set({ to })} placeholder={`${t("delivery.to")} — ${t("delivery.addEmail")}`} suggestions={suggestions} />
                  <EmailChips value={d.cc} onChange={(cc) => set({ cc })} placeholder={`${t("delivery.cc")} — ${t("delivery.addEmail")}`} suggestions={suggestions} />
                </div>
              </div>
            </div>
          ) : <Alert kind="info">{t("problems.sender")}</Alert>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------- code */

export function CodeSourcesEditor({ profile, update }: { profile: Profile; update: Update }) {
  const { t } = useTranslation();
  const { data: connections } = useConnections();
  const codeConns = (connections ?? []).filter((c) => c.type === "gitlab" || c.type === "github");
  const sources = profile.code_sources;
  const used = new Set(sources.map((s) => s.connection_id));
  const [adding, setAdding] = useState(sources.length === 0);
  const setSource = (idx: number, patch: Partial<CodeSource>) =>
    update({ code_sources: sources.map((s, i) => (i === idx ? { ...s, ...patch } : s)) });
  const addSource = (id: string) => {
    if (used.has(id)) return;
    update({ code_sources: [...sources, { connection_id: id, projects: "all", exclude: [], authors: [], include_merge_commits: false }] });
    setAdding(false);
  };
  const unused = codeConns.filter((c) => !used.has(c.id));

  return (
    <div className="space-y-5">
      <div>
        <div className="mb-2 text-sm font-semibold">{t("code.sources")}</div>
        {sources.length === 0 && <p className="text-sm text-muted">{t("code.noSources")}</p>}
        <div className="space-y-3">
          {sources.map((s, idx) => {
            const conn = connections?.find((c) => c.id === s.connection_id);
            if (!conn) return null;
            return (
              <div key={s.connection_id} className="rounded-xl border border-line bg-surface2 p-4">
                <ConnectionRow conn={conn} right={
                  <Button variant="ghost" size="sm" onClick={() => update({ code_sources: sources.filter((_, i) => i !== idx) })}>
                    <Trash2 className="h-4 w-4" />
                  </Button>} />
                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <div>
                    <Label>{t("code.projects")}</Label>
                    <ProjectPicker connectionId={conn.id} value={s.projects} onChange={(projects) => setSource(idx, { projects })} />
                  </div>
                  <div>
                    <Label hint={t("profile.authorsHint")}>{t("profile.authors")}</Label>
                    <Input className="ltr" value={s.authors.join(", ")}
                      onChange={(e) => setSource(idx, { authors: e.target.value.split(",").map((a) => a.trim()).filter(Boolean) })} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {unused.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-muted">{t("common.useExisting")}</div>
          {unused.map((c) => <ConnectionRow key={c.id} conn={c} onClick={() => addSource(c.id)} right={<Plus className="h-4 w-4 text-primary" />} />)}
        </div>
      )}
      {adding ? <CodeConnect onConnected={(c) => addSource(c.id)} />
        : <Button variant="secondary" icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>{t("common.addNew")}</Button>}
    </div>
  );
}

/* ------------------------------------------------------------------ slack */

export function SlackEditor({ profile, update, showConnect = true }: { profile: Profile; update: Update; showConnect?: boolean }) {
  const { t } = useTranslation();
  const { data: connections } = useConnections();
  const slackConns = (connections ?? []).filter((c) => c.type === "slack");
  const s = profile.slack;
  const set = (patch: Partial<Profile["slack"]>) => update({ slack: { ...s, ...patch } });
  const [adding, setAdding] = useState(false);

  return (
    <div className="space-y-5">
      {slackConns.length > 0 && (
        <div className="space-y-2">
          <Label>{t("profile.slackAccount")}</Label>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="radio" className="accent-primary" checked={!s.connection_id} onChange={() => set({ connection_id: null, conversations: [] })} />
            {t("profile.noSlack")}
          </label>
          {slackConns.map((c) => (
            <ConnectionRow key={c.id} conn={c} selected={s.connection_id === c.id}
              onClick={() => set({ connection_id: c.id, conversations: s.connection_id === c.id ? s.conversations : [] })} />
          ))}
          {!adding && showConnect && <Button variant="ghost" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>{t("common.addNew")}</Button>}
        </div>
      )}
      {showConnect && (slackConns.length === 0 || adding) && (
        <SlackConnect onConnected={(c) => { set({ connection_id: c.id, conversations: [] }); setAdding(false); }} />
      )}
      {s.connection_id && (
        <div className="space-y-4">
          <div>
            <Label hint={t("slack.pickHint")}>{t("slack.pick")}</Label>
            <ConversationPicker connectionId={s.connection_id} value={s.conversations} onChange={(conversations) => set({ conversations })} />
          </div>
          <div>
            <Label hint={t("slack.ignoreHint")}>{t("slack.ignore")}</Label>
            <Textarea rows={4} dir="auto" value={s.ignore_messages.join("\n")}
              onChange={(e) => set({ ignore_messages: e.target.value.split("\n") })}
              onBlur={() => set({ ignore_messages: s.ignore_messages.map((x) => x.trim()).filter(Boolean) })} />
          </div>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------- ai */

export function AIEditor({ profile, update }: { profile: Profile; update: Update }) {
  return (
    <ConnectionPicker type="ai" value={profile.ai_connection_id} onChange={(id) => update({ ai_connection_id: id })} />
  );
}

export function SenderEditor({ profile, update }: { profile: Profile; update: Update }) {
  return (
    <ConnectionPicker type="email" value={profile.sender_connection_id} onChange={(id) => update({ sender_connection_id: id })} />
  );
}

/* --------------------------------------------------------------- schedule */

/** A one-time send must be in the future; recurring and send-now are always valid. */
export function scheduleValid(s: Profile["schedule"]): boolean {
  if ((s.mode ?? "recurring") !== "once") return !!s.time;
  return !!s.once_date && !!s.time && msUntil(s.once_date, s.time, s.timezone) > 0;
}

export function ScheduleEditor({ profile, update, showNames = true, inWizard = showNames }: {
  profile: Profile; update: Update; showNames?: boolean; inWizard?: boolean;
}) {
  const { t } = useTranslation();
  const s = profile.schedule;
  const mode = s.mode ?? "recurring";
  const set = (patch: Partial<Profile["schedule"]>) => update({ schedule: { ...s, ...patch } });
  const days = expandDays(s.days);
  const current = compactDays(days);
  const preset = Object.entries(DAY_PRESETS).find(([, v]) => compactDays(expandDays(v)) === current)?.[0] ?? "custom";
  const zones = timezones();
  const modes: { key: ScheduleMode; icon: ReactNode }[] = [
    { key: "recurring", icon: <Repeat className="h-5 w-5" /> },
    { key: "once", icon: <CalendarClock className="h-5 w-5" /> },
    { key: "now", icon: <Send className="h-5 w-5" /> },
  ];
  const pickMode = (next: ScheduleMode) =>
    set({ mode: next, once_date: next === "once" ? (s.once_date || dayIn(s.timezone)) : s.once_date });
  const onceInPast = mode === "once" && !!s.once_date && msUntil(s.once_date, s.time, s.timezone) <= 0;

  return (
    <div className="space-y-5">
      {showNames && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div><Label hint={t("schedule.reportNameHint")}>{t("schedule.reportName")}</Label>
            <Input value={profile.name} onChange={(e) => update({ name: e.target.value })} /></div>
          <div><Label hint={t("schedule.reportTitleHint")}>{t("schedule.reportTitle")}</Label>
            <Input value={profile.report.title} onChange={(e) => update({ report: { ...profile.report, title: e.target.value } })} /></div>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        {modes.map((m) => (
          <button key={m.key} type="button" onClick={() => pickMode(m.key)}
            className={cn("rounded-xl border p-4 text-start transition-all hover:border-primary/60",
              mode === m.key ? "border-primary bg-primary/10 shadow-glow" : "border-line bg-surface2")}>
            <span className={mode === m.key ? "text-primary" : "text-muted"}>{m.icon}</span>
            <div className="mt-2 font-semibold">{t(`schedule.modes.${m.key}`)}</div>
            <div className="text-xs text-muted">{t(`schedule.modeHints.${m.key}`)}</div>
          </button>
        ))}
      </div>

      {mode === "now" ? (
        <Alert kind="info">{t(inWizard ? "schedule.nowWizard" : "schedule.nowEdit")}</Alert>
      ) : (
        <>
          <div className={cn("grid gap-4", mode === "once" ? "sm:grid-cols-[180px_150px_1fr]" : "sm:grid-cols-[180px_1fr]")}>
            {mode === "once" && (
              <div>
                <Label>{t("schedule.date")}</Label>
                <Input type="date" className="ltr text-lg" value={s.once_date ?? ""} min={dayIn(s.timezone)}
                  onChange={(e) => e.target.value && set({ once_date: e.target.value })} />
              </div>
            )}
            <div>
              <Label>{t("schedule.time")}</Label>
              <Input type="time" className="ltr text-lg" value={s.time} onChange={(e) => e.target.value && set({ time: e.target.value })} />
            </div>
            <div>
              <Label>{t("schedule.timezone")}</Label>
              <Select value={s.timezone} onChange={(timezone) => set({ timezone })}
                options={(zones.includes(s.timezone) ? zones : [s.timezone, ...zones]).map((z) => ({ value: z, label: z }))} />
            </div>
          </div>
          {onceInPast && <Alert kind="warn">{t("schedule.oncePast")}</Alert>}
          {mode === "recurring" && <RecurringDays days={days} preset={preset} set={set} />}
          <Switch checked={s.catch_up} onChange={(catch_up) => set({ catch_up })} label={t("schedule.catchUp")} />
          <div>
            <Switch checked={s.skip_empty ?? true} onChange={(skip_empty) => set({ skip_empty })} label={t("schedule.skipEmpty")} />
            <p className="ms-14 mt-1 text-xs text-muted">{t("schedule.skipEmptyHint")}</p>
          </div>
        </>
      )}
    </div>
  );
}

function RecurringDays({ days, preset, set }: {
  days: Set<string>; preset: string; set: (patch: Partial<Profile["schedule"]>) => void;
}) {
  const { t } = useTranslation();
  return (
    <div>
      <Label>{t("schedule.days")}</Label>
      <div className="mb-3 flex flex-wrap gap-2">
        {(["sun_thu", "mon_fri", "everyday"] as const).map((k) => (
          <button key={k} type="button" onClick={() => set({ days: DAY_PRESETS[k] })}
            className={cn("rounded-lg border px-3 py-1.5 text-sm", preset === k ? "border-primary bg-primary/15 text-ink" : "border-line text-muted hover:text-ink")}>
            {t(`schedule.presets.${k}`)}
          </button>
        ))}
        {preset === "custom" && <span className="rounded-lg border border-primary bg-primary/15 px-3 py-1.5 text-sm">{t("schedule.presets.custom")}</span>}
      </div>
      <div className="flex flex-wrap gap-2">
        {DAYS.map((d) => {
          const on = days.has(d);
          return (
            <button key={d} type="button"
              onClick={() => {
                const next = new Set(days);
                on ? next.delete(d) : next.add(d);
                if (next.size) set({ days: compactDays(next) });
              }}
              className={cn("h-11 w-14 rounded-lg border text-sm font-medium transition-colors",
                on ? "border-primary bg-primary text-white" : "border-line bg-surface2 text-muted hover:text-ink")}>
              {t(`schedule.dayNames.${d}`)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ report */

const LANGUAGES = ["English", "Arabic", "French", "German", "Spanish", "Turkish"];

export function ReportEditor({ profile, update }: { profile: Profile; update: Update }) {
  const { t } = useTranslation();
  const r = profile.report;
  const set = (patch: Partial<Profile["report"]>) => update({ report: { ...r, ...patch } });
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="sm:col-span-2"><Label>{t("schedule.reportTitle")}</Label>
          <Input value={r.title} onChange={(e) => set({ title: e.target.value })} /></div>
        <div><Label>{t("profile.language")}</Label>
          <Select value={r.language} onChange={(language) => set({ language })}
            options={(LANGUAGES.includes(r.language) ? LANGUAGES : [r.language, ...LANGUAGES]).map((l) => ({ value: l, label: l }))} /></div>
      </div>
      <div>
        <Label>{t("profile.sections")}</Label>
        <div className="grid gap-2 sm:grid-cols-2">
          {(Object.keys(r.sections) as (keyof typeof r.sections)[]).map((k) => (
            <Checkbox key={k} checked={r.sections[k]} onChange={(v) => set({ sections: { ...r.sections, [k]: v } })}>
              {t(`profile.sec.${k}`)}
            </Checkbox>
          ))}
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="sm:col-span-2"><Label>{t("profile.extra")}</Label>
          <Textarea rows={3} value={r.extra_instructions} placeholder={t("profile.extraPh")}
            onChange={(e) => set({ extra_instructions: e.target.value })} /></div>
        <div><Label>{t("profile.maxPoints")}</Label>
          <Input type="number" min={1} max={15} value={r.max_points} onChange={(e) => set({ max_points: Math.max(1, Math.min(15, Number(e.target.value) || 6)) })} /></div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div><Label>{t("sender.displayName")}</Label>
          <Input value={profile.delivery.sender_name} onChange={(e) => update({ delivery: { ...profile.delivery, sender_name: e.target.value } })} /></div>
      </div>
      <Switch checked={r.branding} onChange={(branding) => set({ branding })} label={t("profile.branding")} />
    </div>
  );
}