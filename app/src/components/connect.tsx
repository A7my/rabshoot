import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCircle2, Copy, Github, Gitlab, Mail, MessageSquare, Plus, Server } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import { copyText, openUrl } from "../lib/platform";
import type { Connection, ConnectionType } from "../lib/types";
import { cn } from "../lib/utils";
import { Alert, Badge, Button, Guide, Input, Label, LinkButton, SecretInput, Select, Spinner, StatusDot } from "./ui";

export const TYPE_ICON: Record<ConnectionType, typeof Mail> = {
  email: Mail, gitlab: Gitlab, github: Github, slack: MessageSquare, ai: Bot,
};

export function useConnections() {
  return useQuery({ queryKey: ["connections"], queryFn: api.connections });
}

export function useAuthLinks() {
  return useQuery({ queryKey: ["authLinks"], queryFn: () => api.authLinks(), staleTime: Infinity });
}

function useConnectedCallback(onConnected: (c: Connection) => void) {
  const qc = useQueryClient();
  return (c: Connection) => {
    qc.invalidateQueries({ queryKey: ["connections"] });
    onConnected(c);
  };
}

function ErrorLine({ error }: { error: string }) {
  return error ? <Alert kind="error">{error}</Alert> : null;
}

/* ------------------------------------------------------------------ email */

