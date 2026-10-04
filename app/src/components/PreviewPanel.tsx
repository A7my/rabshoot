import { useQueryClient } from "@tanstack/react-query";
import { Eye, Pencil, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import type { DraftContent, RunProgress, RunResult, Step } from "../lib/types";
import { ReportEditor } from "./ReportEditor";
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

/** Builds today's report, or the given past `day` when set; the result can be edited and sent as is. */
export function PreviewPanel({ profileId, senderAddress, day, canSend = true }: {
  profileId: string; senderAddress?: string; day?: string; canSend?: boolean;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [result, setResult] = useState<RunResult | null>(null);
  const [busy, setBusy] = useState<"preview" | "test" | "draftTest" | "send" | null>(null);
  const [error, setError] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [progress, setProgress] = useState<RunProgress | null>(null);

  const [draft, setDraft] = useState<{ id: string; content: DraftContent } | null>(null);
  const [original, setOriginal] = useState<DraftContent | null>(null);
  const [html, setHtml] = useState("");
  const [editing, setEditing] = useState(false);
  const [edited, setEdited] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [sentReal, setSentReal] = useState("");
  const renderSeq = useRef(0);

  const run = async (kind: "preview" | "test") => {
    setBusy(kind); setError(""); setSentTo(""); setSentReal(""); setProgress(null); setConfirming(false);
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
      setDraft(r.draft ?? null);
      setOriginal(r.draft?.content ?? null);
      setHtml(r.html ?? "");
      setEdited(false);
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

  useEffect(() => {
    if (!draft || !edited) return;
    const seq = ++renderSeq.current;
    setUpdating(true);
    const timer = setTimeout(async () => {
      try {
        const view = await api.draftRender(draft.id, draft.content);
        if (seq === renderSeq.current) setHtml(view.html);
      } catch (e: any) {
        if (seq === renderSeq.current) setError(e.message);
      } finally {
        if (seq === renderSeq.current) setUpdating(false);
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [draft, edited]);

  const changeContent = (content: DraftContent) => {
    if (!draft) return;
    setDraft({ ...draft, content });
    setEdited(true);
    setSentReal("");
  };

  const sendDraft = async (test: boolean) => {
    if (!draft) return;
    setBusy(test ? "draftTest" : "send"); setError(""); setSentTo("");
    try {
      const r = await api.draftSend(draft.id, draft.content, test, test ? senderAddress : undefined);
      if (r.status === "failed") setError(r.error);
      else if (test) setSentTo(r.recipients.join(", "));
      else {
        setSentReal(r.recipients.join(", "));
        qc.invalidateQueries({ queryKey: ["profiles"] });
        qc.invalidateQueries({ queryKey: ["runs"] });
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
      setConfirming(false);
    }
  };

  const building = busy === "preview" || busy === "test";
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
      {building && (progress ? <RunProgressView progress={progress} /> : <Spinner label={t("preview.building")} />)}
      {error && <Alert kind="error">{error}</Alert>}
      {sentTo && <Alert kind="ok">{t("preview.testSent", { to: sentTo })}</Alert>}
      {sentReal && <Alert kind="ok">{t("preview.sentReal", { to: sentReal })}</Alert>}
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

          {draft && (
            <div className="flex flex-wrap items-center gap-2">
              <Button variant={editing ? "secondary" : "primary"} icon={<Pencil className="h-4 w-4" />} disabled={building}
                onClick={() => setEditing(!editing)}>
                {editing ? t("preview.doneEditing") : t("preview.edit")}
              </Button>
              <Button icon={<Send className="h-4 w-4" />} loading={busy === "draftTest"} disabled={!!busy || updating}
                onClick={() => sendDraft(true)}>
                {t("preview.sendVersionTest")}
              </Button>
              {canSend && (
                <Button variant="brand" icon={<Send className="h-4 w-4" />} disabled={!!busy || updating || !!sentReal}
                  onClick={() => setConfirming(true)}>
                  {t("preview.sendReal")}
                </Button>
              )}
              {edited && <Badge tone="warn">{t("preview.edited")}</Badge>}
              {updating && <Spinner label={t("preview.updating")} />}
            </div>
          )}
          {confirming && (
            <Alert kind="warn" title={t("preview.confirmTitle")}>
              {result.recipients.length ? t("preview.confirmBody", { to: result.recipients.join(", ") }) : t("preview.confirmBodyNoList")}
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="brand" size="sm" icon={<Send className="h-4 w-4" />} loading={busy === "send"} onClick={() => sendDraft(false)}>
                  {t("preview.confirmYes")}
                </Button>
                <Button variant="ghost" size="sm" disabled={busy === "send"} onClick={() => setConfirming(false)}>{t("common.cancel")}</Button>
              </div>
            </Alert>
          )}

          {draft && original && editing && (
            <ReportEditor draftId={draft.id} content={draft.content} original={original} onChange={changeContent} />
          )}
          {html && <EmailFrame html={html} />}
        </>
      )}
    </div>
  );
}
