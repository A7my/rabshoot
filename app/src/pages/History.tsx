import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, History as HistoryIcon, Send } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { EmailFrame, StepsList } from "../components/PreviewPanel";
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Select, Spinner, StatusDot } from "../components/ui";
import { api } from "../lib/api";
import type { Run } from "../lib/types";
import { cn, formatDateTime } from "../lib/utils";

export function History() {
  const { t } = useTranslation();
  const [profileId, setProfileId] = useState("");
  const { data: profiles } = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  const { data: runs, isLoading } = useQuery({
    queryKey: ["runs", profileId], queryFn: () => api.runs(profileId || undefined), refetchInterval: 10_000,
  });
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div>
      <PageHeader title={t("history.title")} actions={
        <Select className="w-60" value={profileId} onChange={setProfileId}
          options={[{ value: "", label: t("history.filterAll") }, ...(profiles ?? []).map((p) => ({ value: p.id, label: p.name }))]} />
      } />
      {isLoading ? <Spinner label={t("common.loading")} /> : !runs?.length ? (
        <EmptyState icon={<HistoryIcon className="h-10 w-10" />} title={t("history.empty")} />
      ) : (
        <div className="space-y-2">
          {runs.map((r) => <RunRow key={r.id} run={r} open={open === r.id} onToggle={() => setOpen(open === r.id ? null : r.id)} />)}
        </div>
      )}
    </div>
  );
}

function RunRow({ run, open, onToggle }: { run: Run; open: boolean; onToggle: () => void }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const { data: detail, isLoading } = useQuery({ queryKey: ["run", run.id], queryFn: () => api.run(run.id), enabled: open });
  const resend = useMutation({
    mutationFn: () => api.sendNow(run.profile_id, run.report_day),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs"] }),
  });
  const canResend = run.status !== "running" && run.trigger !== "preview" && run.trigger !== "test";
  const tone = run.status === "sent" ? "ok" : run.status === "failed" ? "error" : run.status === "running" ? "primary" : "muted";
  return (
    <Card className="p-0">
      <button onClick={onToggle} className="flex w-full items-center gap-4 px-4 py-3 text-start">
        <StatusDot status={run.status} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium" dir="auto">{run.subject || run.profile_name}</div>
          <div className="text-xs text-muted">
            {run.profile_name} · {t("history.day")}: <span className="ltr">{run.report_day}</span> · {formatDateTime(run.started_at, i18n.language)}
          </div>
        </div>
        {run.trigger !== "preview" && <Badge>{t(`trigger.${run.trigger}`)}</Badge>}
        <Badge tone={tone}>{t(`status.${run.status}`)}</Badge>
        <ChevronDown className={cn("h-4 w-4 text-muted transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-4 border-t border-line p-4">
          {run.error && <Alert kind="error">{run.error}</Alert>}
          {resend.isSuccess && <Alert kind="ok">{t("history.resendStarted")}</Alert>}
          {resend.isError && <Alert kind="error">{(resend.error as Error).message}</Alert>}
          {canResend && (
            <Button size="sm" icon={<Send className="h-4 w-4" />} loading={resend.isPending}
              disabled={resend.isSuccess} onClick={() => resend.mutate()}>
              {t("history.resend")}
            </Button>
          )}
          {run.recipients.length > 0 && (
            <div className="text-sm"><span className="text-muted">{t("history.to")}: </span><span className="ltr">{run.recipients.join(", ")}</span></div>
          )}
          {run.steps.length > 0 && <StepsList steps={run.steps} />}
          {isLoading && <Spinner label={t("common.loading")} />}
          {detail?.html && <EmailFrame html={detail.html} />}
        </div>
      )}
    </Card>
  );
}
