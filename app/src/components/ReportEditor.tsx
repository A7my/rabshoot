import { RotateCcw, Sparkles, Undo2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import type { DraftContent } from "../lib/types";
import { Alert, Button, Card, Input, Label, Textarea } from "./ui";

/** Edits a previewed email: the whole text by hand, or polished by the report's AI. */
export function ReportEditor({ draftId, content, original, onChange }: {
  draftId: string; content: DraftContent; original: DraftContent; onChange: (content: DraftContent) => void;
}) {
  const { t } = useTranslation();
  const [instruction, setInstruction] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState("");
  const [beforeAI, setBeforeAI] = useState<DraftContent | null>(null);

  const askAI = async () => {
    setAiBusy(true); setAiError("");
    try {
      const r = await api.draftAI(draftId, content, instruction);
      setBeforeAI(content);
      onChange(r.content);
      setInstruction("");
    } catch (e: any) {
      setAiError(e.message);
    } finally {
      setAiBusy(false);
    }
  };

  const changed = content.body !== original.body || content.subject !== original.subject;
  return (
    <div className="space-y-4">
      <Card className="space-y-3 bg-brand-soft">
        <div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-primary" />{t("editor.aiTitle")}</div>
        <p className="text-xs text-muted">{t("editor.aiHint")}</p>
        <Textarea rows={2} dir="auto" value={instruction} placeholder={t("editor.aiPlaceholder")}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void askAI(); }} />
        <div className="flex flex-wrap gap-2">
          <Button variant="brand" icon={<Sparkles className="h-4 w-4" />} loading={aiBusy} disabled={!content.body.trim()} onClick={askAI}>
            {t("editor.aiApply")}
          </Button>
          {beforeAI && !aiBusy && (
            <Button variant="ghost" icon={<Undo2 className="h-4 w-4" />} onClick={() => { onChange(beforeAI); setBeforeAI(null); }}>
              {t("editor.undo")}
            </Button>
          )}
        </div>
        {aiError && <Alert kind="error">{aiError}</Alert>}
      </Card>

      <Card className="space-y-4">
        <div>
          <Label hint={t("editor.subjectHint")}>{t("editor.subject")}</Label>
          <Input dir="auto" value={content.subject} onChange={(e) => onChange({ ...content, subject: e.target.value })} />
        </div>
        <div>
          <Label hint={t("editor.bodyHint")}>{t("editor.body")}</Label>
          <Textarea rows={16} dir="auto" spellCheck className="min-h-[18rem] resize-y leading-relaxed" value={content.body}
            onChange={(e) => onChange({ ...content, body: e.target.value })} />
        </div>
        {changed && (
          <Button size="sm" variant="ghost" icon={<RotateCcw className="h-4 w-4" />}
            onClick={() => { onChange(original); setBeforeAI(null); }}>
            {t("editor.reset")}
          </Button>
        )}
      </Card>
    </div>
  );
}
