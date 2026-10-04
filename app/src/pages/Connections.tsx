import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, RefreshCw, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ConnectForm, ConnectionRow, DeleteConnectionButton, useConnections } from "../components/connect";
import { Alert, Button, Card, EmptyState, Label, PageHeader, SecretInput, Spinner } from "../components/ui";
import { api } from "../lib/api";
import type { Connection, ConnectionType } from "../lib/types";
import { cn } from "../lib/utils";

const TYPES: ConnectionType[] = ["email", "github", "gitlab", "slack", "ai"];
const SECRET_FIELD: Record<ConnectionType, string> = { email: "password", gitlab: "token", github: "token", slack: "token", ai: "key" };

export function Connections() {
  const { t } = useTranslation();
  const { data: connections, isLoading } = useConnections();
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const [adding, setAdding] = useState<ConnectionType | null>(null);

  return (
    <div>
      <PageHeader title={t("connections.title")} subtitle={t("connections.intro")} />
      {health && !health.secrets_secure && <div className="mb-5"><Alert kind="warn">{t("connections.fileWarning")}</Alert></div>}

      <Card className="mb-6">
        <div className="mb-3 text-sm font-semibold">{t("connections.add")}</div>
        <div className="flex flex-wrap gap-2">
          {TYPES.map((type) => (
            <button key={type} onClick={() => setAdding(adding === type ? null : type)}
              className={cn("flex items-center gap-2 rounded-lg border px-3 py-2 text-sm",
                adding === type ? "border-primary bg-primary/15" : "border-line bg-surface2 text-muted hover:text-ink")}>
              <Plus className="h-4 w-4" />{t(`connections.types.${type}`)}
            </button>
          ))}
        </div>
        {adding && (
          <div className="mt-5 border-t border-line pt-5">
            <ConnectForm type={adding} onConnected={() => setAdding(null)} />
          </div>
        )}
      </Card>

      {isLoading ? <Spinner label={t("common.loading")} /> : !connections?.length ? (
        <EmptyState icon={<KeyRound className="h-10 w-10" />} title={t("connections.title")} body={t("connections.intro")} />
      ) : (
        <div className="space-y-6">
          {TYPES.map((type) => {
            const items = connections.filter((c) => c.type === type);
            if (!items.length) return null;
            return (
              <section key={type}>
                <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{t(`connections.types.${type}`)}</h2>
                <div className="space-y-2">{items.map((c) => <ConnectionItem key={c.id} conn={c} />)}</div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ConnectionItem({ conn }: { conn: Connection }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<"test" | "save" | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [editing, setEditing] = useState(false);
  const [secret, setSecret] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["connections"] });

  const test = async () => {
    setBusy("test"); setMessage(null);
    try {
      const r = await api.testConnection(conn.id);
      setMessage({ kind: r.ok ? "ok" : "error", text: r.message });
      refresh();
    } catch (e: any) { setMessage({ kind: "error", text: e.message }); } finally { setBusy(null); }
  };
  const saveSecret = async () => {
    setBusy("save"); setMessage(null);
    try {
      let value = secret.trim();
      if (conn.type === "email" && conn.meta.provider !== "custom") value = value.replace(/\s+/g, "");
      await api.updateConnection(conn.id, { secret: { [SECRET_FIELD[conn.type]]: value } });
      setMessage({ kind: "ok", text: t("connections.tested") });
      setEditing(false); setSecret(""); refresh();
    } catch (e: any) { setMessage({ kind: "error", text: e.message }); } finally { setBusy(null); }
  };

  const oauth = conn.meta.auth === "device" || conn.meta.auth === "oauth";
  return (
    <div className="space-y-2">
      <ConnectionRow conn={conn} right={
        <div className="flex shrink-0 gap-1">
          <Button variant="ghost" size="sm" loading={busy === "test"} icon={<RefreshCw className="h-4 w-4" />} onClick={test}>{t("common.test")}</Button>
          {!oauth && <Button variant="ghost" size="sm" onClick={() => setEditing(!editing)}>{editing ? <X className="h-4 w-4" /> : t("common.edit")}</Button>}
          <DeleteConnectionButton conn={conn} />
        </div>} />
      {editing && (
        <div className="flex items-end gap-2 ps-8">
          <div className="flex-1"><Label>{t("connections.updateSecret")}</Label>
            <SecretInput value={secret} onChange={(e) => setSecret(e.target.value)} /></div>
          <Button variant="primary" loading={busy === "save"} disabled={!secret.trim()} onClick={saveSecret}>{t("common.save")}</Button>
        </div>
      )}
      {message && <div className="ps-8"><Alert kind={message.kind}>{message.text}</Alert></div>}
    </div>
  );
}