export function EmailConnect({ onConnected }: { onConnected: (c: Connection) => void }) {
  const { t } = useTranslation();
  const done = useConnectedCallback(onConnected);
  const { data: providers } = useQuery({ queryKey: ["providers"], queryFn: api.emailProviders, staleTime: Infinity });
  const [provider, setProvider] = useState("gmail");
  const [touchedProvider, setTouchedProvider] = useState(false);
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [adv, setAdv] = useState({ smtp_host: "", smtp_port: "", imap_host: "", imap_port: "", username: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");

  useEffect(() => {
    if (touchedProvider || !providers) return;
    const domain = address.split("@")[1]?.toLowerCase();
    if (!domain) return;
    const match = Object.entries(providers).find(([, p]) => p.domains.includes(domain));
    setProvider(match ? match[0] : domain.includes(".") ? "custom" : provider);
  }, [address, providers, touchedProvider]); // eslint-disable-line react-hooks/exhaustive-deps

  const preset = providers?.[provider];
  const steps = provider === "gmail" ? t("sender.gmail", { returnObjects: true })
    : provider === "outlook" ? t("sender.outlook", { returnObjects: true })
      : provider === "custom" ? t("sender.custom", { returnObjects: true })
        : t("sender.generic", { returnObjects: true });

  const submit = async () => {
    setBusy(true); setError(""); setWarning("");
    try {
      const meta: Record<string, unknown> = { provider, address: address.trim(), display_name: displayName.trim() };
      if (adv.smtp_host) meta.smtp_host = adv.smtp_host.trim();
      if (adv.smtp_port) meta.smtp_port = Number(adv.smtp_port);
      if (adv.imap_host) meta.imap_host = adv.imap_host.trim();
      if (adv.imap_port) meta.imap_port = Number(adv.imap_port);
      if (adv.username) meta.username = adv.username.trim();
      const secret = provider === "custom" ? password : password.replace(/\s+/g, "");
      const conn = await api.createConnection({ type: "email", meta, secret: { password: secret } });
      if (conn.meta.imap_ok === false) setWarning(t("sender.imapWarn"));
      done(conn);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label required>{t("sender.address")}</Label>
          <Input className="ltr" type="email" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="you@company.com" />
        </div>
        <div>
          <Label>{t("sender.provider")}</Label>
          <Select value={provider} onChange={(v) => { setProvider(v); setTouchedProvider(true); if (v === "custom") setAdvanced(true); }}
            options={Object.entries(providers ?? {}).map(([k, p]) => ({ value: k, label: p.label }))} />
        </div>
      </div>

      <Guide title={t("sender.guideTitle")} steps={steps as string[]}
        actions={preset?.app_password_url ? (
          <>
            {preset.two_factor_url && <LinkButton url={preset.two_factor_url} size="sm">{t("sender.open2fa")}</LinkButton>}
            <LinkButton url={preset.app_password_url} size="sm" variant="primary">{t("sender.openAppPasswords")}</LinkButton>
          </>
        ) : undefined} />
      {preset?.note && <Alert kind="warn">{preset.note}</Alert>}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label required>{t("sender.appPassword")}</Label>
          <SecretInput value={password} onChange={(e) => setPassword(e.target.value)} placeholder={t("sender.appPasswordPh")} />
        </div>
        <div>
          <Label>{t("sender.displayName")}</Label>
          <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Your name" />
        </div>
      </div>

      <button type="button" onClick={() => setAdvanced(!advanced)} className="text-xs text-primary hover:underline">
        {t("common.advanced")}
      </button>
      {advanced && (
        <div className="grid gap-3 rounded-lg border border-line p-4 sm:grid-cols-4">
          <div className="sm:col-span-3"><Label>{t("sender.smtpHost")}</Label>
            <Input className="ltr" value={adv.smtp_host} placeholder={preset?.smtp_host} onChange={(e) => setAdv({ ...adv, smtp_host: e.target.value })} /></div>
          <div><Label>{t("sender.smtpPort")}</Label>
            <Input className="ltr" value={adv.smtp_port} placeholder={String(preset?.smtp_port ?? 587)} onChange={(e) => setAdv({ ...adv, smtp_port: e.target.value })} /></div>
          <div className="sm:col-span-3"><Label>{t("sender.imapHost")}</Label>
            <Input className="ltr" value={adv.imap_host} placeholder={preset?.imap_host} onChange={(e) => setAdv({ ...adv, imap_host: e.target.value })} /></div>
          <div><Label>{t("sender.imapPort")}</Label>
            <Input className="ltr" value={adv.imap_port} placeholder={String(preset?.imap_port ?? 993)} onChange={(e) => setAdv({ ...adv, imap_port: e.target.value })} /></div>
          <div className="sm:col-span-4"><Label>{t("sender.username")}</Label>
            <Input className="ltr" value={adv.username} placeholder={address} onChange={(e) => setAdv({ ...adv, username: e.target.value })} /></div>
        </div>
      )}

      <ErrorLine error={error} />
      {warning && <Alert kind="warn">{warning}</Alert>}
      <Button variant="primary" loading={busy} disabled={!address.includes("@") || !password} onClick={submit}>
        {busy ? t("sender.testing") : t("common.connect")}
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------- code */

function TokenForm({ steps, pageUrl, placeholder, onSubmit }: {
  steps: string[]; pageUrl: string; placeholder: string; onSubmit: (token: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <div className="space-y-4">
      <Guide title={t("code.tokenTitle")} steps={steps}
        actions={<LinkButton url={pageUrl} size="sm" variant="primary">{t("common.openPage")}</LinkButton>} />
      <div>
        <Label required>{t("code.token")}</Label>
        <SecretInput value={token} onChange={(e) => setToken(e.target.value)} placeholder={placeholder} />
      </div>
      <ErrorLine error={error} />
      <Button variant="primary" loading={busy} disabled={!token.trim()} onClick={async () => {
        setBusy(true); setError("");
        try { await onSubmit(token.trim()); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
      }}>{t("common.connect")}</Button>
    </div>
  );
}

function GitHubDevice({ onDone, onFallback }: { onDone: (c: Connection) => void; onFallback: () => void }) {
  const { t } = useTranslation();
  const [flow, setFlow] = useState<{ flow_id: string; user_code: string; verification_uri: string; interval: number } | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const timer = useRef<number>();

  const start = async () => {
    setError("");
    try {
      const f = await api.githubStart();
      setFlow(f);
      await copyText(f.user_code).catch(() => undefined);
      openUrl(f.verification_uri);
    } catch (e: any) { setError(e.message); }
  };

  useEffect(() => {
    if (!flow) return;
    const tick = async () => {
      try {
        const r = await api.githubPoll(flow.flow_id);
        if (r.status === "done" && r.connection) return onDone(r.connection);
        if (r.status !== "pending") { setError(r.message || r.status); setFlow(null); return; }
      } catch (e: any) { setError(e.message); setFlow(null); return; }
      timer.current = window.setTimeout(tick, Math.max(flow.interval, 3) * 1000);
    };
    timer.current = window.setTimeout(tick, flow.interval * 1000);
    return () => window.clearTimeout(timer.current);
  }, [flow]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!flow) {
    return (
      <div className="space-y-3">
        <ErrorLine error={error} />
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={start} icon={<Github className="h-4 w-4" />}>{t("code.signIn")}</Button>
          <Button variant="ghost" onClick={onFallback}>{t("code.useToken")}</Button>
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-primary/40 bg-primary/10 p-5 text-center">
      <div className="text-sm font-medium">{t("code.deviceTitle")}</div>
      <div className="ltr my-4 font-mono text-3xl font-bold tracking-[0.3em] text-ink">{flow.user_code}</div>
      <div className="mb-4 flex justify-center gap-2">
        <Button size="sm" onClick={async () => { await copyText(flow.user_code); setCopied(true); }} icon={<Copy className="h-3.5 w-3.5" />}>
          {copied ? t("common.copied") : t("common.copy")}
        </Button>
        <LinkButton size="sm" url={flow.verification_uri}>{t("common.openPage")}</LinkButton>
      </div>
      <p className="mx-auto max-w-md text-xs text-muted">{t("code.deviceBody")}</p>
      <div className="mt-4 flex justify-center"><Spinner label={t("code.waiting")} /></div>
    </div>
  );
}

function GitLabOAuth({ baseUrl, onDone, onFallback }: { baseUrl: string; onDone: (c: Connection) => void; onFallback: () => void }) {
  const { t } = useTranslation();
  const [flowId, setFlowId] = useState<string | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!flowId) return;
    const id = window.setInterval(async () => {
      try {
        const r = await api.gitlabStatus(flowId);
        if (r.status === "done" && r.connection) { window.clearInterval(id); onDone(r.connection); }
        else if (r.status !== "pending") { window.clearInterval(id); setError(r.message || r.status); setFlowId(null); }
      } catch (e: any) { window.clearInterval(id); setError(e.message); setFlowId(null); }
    }, 2000);
    return () => window.clearInterval(id);
  }, [flowId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (flowId) return <div className="rounded-xl border border-primary/40 bg-primary/10 p-5"><Spinner label={t("code.oauthWaiting")} /></div>;
  return (
    <div className="space-y-3">
      <ErrorLine error={error} />
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" icon={<Gitlab className="h-4 w-4" />} onClick={async () => {
          setError("");
          try { const f = await api.gitlabStart(baseUrl); setFlowId(f.flow_id); openUrl(f.authorize_url); }
          catch (e: any) { setError(e.message); }
        }}>{t("code.signIn")}</Button>
        <Button variant="ghost" onClick={onFallback}>{t("code.useToken")}</Button>
      </div>
    </div>
  );
}

type CodeKind = "github" | "gitlab" | "selfhosted";

export function CodeConnect({ onConnected }: { onConnected: (c: Connection) => void }) {
  const { t } = useTranslation();
  const done = useConnectedCallback(onConnected);
  const { data: links } = useAuthLinks();
  const [kind, setKind] = useState<CodeKind | null>(null);
  const [useToken, setUseToken] = useState(false);
  const [serverUrl, setServerUrl] = useState("https://");

  const options: { key: CodeKind; icon: ReactNode; title: string; hint: string }[] = [
    { key: "github", icon: <Github className="h-6 w-6" />, title: t("code.github"), hint: t("code.githubHint") },
    { key: "gitlab", icon: <Gitlab className="h-6 w-6 text-[#FC6D26]" />, title: t("code.gitlab"), hint: t("code.gitlabHint") },
    { key: "selfhosted", icon: <Server className="h-6 w-6 text-ok" />, title: t("code.selfHosted"), hint: t("code.selfHostedHint") },
  ];
  const cleanUrl = serverUrl.trim().replace(/\/+$/, "");
  const createCode = async (type: "github" | "gitlab", token: string, url?: string) => {
    const conn = await api.createConnection({ type, meta: type === "gitlab" ? { url: url || "https://gitlab.com", auth: "pat" } : { auth: "pat" }, secret: { token } });
    done(conn);
    setKind(null);
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {options.map((o) => (
          <button key={o.key} type="button" onClick={() => { setKind(o.key); setUseToken(false); }}
            className={cn("rounded-xl border p-4 text-start transition-all hover:border-primary/60",
              kind === o.key ? "border-primary bg-primary/10 shadow-glow" : "border-line bg-surface2")}>
            {o.icon}
            <div className="mt-3 font-semibold">{o.title}</div>
            <div className="text-xs text-muted">{o.hint}</div>
          </button>
        ))}
      </div>

      {kind === "github" && links && (
        links.github_device && !useToken
          ? <GitHubDevice onDone={(c) => { done(c); setKind(null); }} onFallback={() => setUseToken(true)} />
          : <>
            {!links.github_device && <Alert kind="info">{t("code.oauthUnavailable")}</Alert>}
            <TokenForm steps={t("code.githubTokenSteps", { returnObjects: true }) as string[]} pageUrl={links.github_token_page}
              placeholder="ghp_…" onSubmit={(tok) => createCode("github", tok)} />
          </>
      )}
      {kind === "gitlab" && links && (
        links.gitlab_oauth && !useToken
          ? <GitLabOAuth baseUrl="https://gitlab.com" onDone={(c) => { done(c); setKind(null); }} onFallback={() => setUseToken(true)} />
          : <>
            {!links.gitlab_oauth && <Alert kind="info">{t("code.oauthUnavailable")}</Alert>}
            <TokenForm steps={t("code.gitlabTokenSteps", { returnObjects: true }) as string[]} pageUrl={links.gitlab_token_page}
              placeholder="glpat-…" onSubmit={(tok) => createCode("gitlab", tok, "https://gitlab.com")} />
          </>
      )}
      {kind === "selfhosted" && (
        <div className="space-y-4">
          <div>
            <Label required>{t("code.serverUrl")}</Label>
            <Input className="ltr" value={serverUrl} onChange={(e) => setServerUrl(e.target.value)} placeholder="https://gitlab.company.com" />
          </div>
          {/^https?:\/\/[^/]+\.[^/]+/.test(cleanUrl) && (
            <TokenForm steps={t("code.gitlabTokenSteps", { returnObjects: true }) as string[]}
              pageUrl={`${cleanUrl}/-/user_settings/personal_access_tokens?name=RabShoot&scopes=read_api,read_user`}
              placeholder="glpat-…" onSubmit={(tok) => createCode("gitlab", tok, cleanUrl)} />
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ slack */

const SLACK_CLIENT_ID = /^\d{5,}\.\d{5,}$/;

function CopyButton({ text, label }: { text: string; label?: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <Button size="sm" icon={<Copy className="h-3.5 w-3.5" />}
      onClick={async (e) => { e.stopPropagation(); await copyText(text); setCopied(true); window.setTimeout(() => setCopied(false), 2000); }}>
      {copied ? t("common.copied") : label || t("common.copy")}
    </Button>
  );
}

function SlackSignIn({ onDone }: { onDone: (c: Connection) => void }) {
  const { t } = useTranslation();
  const { data: connections } = useConnections();
  const known = connections?.find((c) => c.type === "slack" && c.meta.client_id)?.meta.client_id as string | undefined;
  const [code, setCode] = useState("");
  const [flowId, setFlowId] = useState<string | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (!code && known) setCode(known); }, [known]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!flowId) return;
    const id = window.setInterval(async () => {
      try {
        const r = await api.slackStatus(flowId);
        if (r.status === "done" && r.connection) { window.clearInterval(id); onDone(r.connection); }
        else if (r.status !== "pending") { window.clearInterval(id); setError(r.message || r.status); setFlowId(null); }
      } catch (e: any) { window.clearInterval(id); setError(e.message); setFlowId(null); }
    }, 2000);
    return () => window.clearInterval(id);
  }, [flowId]); // eslint-disable-line react-hooks/exhaustive-deps

  const clean = code.trim();
  if (flowId) {
    return (
      <div className="space-y-3 rounded-xl border border-primary/40 bg-primary/10 p-5">
        <Spinner label={t("slack.waiting")} />
        <Button variant="ghost" size="sm" onClick={() => setFlowId(null)}>{t("common.cancel")}</Button>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div>
        <Label required>{t("slack.teamCode")}</Label>
        <Input className="ltr font-mono" value={code} onChange={(e) => setCode(e.target.value)} placeholder="1234567890123.1234567890123" />
        <p className="mt-1 text-xs text-muted">{t("slack.teamCodeHint")}</p>
      </div>
      {clean && !SLACK_CLIENT_ID.test(clean) && <Alert kind="warn">{t("slack.teamCodeInvalid")}</Alert>}
      <ErrorLine error={error} />
      <Button variant="primary" disabled={!SLACK_CLIENT_ID.test(clean)} icon={<MessageSquare className="h-4 w-4" />} onClick={async () => {
        setError("");
        try { const f = await api.slackStart(clean); setFlowId(f.flow_id); openUrl(f.authorize_url); }
        catch (e: any) { setError(e.message); }
      }}>{t("slack.signIn")}</Button>
    </div>
  );
}

function SlackTokenForm({ onDone }: { onDone: (c: Connection) => void }) {
  const { t } = useTranslation();
  const { data: links } = useAuthLinks();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <div className="space-y-4">
      <Guide title={t("slack.tokenTitle")} steps={t("slack.tokenSteps", { returnObjects: true }) as string[]}
        actions={links && <LinkButton url={links.slack_manifest_url} size="sm">{t("slack.createApp")}</LinkButton>} />
      <div>
        <Label required>{t("slack.token")}</Label>
        <SecretInput value={token} onChange={(e) => setToken(e.target.value)} placeholder={t("slack.tokenPh")} />
      </div>
      <ErrorLine error={error} />
      <Button variant="primary" loading={busy} disabled={!/^xox[pb]-/.test(token.trim())} onClick={async () => {
        setBusy(true); setError("");
        try { onDone(await api.createConnection({ type: "slack", secret: { token: token.trim() } })); setToken(""); }
        catch (e: any) { setError(e.message); } finally { setBusy(false); }
      }}>{t("common.connect")}</Button>
    </div>
  );
}

type SlackPath = "join" | "first" | "token";

export function SlackConnect({ onConnected }: { onConnected: (c: Connection) => void }) {
  const { t } = useTranslation();
  const done = useConnectedCallback(onConnected);
  const { data: links } = useAuthLinks();
  const [path, setPath] = useState<SlackPath>("join");
  const choices: { key: SlackPath; title: string; hint: string }[] = [
    { key: "join", title: t("slack.joinTitle"), hint: t("slack.joinHint") },
    { key: "first", title: t("slack.firstTitle"), hint: t("slack.firstHint") },
  ];
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        {choices.map((c) => (
          <button key={c.key} type="button" onClick={() => setPath(c.key)}
            className={cn("rounded-xl border p-4 text-start transition-all hover:border-primary/60",
              path === c.key ? "border-primary bg-primary/10 shadow-glow" : "border-line bg-surface2")}>
            <div className="font-semibold">{c.title}</div>
            <div className="text-xs text-muted">{c.hint}</div>
          </button>
        ))}
      </div>

      {path === "first" && links && (
        <>
          <Guide title={t("slack.guideTitle")} steps={t("slack.steps", { returnObjects: true }) as string[]}
            actions={<>
              <LinkButton url={links.slack_manifest_url} variant="primary" size="sm">{t("slack.createApp")}</LinkButton>
              <CopyButton text={JSON.stringify(links.slack_manifest, null, 2)} label={t("slack.copyManifest")} />
            </>} />
          <Alert kind="info">
            <div>{t("slack.existingApp")}</div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <code className="ltr rounded bg-surface2 px-2 py-1 text-xs">{links.slack_redirect_url}</code>
              <CopyButton text={links.slack_redirect_url} />
            </div>
          </Alert>
        </>
      )}
      {path !== "token" && <SlackSignIn onDone={done} />}
      {path !== "token" && <Alert kind="info">{t("slack.privateNote")}</Alert>}
      {path === "first" && <Alert kind="warn">{t("slack.limitNote")}</Alert>}

      {path === "token"
        ? <>
          <SlackTokenForm onDone={done} />
          <button type="button" onClick={() => setPath("join")} className="text-xs text-primary hover:underline">{t("slack.backToSignIn")}</button>
        </>
        : <button type="button" onClick={() => setPath("token")} className="text-xs text-primary hover:underline">{t("slack.useToken")}</button>}
    </div>
  );
}

/* --------------------------------------------------------------------- ai */

export function AIConnect({ onConnected }: { onConnected: (c: Connection) => void }) {
  const { t } = useTranslation();
  const done = useConnectedCallback(onConnected);
  const { data: links } = useAuthLinks();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <div className="space-y-4">
      <Guide steps={t("ai.steps", { returnObjects: true }) as string[]}
        actions={<LinkButton url={links?.ai_key_page || "https://aistudio.google.com/apikey"} variant="primary" size="sm">{t("ai.openStudio")}</LinkButton>} />
      <div>
        <Label required>{t("ai.key")}</Label>
        <SecretInput value={key} onChange={(e) => setKey(e.target.value)} placeholder={t("ai.keyPh")} />
      </div>
      <Alert kind="warn">{t("ai.privacy")}</Alert>
      <ErrorLine error={error} />
      <Button variant="primary" loading={busy} disabled={key.trim().length < 10} onClick={async () => {
        setBusy(true); setError("");
        try { done(await api.createConnection({ type: "ai", meta: { provider: "gemini" }, secret: { key: key.trim() } })); setKey(""); }
        catch (e: any) { setError(e.message); } finally { setBusy(false); }
      }}>{busy ? t("ai.testing") : t("common.connect")}</Button>
    </div>
  );
}

/* ---------------------------------------------------------------- picker */

export function ConnectForm({ type, onConnected }: { type: ConnectionType; onConnected: (c: Connection) => void }) {
  if (type === "email") return <EmailConnect onConnected={onConnected} />;
  if (type === "slack") return <SlackConnect onConnected={onConnected} />;
  if (type === "ai") return <AIConnect onConnected={onConnected} />;
  return <CodeConnect onConnected={onConnected} />;
}

export function ConnectionRow({ conn, selected, onClick, right }: { conn: Connection; selected?: boolean; onClick?: () => void; right?: ReactNode }) {
  const { t } = useTranslation();
  const Icon = TYPE_ICON[conn.type];
  return (
    <div onClick={onClick}
      className={cn("flex items-center gap-3 rounded-lg border p-3 transition-colors",
        onClick && "cursor-pointer hover:border-primary/60",
        selected ? "border-primary bg-primary/10" : "border-line bg-surface2")}>
      <Icon className="h-5 w-5 shrink-0 text-primary" />
      <div className="min-w-0 flex-1">
        <div className="ltr truncate text-start text-sm font-medium">{conn.label || conn.type}</div>
        <div className="flex items-center gap-1.5 truncate text-xs text-muted">
          <StatusDot status={conn.status} />
          {conn.status_message || t(`status.${conn.status}`)}
        </div>
        {conn.type === "slack" && conn.meta.client_id && (
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
            <span>{t("slack.shareCode")}</span>
            <code className="ltr font-mono text-ink">{conn.meta.client_id}</code>
            <CopyButton text={conn.meta.client_id} />
          </div>
        )}
      </div>
      {selected && <CheckCircle2 className="h-5 w-5 shrink-0 text-primary" />}
      {right}
    </div>
  );
}

/** Pick one saved connection of a type, or connect a new one inline. */
export function ConnectionPicker({ type, value, onChange }: { type: "email" | "slack" | "ai"; value: string | null; onChange: (id: string) => void }) {
  const { t } = useTranslation();
  const { data: connections, isLoading } = useConnections();
  const items = (connections ?? []).filter((c) => c.type === type);
  const [adding, setAdding] = useState(false);
  useEffect(() => { if (!isLoading && items.length === 0) setAdding(true); }, [isLoading, items.length]);
  useEffect(() => {
    if (!value && items.length === 1 && !adding) onChange(items[0].id);
  }, [items.length]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) return <Spinner label={t("common.loading")} />;
  return (
    <div className="space-y-3">
      {items.length > 0 && (
        <div className="space-y-2">
          {items.map((c) => <ConnectionRow key={c.id} conn={c} selected={c.id === value} onClick={() => { onChange(c.id); setAdding(false); }} />)}
        </div>
      )}
      {items.length > 0 && !adding && (
        <Button variant="ghost" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>{t("common.addNew")}</Button>
      )}
      {adding && (
        <div className={cn(items.length > 0 && "rounded-xl border border-line p-4")}>
          <ConnectForm type={type} onConnected={(c) => { onChange(c.id); setAdding(false); }} />
        </div>
      )}
    </div>
  );
}

export function ConnectionBadge({ conn }: { conn?: Connection }) {
  const { t } = useTranslation();
  if (!conn) return null;
  return <Badge tone={conn.status === "ok" ? "ok" : conn.status === "error" ? "error" : "muted"}>{t(`status.${conn.status}`)}</Badge>;
}
