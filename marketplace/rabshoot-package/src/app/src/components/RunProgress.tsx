import { AlertTriangle, CheckCircle2, Circle, Loader2, MinusCircle, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { RunProgress, RunStage } from "../lib/types";
import { cn } from "../lib/utils";
import { Alert } from "./ui";

const ORDER: RunStage[] = ["code", "slack", "ai", "render", "email"];

type StageState = "done" | "warn" | "error" | "skipped" | "active" | "pending";

function stageStates(p: RunProgress): Record<RunStage, StageState> {
  const current = p.stage === "prepare" ? -1 : ORDER.indexOf(p.stage);
  const finished = p.status !== "running";
  const out = {} as Record<RunStage, StageState>;
  ORDER.forEach((stage, i) => {
    const steps = p.steps.filter((s) => s.key === stage);
    const worst = steps.some((s) => s.status === "error") ? "error"
      : steps.some((s) => s.status === "warn") ? "warn"
        : steps.length && steps.every((s) => s.status === "skipped") ? "skipped" : null;
    if (i < current || (finished && p.status !== "failed")) out[stage] = worst ?? "done";
    else if (i === current) out[stage] = finished ? (worst ?? "error") : "active";
    else out[stage] = "pending";
  });
  return out;
}

const ICON: Record<StageState, JSX.Element> = {
  done: <CheckCircle2 className="h-3.5 w-3.5 text-ok" />,
  warn: <AlertTriangle className="h-3.5 w-3.5 text-warn" />,
  error: <XCircle className="h-3.5 w-3.5 text-danger" />,
  skipped: <MinusCircle className="h-3.5 w-3.5 text-muted" />,
  active: <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />,
  pending: <Circle className="h-3.5 w-3.5 text-muted/50" />,
};

export function RunProgressView({ progress: p, compact }: { progress: RunProgress; compact?: boolean }) {
  const { t } = useTranslation();
  const finished = p.status !== "running";
  const failed = p.status === "failed";
  const states = stageStates(p);
  const title = finished ? t(`progress.done.${p.status}`)
    : p.stage === "email" && !p.sending ? t("progress.stage.recipients")
      : t(`progress.stage.${p.stage}`);

  return (
    <div className={cn("space-y-2.5 rounded-xl border p-4",
      failed ? "border-danger/40 bg-danger/5" : finished ? "border-ok/40 bg-ok/5" : "border-primary/40 bg-primary/5")}>
      <div className="flex items-center justify-between gap-3 text-sm">
        <div className="flex min-w-0 items-center gap-2 font-medium">
          {finished ? (failed ? <XCircle className="h-4 w-4 shrink-0 text-danger" /> : <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" />)
            : <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />}
          <span className="truncate">{title}</span>
        </div>
        <span className="ltr shrink-0 tabular-nums text-muted">{p.percent}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={p.percent} aria-valuemin={0} aria-valuemax={100}>
        <div className={cn("h-full rounded-full transition-all duration-700",
          failed ? "bg-danger" : finished ? "bg-ok" : "bg-primary")} style={{ width: `${Math.max(p.percent, 3)}%` }} />
      </div>
      {!finished && p.total > 0 && (
        <div className="flex min-w-0 gap-1.5 text-xs text-muted">
          <span className="ltr shrink-0 tabular-nums">{p.current}/{p.total}</span>
          {p.item && <><span>·</span><span className="truncate" dir="auto">{p.item}</span></>}
        </div>
      )}
      {!compact && (
        <ol className="flex flex-wrap gap-x-4 gap-y-1.5 pt-0.5 text-xs">
          {ORDER.map((stage) => (
            <li key={stage} className={cn("flex items-center gap-1.5",
              states[stage] === "pending" ? "text-muted/70" : states[stage] === "active" ? "font-medium text-ink" : "text-muted")}>
              {ICON[states[stage]]}
              {t(`progress.short.${stage}`)}
            </li>
          ))}
        </ol>
      )}
      {failed && p.error && <Alert kind="error">{p.error}</Alert>}
    </div>
  );
}
