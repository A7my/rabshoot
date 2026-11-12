import { AlertTriangle, Check, CheckCircle2, ChevronDown, ExternalLink, Info, Loader2, X, XCircle } from "lucide-react";
import {
  forwardRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type KeyboardEvent,
  type ReactNode, type TextareaHTMLAttributes,
} from "react";
import { useTranslation } from "react-i18next";
import { openUrl } from "../lib/platform";
import { cn, EMAIL_RE } from "../lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "brand";

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean; size?: "sm" | "md" | "lg"; icon?: ReactNode }
>(function Button({ variant = "secondary", loading, size = "md", icon, className, children, disabled, ...rest }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all",
        "disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
        size === "sm" && "h-8 px-3 text-xs",
        size === "md" && "h-10 px-4 text-sm",
        size === "lg" && "h-12 px-6 text-base",
        variant === "primary" && "bg-primary text-white hover:bg-primary-hover",
        variant === "brand" && "bg-brand text-white hover:brightness-110 shadow-glow",
        variant === "secondary" && "bg-surface2 text-ink border border-line hover:border-primary/50",
        variant === "ghost" && "text-muted hover:text-ink hover:bg-surface2",
        variant === "danger" && "bg-danger/10 text-danger border border-danger/30 hover:bg-danger/20",
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

export function LinkButton({ url, children, variant = "secondary", size }: { url: string; children: ReactNode; variant?: Variant; size?: "sm" | "md" | "lg" }) {
  return (
    <Button variant={variant} size={size} onClick={() => openUrl(url)} icon={<ExternalLink className="h-4 w-4" />}>
      {children}
    </Button>
  );
}

export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-xl border border-line bg-surface p-5", className)} {...rest}>
      {children}
    </div>
  );
}

export function Label({ children, hint, required }: { children: ReactNode; hint?: ReactNode; required?: boolean }) {
  return (
    <div className="mb-1.5">
      <span className="text-sm font-medium text-ink">
        {children}
        {required && <span className="ms-1 text-danger">*</span>}
      </span>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(
  function Input({ className, invalid, ...rest }, ref) {
    return (
      <input
        ref={ref}
        className={cn(
          "h-10 w-full rounded-lg border bg-bg px-3 text-sm text-ink placeholder:text-muted/60",
          "focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/60",
          invalid ? "border-danger/60" : "border-line",
          className,
        )}
        {...rest}
      />
    );
  },
);

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink placeholder:text-muted/60",
        "focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/60",
        className,
      )}
      {...rest}
    />
  );
}

export function Select({ value, onChange, options, className }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full appearance-none rounded-lg border border-line bg-bg pe-9 ps-3 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary/40"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute end-3 top-3 h-4 w-4 text-muted" />
    </div>
  );
}

export function Switch({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn("relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors", checked ? "bg-primary" : "bg-line")}
      >
        <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all", checked ? "start-[18px]" : "start-0.5")} />
      </button>
      {(label || hint) && (
        <span>
          {label && <span className="block text-sm text-ink">{label}</span>}
          {hint && <span className="block text-xs text-muted">{hint}</span>}
        </span>
      )}
    </label>
  );
}

export function Checkbox({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children?: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5 text-sm">
      <span
        onClick={(e) => { e.preventDefault(); onChange(!checked); }}
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors",
          checked ? "border-primary bg-primary" : "border-line bg-bg",
        )}
      >
        {checked && <Check className="h-3 w-3 text-white" strokeWidth={3} />}
      </span>
      <span onClick={(e) => { e.preventDefault(); onChange(!checked); }} className="min-w-0 flex-1">{children}</span>
    </label>
  );
}

export function Alert({ kind = "info", children, title }: { kind?: "info" | "warn" | "error" | "ok"; children: ReactNode; title?: ReactNode }) {
  const Icon = { info: Info, warn: AlertTriangle, error: XCircle, ok: CheckCircle2 }[kind];
  return (
    <div
      className={cn(
        "flex gap-3 rounded-lg border p-3 text-sm",
        kind === "info" && "border-primary/30 bg-primary/10 text-ink",
        kind === "warn" && "border-warn/30 bg-warn/10 text-ink",
        kind === "error" && "border-danger/30 bg-danger/10 text-ink",
        kind === "ok" && "border-ok/30 bg-ok/10 text-ink",
      )}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0",
        kind === "info" && "text-primary", kind === "warn" && "text-warn",
        kind === "error" && "text-danger", kind === "ok" && "text-ok")} />
      <div className="min-w-0 flex-1">
        {title && <div className="mb-0.5 font-medium">{title}</div>}
        <div className="text-ink/90">{children}</div>
      </div>
    </div>
  );
}

