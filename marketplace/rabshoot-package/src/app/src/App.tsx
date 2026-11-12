import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes } from "react-router-dom";
import { Brand, Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { applyLanguage } from "./i18n";
import { api } from "./lib/api";
import { notify, onShellEvent } from "./lib/platform";
import { Connections } from "./pages/Connections";
import { Dashboard } from "./pages/Dashboard";
import { History } from "./pages/History";
import { ProfileEdit } from "./pages/ProfileEdit";
import { OldReport } from "./pages/OldReport";
import { Settings } from "./pages/Settings";
import { Wizard } from "./pages/Wizard";

function Splash({ error }: { error?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6">
      <Brand size="lg" />
      {error ? (
        <div className="max-w-sm text-center">
          <div className="flex items-center justify-center gap-2 text-danger"><AlertTriangle className="h-4 w-4" />{t("engine.unreachable")}</div>
          <p className="mt-1 text-sm text-muted">{t("engine.unreachableHint")}</p>
        </div>
      ) : <Spinner label={t("engine.starting")} />}
    </div>
  );
}

/** Desktop notifications for runs that finish while the window is hidden. */
function useRunNotifications(enabled: boolean) {
  const { t } = useTranslation();
  const seen = useRef<Set<string> | null>(null);
  const { data: runs } = useQuery({ queryKey: ["runs", "notify"], queryFn: () => api.runs(undefined, 20), refetchInterval: 30_000, enabled });
  useEffect(() => {
    if (!runs) return;
    const finished = runs.filter((r) => ["sent", "failed", "skipped"].includes(r.status));
    if (seen.current === null) { seen.current = new Set(finished.map((r) => r.id)); return; }
    for (const r of finished) {
      if (seen.current.has(r.id)) continue;
      seen.current.add(r.id);
      if (!["schedule", "catch_up", "manual"].includes(r.trigger)) continue;
      notify(`RabShoot · ${r.profile_name}`, r.status === "sent"
        ? `${t("status.sent")} → ${r.recipients.join(", ")}`
        : r.status === "skipped" ? t("progress.done.skipped")
          : `${t("status.failed")}: ${r.error ?? ""}`);
    }
  }, [runs, t]);
}

export default function App() {
  const qc = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: 20, retryDelay: 750 });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: health.isSuccess });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles, enabled: health.isSuccess });
  useRunNotifications(!!settings.data?.notifications);

  useEffect(() => onShellEvent("tray-toggle-pause", async () => {
    const current = await api.settings();
    await api.saveSettings({ ...current, paused: !current.paused });
    qc.invalidateQueries();
  }), [qc]);
  useEffect(() => onShellEvent("engine-ready", () => qc.invalidateQueries()), [qc]);

  useEffect(() => {
    if (settings.data && !localStorage.getItem("rabshoot.lang")) applyLanguage(settings.data.language);
  }, [settings.data]);

  if (health.isError) return <Splash error />;
  if (!settings.data || !profiles.data) return <Splash />;

  const onboarding = !settings.data.onboarding_done && profiles.data.length === 0;
  if (onboarding) {
    return (
      <Routes>
        <Route path="*" element={<Wizard mode="onboarding" />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="/profiles/new" element={<Wizard mode="new" />} />
      <Route path="*" element={
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/profiles/:id" element={<ProfileEdit />} />
            <Route path="/profiles/:id/old-report" element={<OldReport />} />
            <Route path="/connections" element={<Connections />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      } />
    </Routes>
  );
}
