import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, History, Send } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { useConnections } from "../components/connect";
import { PreviewPanel } from "../components/PreviewPanel";
import { Alert, Button, Card, Input, Label, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { dayIn, formatDay, shiftDay } from "../lib/utils";

/** Sends a report for a day that already passed, separate from the normal (today) send. */
export function OldReport() {
  const { t, i18n } = useTranslation();
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: profile, isLoading, error } = useQuery({ queryKey: ["profile", id], queryFn: () => api.profile(id) });
  const { data: connections } = useConnections();
  const latest = profile ? shiftDay(dayIn(profile.schedule.timezone), -1) : "";
  const [picked, setPicked] = useState("");
  const day = picked || latest;
  const send = useMutation({
    mutationFn: () => api.sendNow(id, day),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["profiles"] }); navigate("/"); },
  });

  if (isLoading || !profile) return error ? <Alert kind="error">{(error as Error).message}</Alert> : <Spinner label={t("common.loading")} />;
  const sender = connections?.find((c) => c.id === profile.sender_connection_id);
  const blocked = profile.problems.length > 0 || profile.running;

  return (
    <div className="max-w-4xl">
      <button onClick={() => navigate("/")} className="mb-4 flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4 rtl:rotate-180" />{t("nav.dashboard")}
      </button>
      <h1 className="flex items-center gap-2 text-2xl font-bold"><History className="h-6 w-6 text-primary" />{t("oldReport.title")}</h1>
      <p className="mt-1 text-sm text-muted" dir="auto">{profile.name}</p>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">{t("oldReport.intro")}</p>

      <Card className="mt-6 space-y-5">
        <div className="flex flex-wrap items-end gap-4">
          <div className="w-52">
            <Label>{t("oldReport.day")}</Label>
            <Input type="date" className="ltr text-lg" value={day} max={latest}
              onChange={(e) => e.target.value && e.target.value <= latest && setPicked(e.target.value)} />
          </div>
          <div className="pb-2.5 text-lg font-semibold">{formatDay(day, i18n.language)}</div>
        </div>
        {profile.problems.length > 0 && (
          <Alert kind="warn">{profile.problems.map((p) => t(`problems.${p}`)).join(" · ")}</Alert>
        )}
        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-5">
          <Button variant="brand" icon={<Send className="h-4 w-4" />} disabled={blocked} loading={send.isPending}
            onClick={() => send.mutate()}>
            {t("oldReport.send", { day: formatDay(day, i18n.language) })}
          </Button>
          <span className="text-xs text-muted">{t("oldReport.sendHint")}</span>
        </div>
        {send.error && <Alert kind="error">{(send.error as Error).message}</Alert>}
      </Card>

      <h2 className="mb-3 mt-8 font-semibold">{t("oldReport.previewTitle")}</h2>
      <PreviewPanel key={day} profileId={profile.id} senderAddress={sender?.meta.address} day={day} />
    </div>
  );
}