export function Badge({ tone = "muted", children }: { tone?: "muted" | "ok" | "warn" | "error" | "primary" | "violet"; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium",
        tone === "muted" && "bg-line/70 text-muted",
        tone === "ok" && "bg-ok/15 text-ok",
        tone === "warn" && "bg-warn/15 text-warn",
        tone === "error" && "bg-danger/15 text-danger",
        tone === "primary" && "bg-primary/15 text-primary",
        tone === "violet" && "bg-violet/15 text-violet",
      )}
    >
      {children}
    </span>
  );
}

export function Spinner({ label }: { label?: ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted">
      <Loader2 className="h-4 w-4 animate-spin text-primary" />
      {label}
    </div>
  );
}

/** Numbered how-to list with optional action buttons. */
export function Guide({ title, steps, actions, className }: { title?: ReactNode; steps: string[]; actions?: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border border-line bg-brand-soft p-4", className)}>
      {title && <div className="mb-3 text-sm font-semibold">{title}</div>}
      <ol className="space-y-2.5">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/20 text-xs font-bold text-primary">
              {i + 1}
            </span>
            <span className="pt-0.5 text-ink/90">{s}</span>
          </li>
        ))}
      </ol>
      {actions && <div className="mt-4 flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function SecretInput(props: InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input {...props} type={show ? "text" : "password"} autoComplete="off" spellCheck={false} className="ltr pe-16 font-mono" />
      <button type="button" onClick={() => setShow(!show)} className="absolute end-2 top-2 rounded px-2 py-1 text-xs text-muted hover:text-ink">
        {show ? "Hide" : "Show"}
      </button>
    </div>
  );
}

/** Email chips with optional suggestions. */
export function EmailChips({ value, onChange, placeholder, suggestions = [] }: {
  value: string[]; onChange: (v: string[]) => void; placeholder?: string; suggestions?: string[];
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [error, setError] = useState(false);
  const add = (raw: string) => {
    const parts = raw.split(/[,;\s]+/).map((p) => p.trim()).filter(Boolean);
    if (!parts.length) return;
    const bad = parts.filter((p) => !EMAIL_RE.test(p));
    if (bad.length) { setError(true); return; }
    const next = [...value];
    for (const p of parts) if (!next.some((v) => v.toLowerCase() === p.toLowerCase())) next.push(p);
    onChange(next);
    setText("");
    setError(false);
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (["Enter", ",", ";", "Tab"].includes(e.key) && text.trim()) { e.preventDefault(); add(text); }
    if (e.key === "Backspace" && !text && value.length) onChange(value.slice(0, -1));
  };
  const matches = text.length > 0
    ? suggestions.filter((s) => s.toLowerCase().includes(text.toLowerCase()) && !value.includes(s)).slice(0, 6)
    : [];
  return (
    <div className="relative">
      <div className={cn("flex min-h-10 flex-wrap items-center gap-1.5 rounded-lg border bg-bg px-2 py-1.5",
        error ? "border-danger/60" : "border-line focus-within:border-primary/60 focus-within:ring-2 focus-within:ring-primary/40")}>
        {value.map((v) => (
          <span key={v} className="ltr inline-flex items-center gap-1 rounded-md bg-primary/15 px-2 py-0.5 text-xs text-ink">
            {v}
            <button type="button" onClick={() => onChange(value.filter((x) => x !== v))} className="text-muted hover:text-danger">
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          value={text}
          onChange={(e) => { setText(e.target.value); setError(false); }}
          onKeyDown={onKey}
          onBlur={() => text.trim() && add(text)}
          placeholder={value.length ? "" : placeholder}
          className="ltr min-w-[160px] flex-1 bg-transparent text-sm outline-none placeholder:text-muted/60"
        />
      </div>
      {error && <p className="mt-1 text-xs text-danger">{t("errors.invalidEmail")}</p>}
      {matches.length > 0 && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-line bg-surface2 shadow-xl">
          {matches.map((m) => (
            <button key={m} type="button" onMouseDown={(e) => { e.preventDefault(); add(m); }}
              className="ltr block w-full px-3 py-2 text-start text-sm hover:bg-primary/15">
              {m}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function SegmentedTabs<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode; icon?: ReactNode }[];
}) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-bg p-1">
      {items.map((it) => (
        <button key={it.value} type="button" onClick={() => onChange(it.value)}
          className={cn("flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
            value === it.value ? "bg-surface2 text-ink shadow" : "text-muted hover:text-ink")}>
          {it.icon}
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function EmptyState({ icon, title, body, action }: { icon?: ReactNode; title: ReactNode; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line px-6 py-14 text-center">
      {icon && <div className="mb-4 text-primary">{icon}</div>}
      <div className="text-base font-semibold">{title}</div>
      {body && <p className="mt-1 max-w-md text-sm text-muted">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function StatusDot({ status }: { status: string }) {
  return (
    <span className={cn("inline-block h-2 w-2 rounded-full",
      status === "ok" || status === "sent" ? "bg-ok"
        : status === "warn" || status === "running" || status === "previewed" ? "bg-warn"
          : status === "error" || status === "failed" ? "bg-danger" : "bg-muted")} />
  );
}
