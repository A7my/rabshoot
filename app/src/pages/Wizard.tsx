import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, CheckCircle2, Languages, Send, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { AIEditor, CodeSourcesEditor, DeliveryEditor, ScheduleEditor, scheduleValid, SenderEditor, SlackEditor } from "../components/editors";
import { Brand } from "../components/Layout";
import { PreviewPanel } from "../components/PreviewPanel";
import { useConnections } from "../components/connect";
import { Alert, Button } from "../components/ui";
import { applyLanguage } from "../i18n";
import { api } from "../lib/api";
import type { Profile } from "../lib/types";
import { cn, localTimezone, newProfile, toProfile } from "../lib/utils";

const STEPS = ["welcome", "sender", "delivery", "code", "slack", "ai", "schedule", "preview"] as const;
type StepKey = (typeof STEPS)[number];
const DRAFT_KEY = "rabshoot.wizard";

function loadDraft(): { profile: Profile; step: number } | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const draft = JSON.parse(raw);
    draft.profile.schedule = { mode: "recurring", once_date: null, skip_empty: true, ...draft.profile.schedule };
    return draft;
  } catch {
    return null;
  }
}

export function Wizard({ mode }: { mode: "onboarding" | "new" }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const draft = mode === "onboarding" ? loadDraft() : null;
  const steps = mode === "onboarding" ? STEPS : STEPS.slice(1);
  const [profile, setProfile] = useState<Profile>(draft?.profile ?? newProfile(localTimezone()));
  const [index, setIndex] = useState(Math.min(draft?.step ?? 0, steps.length - 1));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { data: connections } = useConnections();
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });

  const step: StepKey = steps[index];
  const update = (patch: Partial<Profile>) => setProfile((p) => ({ ...p, ...patch }));

  useEffect(() => {
    if (mode === "onboarding") localStorage.setItem(DRAFT_KEY, JSON.stringify({ profile, step: index }));
  }, [profile, index, mode]);

  const slackOffered = useRef(false);
  useEffect(() => {
    if (step !== "slack" || slackOffered.current || !connections) return;
    slackOffered.current = true;
    const slack = connections.find((c) => c.type === "slack");
    if (slack && !profile.slack.connection_id) update({ slack: { ...profile.slack, connection_id: slack.id } });
  }, [step, connections]); // eslint-disable-line react-hooks/exhaustive-deps

  const d = profile.delivery;
  const valid: Record<StepKey, boolean> = {
    welcome: true,
    sender: !!profile.sender_connection_id,
    delivery: d.mode === "recipients" ? d.to.length > 0 : !!(d.thread && (d.thread.subject || d.thread.message_id)),
    code: profile.code_sources.length > 0,
    slack: !profile.slack.connection_id || profile.slack.conversations.length > 0,
    ai: !!profile.ai_connection_id,
    schedule: scheduleValid(profile.schedule),
    preview: true,
  };

  const save = async (): Promise<Profile> => {
    const body: any = toProfile(profile);
    if (!body.id) {
      delete body.id;
      if (!body.slack.ignore_messages.length) delete body.slack.ignore_messages;
      const created = await api.createProfile(body);
      setProfile(created);
      return created;
    }
    const saved = await api.updateProfile(body);
    setProfile(saved);
    return saved;
  };

  const next = async () => {
    setError("");
    if (step === "schedule") {
      setSaving(true);
      try { await save(); } catch (e: any) { setError(e.message); setSaving(false); return; }
      setSaving(false);
    }
    if (step === "preview") return finish();
    setIndex((i) => Math.min(i + 1, steps.length - 1));
  };

  const finish = async () => {
    setSaving(true);
    try {
      const saved = await save();
      if (saved.schedule.mode === "now") await api.sendNow(saved.id);
      if (settings && !settings.onboarding_done) {
        await api.saveSettings({ ...settings, onboarding_done: true, language: i18n.language as "en" | "ar" });
      }
      localStorage.removeItem(DRAFT_KEY);
      qc.invalidateQueries();
      navigate("/", { replace: true });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const sendingNow = profile.schedule.mode === "now";
  const finishLabel = sendingNow ? t("wizard.finishSend") : t("wizard.finish");

  const skipSlack = () => { update({ slack: { ...profile.slack, connection_id: null, conversations: [] } }); setIndex(index + 1); };
  const sender = connections?.find((c) => c.id === profile.sender_connection_id);

  const content: Record<StepKey, ReactNode> = {
    welcome: <Welcome />,
    sender: <SenderEditor profile={profile} update={update} />,
    delivery: <DeliveryEditor profile={profile} update={update} />,
    code: <CodeSourcesEditor profile={profile} update={update} />,
    slack: <SlackEditor profile={profile} update={update} />,
    ai: <AIEditor profile={profile} update={update} />,
    schedule: <ScheduleEditor profile={profile} update={update} />,
    preview: profile.id ? <PreviewPanel profileId={profile.id} senderAddress={sender?.meta.address} /> : null,
  };
  const heading: Record<StepKey, [string, string]> = {
    welcome: [t("wizard.welcomeTitle"), t("wizard.welcomeBody")],
    sender: [t("sender.title"), t("sender.intro")],
    delivery: [t("delivery.title"), t("delivery.intro")],
    code: [t("code.title"), t("code.intro")],
    slack: [t("slack.title"), t("slack.intro")],
    ai: [t("ai.title"), t("ai.intro")],
    schedule: [t("schedule.title"), t("schedule.intro")],
    preview: [t("preview.title"), t("preview.intro")],
  };
  const required: Partial<Record<StepKey, boolean>> = { sender: true, delivery: true, code: true, ai: true };

  return (
    <div className="flex h-full">
      <aside className="hidden w-72 shrink-0 flex-col border-e border-line bg-surface/60 p-6 md:flex">
        <Brand />
        <ol className="mt-10 space-y-1">
          {steps.map((s, i) => {
            const done = i < index;
            return (
              <li key={s}>
                <button type="button" disabled={i > index} onClick={() => setIndex(i)}
                  className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2 text-start text-sm transition-colors",
                    i === index ? "bg-primary/15 text-ink" : done ? "text-ink/80 hover:bg-surface2" : "text-muted/60")}>
                  <span className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                    done ? "bg-ok text-white" : i === index ? "bg-primary text-white" : "bg-line text-muted")}>
                    {done ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : i + 1}
                  </span>
                  {t(`wizard.steps.${s}`)}
                  {s === "slack" && <span className="ms-auto text-[10px] text-muted">{t("common.optional")}</span>}
                </button>
              </li>
            );
          })}
        </ol>
        {mode === "new" && (
          <Button variant="ghost" className="mt-auto" icon={<X className="h-4 w-4" />} onClick={() => navigate("/")}>{t("common.cancel")}</Button>
        )}
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-8 py-10">
          <div className="mb-2 text-xs font-medium uppercase tracking-wider text-primary">
            {t("wizard.stepOf", { n: index + 1, total: steps.length })}
            {required[step] && <span className="ms-2 text-muted">· {t("common.required")}</span>}
          </div>
          <h1 className="text-2xl font-bold">{heading[step][0]}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">{heading[step][1]}</p>
          {step === "slack" && <p className="mt-2 text-sm text-muted">{t("slack.skipHint")}</p>}

          <div className="mt-8">{content[step]}</div>

          {error && <div className="mt-6"><Alert kind="error">{error}</Alert></div>}

          <div className="mt-10 flex items-center justify-between border-t border-line pt-6">
            <Button variant="ghost" disabled={index === 0} onClick={() => setIndex(index - 1)}
              icon={<ArrowLeft className="h-4 w-4 rtl:rotate-180" />}>{t("common.back")}</Button>
            <div className="flex gap-2">
              {step === "slack" && (
                <Button variant="ghost" onClick={skipSlack}>{t("common.skip")}</Button>
              )}
              <Button variant={step === "welcome" || step === "preview" ? "brand" : "primary"} size={step === "welcome" ? "lg" : "md"}
                disabled={!valid[step]} loading={saving} onClick={next}>
                {step === "welcome" ? t("wizard.start") : step === "preview" ? finishLabel : t("common.next")}
                {step === "preview" ? (sendingNow ? <Send className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />) : <ArrowRight className="h-4 w-4 rtl:rotate-180" />}
              </Button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function Welcome() {
  const { t, i18n } = useTranslation();
  const bullets = t("wizard.welcomeBullets", { returnObjects: true }) as string[];
  return (
    <div className="space-y-8">
      <div className="flex items-center gap-6 rounded-2xl border border-line bg-brand-soft p-6">
        <img src="/logo.png" alt="RabShoot" className="h-36 w-36 shrink-0" />
        <ul className="space-y-3">
          {bullets.map((b) => (
            <li key={b} className="flex gap-3 text-sm">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" />
              <span>{b}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <div className="mb-2 flex items-center gap-2 text-sm font-medium"><Languages className="h-4 w-4 text-primary" />{t("wizard.language")}</div>
        <div className="flex gap-2">
          {([["en", "English"], ["ar", "العربية"]] as const).map(([code, label]) => (
            <button key={code} type="button" onClick={() => applyLanguage(code)}
              className={cn("h-11 min-w-32 rounded-lg border px-5 text-sm font-medium",
                i18n.language === code ? "border-primary bg-primary/15" : "border-line bg-surface2 text-muted hover:text-ink")}>
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
