import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useConnections } from "../components/connect";
import { AIEditor, CodeSourcesEditor, DeliveryEditor, ReportEditor, ScheduleEditor, SenderEditor, SlackEditor } from "../components/editors";
import { PreviewPanel } from "../components/PreviewPanel";
import { Alert, Button, Card, Input, Label, Spinner, Switch } from "../components/ui";
import { api } from "../lib/api";
import type { Profile } from "../lib/types";
import { cn, toProfile } from "../lib/utils";

const TABS = ["delivery", "code", "slack", "ai", "schedule", "look", "preview"] as const;
type Tab = (typeof TABS)[number];

export function ProfileEdit() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.includes(params.get("tab") as Tab) ? params.get("tab") : "delivery") as Tab;
  const { data, isLoading, error } = useQuery({ queryKey: ["profile", id], queryFn: () => api.profile(id) });
  const { data: connections } = useConnections();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  useEffect(() => { if (data && !dirty) setProfile(toProfile(data)); }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading || !profile) return error ? <Alert kind="error">{(error as Error).message}</Alert> : <Spinner label={t("common.loading")} />;

  const update = (patch: Partial<Profile>) => { setProfile({ ...profile, ...patch }); setDirty(true); setStatus(null); };
  const save = async () => {
    setSaving(true);
    try {
      const saved = await api.updateProfile({ ...profile, slack: { ...profile.slack, ignore_messages: profile.slack.ignore_messages.map((x) => x.trim()).filter(Boolean) } });
      setProfile(saved); setDirty(false);
      setStatus({ kind: "ok", text: t("common.saved") });
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["profile", id] });
    } catch (e: any) {
      setStatus({ kind: "error", text: e.message });
    } finally {
      setSaving(false);
    }
  };
  const remove = async () => {
    if (!window.confirm(t("common.confirmDelete"))) return;
    await api.deleteProfile(profile.id);
    qc.invalidateQueries({ queryKey: ["profiles"] });
    navigate("/");
  };
  const setTab = async (next: Tab) => {
    if (next === "preview" && dirty) await save();
    setParams({ tab: next });
  };
  const sender = connections?.find((c) => c.id === profile.sender_connection_id);

  return (
    <div>
      <button onClick={() => navigate("/")} className="mb-4 flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4 rtl:rotate-180" />{t("nav.dashboard")}
      </button>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-[260px] flex-1">
          <Label>{t("schedule.reportName")}</Label>
          <Input value={profile.name} onChange={(e) => update({ name: e.target.value })} className="h-11 text-lg font-semibold" dir="auto" />
        </div>
        <div className="flex items-center gap-4">
          <Switch checked={profile.enabled} onChange={(enabled) => update({ enabled })} label={t("profile.enabled")} />
          <Button variant="primary" icon={<Save className="h-4 w-4" />} disabled={!dirty} loading={saving} onClick={save}>{t("common.save")}</Button>
        </div>
      </div>
      {dirty && <p className="-mt-3 mb-4 text-xs text-warn">{t("profile.unsaved")}</p>}
      {status && <div className="mb-4"><Alert kind={status.kind}>{status.text}</Alert></div>}
      {data && data.problems.length > 0 && !dirty && (
        <div className="mb-4"><Alert kind="warn">{data.problems.map((p) => t(`problems.${p}`)).join(" · ")}</Alert></div>
      )}

      <div className="mb-6 flex gap-1 overflow-x-auto border-b border-line">
        {TABS.map((k) => (
          <button key={k} onClick={() => setTab(k)}
            className={cn("-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-sm transition-colors",
              tab === k ? "border-primary text-ink" : "border-transparent text-muted hover:text-ink")}>
            {t(`profile.tabs.${k}`)}
          </button>
        ))}
      </div>

      <Card>
        {tab === "delivery" && (
          <div className="space-y-8">
            <section>
              <h3 className="mb-3 font-semibold">{t("profile.sender")}</h3>
              <SenderEditor profile={profile} update={update} />
            </section>
            <section>
              <h3 className="mb-3 font-semibold">{t("delivery.title")}</h3>
              <DeliveryEditor profile={profile} update={update} />
            </section>
          </div>
        )}
        {tab === "code" && <CodeSourcesEditor profile={profile} update={update} />}
        {tab === "slack" && <SlackEditor profile={profile} update={update} />}
        {tab === "ai" && <AIEditor profile={profile} update={update} />}
        {tab === "schedule" && <ScheduleEditor profile={profile} update={update} showNames={false} />}
        {tab === "look" && <ReportEditor profile={profile} update={update} />}
        {tab === "preview" && <PreviewPanel profileId={profile.id} senderAddress={sender?.meta.address} />}
      </Card>

      <div className="mt-8 flex justify-end">
        <Button variant="danger" size="sm" icon={<Trash2 className="h-4 w-4" />} onClick={remove}>{t("profile.deleteReport")}</Button>
      </div>
    </div>
  );
}
