import { Eye, Send } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import type { RunProgress, RunResult, Step } from "../lib/types";
import { RunProgressView } from "./RunProgress";
import { Alert, Badge, Button, Card, Spinner, StatusDot } from "./ui";

export function StepsList({ steps }: { steps: Step[] }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1.5">
      {steps.map((s, i) => (
        <div key={i} className="flex items-start gap-2.5 text-sm">
          <span className="mt-1.5"><StatusDot status={s.status} /></span>
          <span className="w-20 shrink-0 font-medium">{t(`preview.steps.${s.key}`)}</span>
          <span className="ltr min-w-0 flex-1 text-start text-muted">{s.message}</span>
        </div>
      ))}
    </div>
  );
}

export function EmailFrame({ html }: { html: string }) {
  return (
    <iframe title="report" srcDoc={html} sandbox="allow-popups allow-popups-to-escape-sandbox"
      className="h-[640px] w-full rounded-lg border border-line bg-white" />
  );
}

/** Builds today's report, or the given past `day` when set. */
export function PreviewPanel({ profileId, senderAddress, day }: { profileId: string; senderAddress?: string; day?: string }) {
  const { t } = useTranslation();
  const [result, setResult] = useState<RunResult | null>(null);
  const [busy, setBusy] = useState<"preview" | "test" | null>(null);
  const [error, setError] = useState("");
  const [sentTo, setSentTo] = useState("");

  const [progress, setProgress] = useState<RunProgress | null>(null);

  const run = async (kind: "preview" | "test") => {
    setBusy(kind); setError(""); setSentTo(""); setProgress(null);
    let polling = true;
    const poll = async () => {
      while (polling) {
        try {
          const r = await api.progress(profileId);
          if (polling && r.progress?.status === "running") setProgress(r.progress);
        } catch { /* the run itself reports errors */ }
        await new Promise((resolve) => setTimeout(resolve, 700));
      }
    };
    void poll();
    try {
      const r = kind === "preview" ? await api.preview(profileId, day) : await api.testSend(profileId, senderAddress, day);
      setResult(r);
      if (r.status === "failed") setError(r.error);
      else if (kind === "test") setSentTo(r.recipients.join(", "));
    } catch (e: any) {
      setError(e.message);
    } finally {
      polling = false;
      setProgress(null);
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" icon={<Eye className="h-4 w-4" />} loading={busy === "preview"} disabled={!!busy} onClick={() => run("preview")}>
          {t("preview.build")}
        </Button>
        <Button icon={<Send className="h-4 w-4" />} loading={busy === "test"} disabled={!!busy} onClick={() => run("test")}>
          {t("preview.sendTest")}
        </Button>
      </div>
      {busy && (progress ? <RunProgressView progress={progress} /> : <Spinner label={t("preview.building")} />)}
      {error && <Alert kind="error">{error}</Alert>}
      {sentTo && <Alert kind="ok">{t("preview.testSent", { to: sentTo })}</Alert>}
      {result && (
        <>
          <Card className="space-y-3 p-4">
            <StepsList steps={result.steps} />
            {result.subject && (
              <div className="border-t border-line pt-3 text-sm">
                <span className="text-muted">{t("preview.subject")}: </span><span dir="auto">{result.subject}</span>
              </div>
            )}
            {result.recipients.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-sm">
                <span className="text-muted">{t("preview.recipients")}:</span>
                {result.recipients.map((r) => <Badge key={r} tone="primary"><span className="ltr">{r}</span></Badge>)}
              </div>
            )}
          </Card>
          {result.html && <EmailFrame html={result.html} />}
        </>
      )}
    </div>
  );
}
