import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CalendarClock, CheckCircle2, Clock, History, Pause, Pencil, Play, Rocket, Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { RunProgressView } from "../components/RunProgress";
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Spinner, StatusDot } from "../components/ui";
import { api } from "../lib/api";
import type { ProfileView } from "../lib/types";
import { dayIn, expandDays, formatDateTime, formatTime, relativeTime, toProfile } from "../lib/utils";

/** Today's scheduled send that hasn't happened yet, and one skipped because it was sent early. */
function todayPlan(p: ProfileView, paused: boolean) {
  const tz = p.schedule.timezone;
  const today = dayIn(tz);
  const active = p.enabled && !paused && p.problems.length === 0;
  return {
    pending: active && p.next_run && dayIn(tz, p.next_run) === today ? p.next_run : null,
    skipped: p.skipped_run && dayIn(tz, p.skipped_run.at) === today ? p.skipped_run : null,
  };
}

function useSendNow(profileId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (day?: string) => api.sendNow(profileId, day),
    onSettled: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

const isBusy = (p: ProfileView) => p.running || p.progress?.status === "running";

export function Dashboard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: profiles, isLoading } = useQuery({
    queryKey: ["profiles"], queryFn: api.profiles,
    refetchInterval: (q) => (q.state.data?.some(isBusy) ? 1000 : 5000),
  });
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const resume = useMutation({
    mutationFn: () => api.saveSettings({ ...settings!, paused: false }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const paused = !!settings?.paused;

  if (isLoading) return <Spinner label={t("common.loading")} />;
  return (
    <div>
      <PageHeader title={t("dashboard.title")} />
      {paused && (
        <div className="mb-5">
          <Alert kind="warn" title={t("dashboard.allPaused")}>
            <Button size="sm" className="mt-2" onClick={() => resume.mutate()} loading={resume.isPending}>{t("dashboard.resumeAll")}</Button>
          </Alert>
        </div>
      )}
      {!profiles?.length ? (
        <EmptyState icon={<Rocket className="h-10 w-10" />} title={t("dashboard.empty")} body={t("dashboard.emptyBody")}
          action={<Button variant="brand" onClick={() => navigate("/profiles/new")}>{t("dashboard.create")}</Button>} />
      ) : (
        <>
          <TodayPanel profiles={profiles} paused={paused} />
          <div className="grid gap-4 lg:grid-cols-2">
            {profiles.map((p) => <ProfileCard key={p.id} profile={p} paused={paused} />)}
          </div>
        </>
      )}
    </div>
  );
}

function TodayPanel({ profiles, paused }: { profiles: ProfileView[]; paused: boolean }) {
  const { t } = useTranslation();
  const rows = profiles
    .map((p) => ({ p, ...todayPlan(p, paused) }))
    .filter(({ p, pending, skipped }) => pending || skipped || (isBusy(p) && p.progress?.trigger === "schedule"))
    .sort((a, b) => (a.pending ?? "9").localeCompare(b.pending ?? "9"));
  if (!rows.length) return null;
  return (
    <Card className="mb-6">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <CalendarClock className="h-4 w-4 text-primary" />{t("dashboard.today")}
      </div>
      <div className="divide-y divide-line">
        {rows.map(({ p, pending, skipped }) => <TodayRow key={p.id} profile={p} pending={pending} skipped={skipped} />)}
      </div>
    </Card>
  );
}

function TodayRow({ profile: p, pending, skipped }: {
  profile: ProfileView; pending: string | null; skipped: ProfileView["skipped_run"];
}) {
  const { t, i18n } = useTranslation();
  const send = useSendNow(p.id);
  const tz = p.schedule.timezone;
  const busy = isBusy(p);
  return (
    <div className="space-y-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium" dir="auto">{p.name}</div>
          {pending && !busy && (
            <div className="flex flex-wrap items-center gap-x-1.5 text-sm text-muted">
              <Clock className="h-3.5 w-3.5" />
              {t("dashboard.scheduledAt")} <span className="ltr font-medium text-ink">{formatTime(pending, i18n.language, tz)}</span>
              <span>· {relativeTime(pending, i18n.language)}</span>
            </div>
          )}
          {skipped && !busy && (
            <div className="flex flex-wrap items-center gap-x-1.5 text-sm text-ok">
              <CalendarCheck className="h-3.5 w-3.5" />
              {t("dashboard.sentEarly", { sent: formatTime(skipped.sent_at, i18n.language, tz), time: formatTime(skipped.at, i18n.language, tz) })}
            </div>
          )}
        </div>
        {pending && !busy && (
          <div className="flex flex-col items-end gap-1">
            <Button variant="primary" size="sm" icon={<Send className="h-4 w-4" />} loading={send.isPending} onClick={() => send.mutate(undefined)}>
              {t("dashboard.sendNow")}
            </Button>
            <span className="text-xs text-muted">{t("dashboard.skipHint", { time: formatTime(pending, i18n.language, tz) })}</span>
          </div>
        )}
      </div>
      {busy && p.progress && <RunProgressView progress={p.progress} compact />}
      {send.error && <Alert kind="error">{(send.error as Error).message}</Alert>}
    </div>
  );
}

function ProfileCard({ profile: p, paused }: { profile: ProfileView; paused: boolean }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const send = useSendNow(p.id);
  const toggle = useMutation({
    mutationFn: () => api.updateProfile({ ...toProfile(p), enabled: !p.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
  const needsSetup = p.problems.length > 0;
  const days = expandDays(p.schedule.days);
  const dayLabel = days.size === 7 ? t("schedule.presets.everyday")
    : ["sat", "sun", "mon", "tue", "wed", "thu", "fri"].filter((d) => days.has(d)).map((d) => t(`schedule.dayNames.${d}`)).join(" · ");
  const last = p.last_run;
  const tz = p.schedule.timezone;
  const { pending, skipped } = todayPlan(p, paused);
  const busy = isBusy(p);
  const active = p.enabled && !paused;
  const mode = p.schedule.mode;

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-lg font-semibold" dir="auto">{p.name}</h3>
            {needsSetup ? <Badge tone="warn">{t("dashboard.needsSetup")}</Badge>
              : busy ? <Badge tone="primary">{t("dashboard.running")}</Badge>
                : !active ? <Badge>{t("dashboard.paused")}</Badge> : null}
          </div>
          <div className="mt-1 flex items-center gap-2 text-sm text-muted">
            <Clock className="h-3.5 w-3.5" />
            {mode === "now" ? t("dashboard.manualOnly")
              : mode === "once" ? <>{t("dashboard.onceOn")} <span className="ltr">{p.schedule.once_date} {p.schedule.time}</span></>
                : <><span className="ltr">{p.schedule.time}</span> · {dayLabel}</>}
          </div>
        </div>
        <Button variant="ghost" size="sm" icon={<Pencil className="h-4 w-4" />} onClick={() => navigate(`/profiles/${p.id}`)}>
          {t("dashboard.editReport")}
        </Button>
      </div>

      {needsSetup ? (
        <ul className="space-y-1 text-sm text-warn">
          {p.problems.map((pr) => <li key={pr}>• {t(`problems.${pr}`)}</li>)}
        </ul>
      ) : (
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-lg bg-surface2 p-3">
            <div className="flex items-center gap-1.5 text-xs text-muted"><CalendarClock className="h-3.5 w-3.5" />{t("dashboard.next")}</div>
            <div className="mt-1 font-medium">{active && p.next_run ? formatDateTime(p.next_run, i18n.language, tz) : "—"}</div>
            {!p.next_run && mode !== "recurring" && (
              <div className="text-xs text-muted">{t(mode === "now" ? "dashboard.noSchedule" : "dashboard.onceDone")}</div>
            )}
            {active && p.next_run && <div className="text-xs text-muted">{relativeTime(p.next_run, i18n.language)}</div>}
            {skipped && (
              <div className="mt-1 flex items-center gap-1 text-xs text-ok">
                <CheckCircle2 className="h-3 w-3 shrink-0" />{t("dashboard.todaySkipped", { time: formatTime(skipped.at, i18n.language, tz) })}
              </div>
            )}
          </div>
          <div className="rounded-lg bg-surface2 p-3">
            <div className="text-xs text-muted">{t("dashboard.last")}</div>
            {last ? (
              <>
                <div className="mt-1 flex items-center gap-2 font-medium"><StatusDot status={last.status} />{t(`status.${last.status}`)}</div>
                <div className="text-xs text-muted">{relativeTime(last.started_at, i18n.language)} · {t(`trigger.${last.trigger}`)}</div>
                {last.status === "skipped" && <div className="mt-1 text-xs text-muted">{t("dashboard.quietDay")}</div>}
              </>
            ) : <div className="mt-1 text-muted">{t("dashboard.never")}</div>}
          </div>
        </div>
      )}
      {p.progress && ["schedule", "catch_up", "manual"].includes(p.progress.trigger) && <RunProgressView progress={p.progress} />}
      {!busy && !p.progress && last?.status === "failed" && last.error && <Alert kind="error">{last.error}</Alert>}
      {send.error && <Alert kind="error">{(send.error as Error).message}</Alert>}

      <div className="mt-auto space-y-1.5">
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" size="sm" icon={<Send className="h-4 w-4" />} disabled={needsSetup || busy}
            loading={send.isPending || busy} onClick={() => send.mutate(undefined)}>
            {busy ? t("dashboard.sending") : t("dashboard.sendNow")}
          </Button>
          <Button variant="ghost" size="sm" icon={<History className="h-4 w-4" />} disabled={needsSetup || busy}
            onClick={() => navigate(`/profiles/${p.id}/old-report`)}>
            {t("dashboard.pastDay")}
          </Button>
          <Button size="sm" onClick={() => navigate(`/profiles/${p.id}?tab=preview`)} disabled={needsSetup || busy}>{t("dashboard.preview")}</Button>
          {mode !== "now" && (
            <Button variant="ghost" size="sm" icon={p.enabled ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              loading={toggle.isPending} onClick={() => toggle.mutate()}>
              {p.enabled ? t("dashboard.pause") : t("dashboard.resume")}
            </Button>
          )}
        </div>
        {pending && !busy && <div className="text-xs text-muted">{t("dashboard.skipHint", { time: formatTime(pending, i18n.language, tz) })}</div>}
      </div>
    </Card>
  );
}

