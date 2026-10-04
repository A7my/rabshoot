import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, FolderOpen, Github, Languages, Linkedin, ShieldCheck, Wand2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { AUTHOR, AUTHOR_URL, Brand, PROJECT_URL } from "../components/Layout";
import { Button, Card, PageHeader, Spinner, Switch } from "../components/ui";
import { applyLanguage } from "../i18n";
import { api } from "../lib/api";
import { copyText, openUrl, setAutostart } from "../lib/platform";
import type { Settings as SettingsT } from "../lib/types";
import { cn } from "../lib/utils";

export function Settings() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health });
  if (!settings) return <Spinner label={t("common.loading")} />;

  const save = async (patch: Partial<SettingsT>) => {
    const next = { ...settings, ...patch };
    qc.setQueryData(["settings"], next);
    await api.saveSettings(next);
    if (patch.autostart !== undefined) await setAutostart(patch.autostart).catch(() => undefined);
    qc.invalidateQueries({ queryKey: ["profiles"] });
  };

  return (
    <div className="space-y-5">
      <PageHeader title={t("settings.title")} />
      <Card className="space-y-4">
        <div className="flex items-center gap-2 text-sm font-medium"><Languages className="h-4 w-4 text-primary" />{t("settings.language")}</div>
        <div className="flex gap-2">
          {([["en", "English"], ["ar", "العربية"]] as const).map(([code, label]) => (
            <button key={code} onClick={() => { applyLanguage(code); save({ language: code }); }}
              className={cn("h-10 min-w-28 rounded-lg border px-4 text-sm",
                i18n.language === code ? "border-primary bg-primary/15" : "border-line bg-surface2 text-muted hover:text-ink")}>
              {label}
            </button>
          ))}
        </div>
      </Card>
      <Card className="space-y-4">
        <Switch checked={settings.autostart} onChange={(autostart) => save({ autostart })} label={t("settings.autostart")} />
        <Switch checked={settings.notifications} onChange={(notifications) => save({ notifications })} label={t("settings.notifications")} />
        <Switch checked={settings.catch_up_default} onChange={(catch_up_default) => save({ catch_up_default })} label={t("settings.catchUp")} />
        <Switch checked={settings.paused} onChange={(paused) => save({ paused })} label={t("settings.pauseAll")} />
      </Card>
      <Card className="space-y-3">
        <Button icon={<Wand2 className="h-4 w-4" />} onClick={() => navigate("/profiles/new")}>{t("settings.rerunWizard")}</Button>
      </Card>
      <Card className="space-y-4">
        <div className="text-sm font-semibold">{t("settings.about")}</div>
        <Brand />
        <div className="grid gap-2 text-sm sm:grid-cols-2">
          <div><span className="text-muted">{t("settings.version")}: </span>{__APP_VERSION__}</div>
          <div className="flex items-center gap-1.5">
            <ShieldCheck className={cn("h-4 w-4", health?.secrets_secure ? "text-ok" : "text-warn")} />
            <span className="text-muted">{t("settings.secrets")}: </span>
            {health ? t(health.secrets_secure ? "settings.keychain" : "settings.file") : "—"}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">{t("settings.developedBy")}</span>
          <span className="font-medium">{AUTHOR}</span>
          <Button size="sm" variant="ghost" icon={<Linkedin className="h-3.5 w-3.5" />} onClick={() => openUrl(AUTHOR_URL)}>LinkedIn</Button>
          <Button size="sm" variant="ghost" icon={<Github className="h-3.5 w-3.5" />} onClick={() => openUrl(PROJECT_URL)}>GitHub</Button>
        </div>
        <p className="text-xs text-muted">{t("settings.dataFolder")}</p>
        {health?.paths && (
          <div className="space-y-2">
            {([["config", t("settings.configPath")], ["data", t("settings.dataPath")], ["logs", t("settings.logsPath")]] as const).map(([key, label]) => (
              <div key={key} className="flex items-center gap-3 rounded-lg border border-line bg-surface2 px-3 py-2 text-xs">
                <FolderOpen className="h-4 w-4 shrink-0 text-muted" />
                <span className="w-24 shrink-0 text-muted">{label}</span>
                <code className="ltr min-w-0 flex-1 truncate" title={health.paths[key]}>{health.paths[key]}</code>
                <Button size="sm" variant="ghost" icon={<Copy className="h-3.5 w-3.5" />} onClick={() => copyText(health.paths[key])}>
                  {t("common.copy")}
                </Button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
