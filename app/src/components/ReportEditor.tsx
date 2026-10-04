import { Code2, MessageSquare, Plus, Sparkles, Trash2, Undo2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import type { DraftContent } from "../lib/types";
import { cn } from "../lib/utils";
import { Alert, Button, Card, Input, Label, Textarea } from "./ui";

const MAJOR = "[Major]";
const isMajor = (point: string) => point.startsWith(MAJOR);
const textOf = (point: string) => (isMajor(point) ? point.slice(MAJOR.length).trimStart() : point);
const withMajor = (text: string, major: boolean) => (major ? `${MAJOR} ${text}` : text);

/** Edits a previewed report by hand or by asking the report's AI. */
export function ReportEditor({ draftId, content, onChange }: {
  draftId: string; content: DraftContent; onChange: (content: DraftContent) => void;
}) {
  const { t } = useTranslation();
  const [instruction, setInstruction] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState("");
  const [beforeAI, setBeforeAI] = useState<DraftContent | null>(null);

  const setPoints = (index: number, points: string[]) =>
    onChange({ ...content, items: content.items.map((it, i) => (i === index ? { ...it, points } : it)) });

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

  return (
    <div className="space-y-4">
      <Card className="space-y-3 bg-brand-soft">
        <div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-primary" />{t("editor.aiTitle")}</div>
        <p className="text-xs text-muted">{t("editor.aiHint")}</p>
        <Textarea rows={2} dir="auto" value={instruction} placeholder={t("editor.aiPlaceholder")}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && instruction.trim()) void askAI(); }} />
        <div className="flex flex-wrap gap-2">
          <Button variant="brand" icon={<Sparkles className="h-4 w-4" />} loading={aiBusy} disabled={!instruction.trim()} onClick={askAI}>
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
          <Label hint={t("editor.noteHint")}>{t("editor.note")}</Label>
          <Textarea rows={3} dir="auto" value={content.note} placeholder={t("editor.notePlaceholder")}
            onChange={(e) => onChange({ ...content, note: e.target.value })} />
        </div>
      </Card>

      {content.items.length === 0 && <p className="text-sm text-muted">{t("editor.empty")}</p>}
      {content.items.map((item, index) => (
        <Card key={item.key} className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            {item.kind === "project" ? <Code2 className="h-4 w-4 text-primary" /> : <MessageSquare className="h-4 w-4 text-violet" />}
            <span dir="auto">{item.name}</span>
          </div>
          {item.points.length === 0 && (
            <p className="text-xs text-muted">{t(item.kind === "project" ? "editor.noPointsCode" : "editor.noPointsSlack")}</p>
          )}
          {item.points.map((point, i) => (
            <div key={i} className="flex items-start gap-2">
              <button type="button" title={t("editor.majorHint")}
                onClick={() => setPoints(index, item.points.map((p, j) => (j === i ? withMajor(textOf(p), !isMajor(p)) : p)))}
                className={cn("mt-2 shrink-0 rounded px-1.5 py-0.5 text-3xs font-bold tracking-wide transition-colors",
                  isMajor(point) ? "bg-warn/15 text-warn" : "bg-surface2 text-muted hover:text-ink")}>
                {t("editor.major")}
              </button>
              <Textarea rows={2} dir="auto" className="flex-1" value={textOf(point)}
                onChange={(e) => setPoints(index, item.points.map((p, j) => (j === i ? withMajor(e.target.value, isMajor(p)) : p)))} />
              <button type="button" aria-label={t("editor.removePoint")} title={t("editor.removePoint")}
                onClick={() => setPoints(index, item.points.filter((_, j) => j !== i))}
                className="mt-1.5 rounded p-1.5 text-muted hover:bg-danger/10 hover:text-danger">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
          <Button size="sm" variant="ghost" icon={<Plus className="h-4 w-4" />} onClick={() => setPoints(index, [...item.points, ""])}>
            {t("editor.addPoint")}
          </Button>
        </Card>
      ))}
    </div>
  );
}
