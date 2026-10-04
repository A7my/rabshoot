import { engineInfo } from "./platform";
import type {
  AuthLinks, CodeProject, Connection, ConnectionType, Contact, EmailProvider, Health, MailThread,
  Profile, ProfileView, Run, RunProgress, RunResult, Settings, SlackConversation,
} from "./types";

let enginePromise: Promise<{ url: string; token: string }> | null = null;

function engine() {
  if (!enginePromise) {
    enginePromise = engineInfo().catch((err) => {
      enginePromise = null;
      throw err;
    });
  }
  return enginePromise;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const { url, token } = await engine();
  let resp: Response;
  try {
    resp = await fetch(url + path, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    // The engine may have restarted on a new port; ask the shell again next time.
    enginePromise = null;
    throw new ApiError(0, "engine_unreachable");
  }
  if (!resp.ok) {
    let message = resp.statusText;
    try {
      const data = await resp.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail))
        message = data.detail.map((d: any) => d.msg?.replace(/^Value error, /, "")).join("; ");
    } catch {
      /* not JSON */
    }
    throw new ApiError(resp.status, message);
  }
  return resp.json() as Promise<T>;
}

const q = (params: Record<string, string | undefined>) => {
  const s = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "") as [string, string][],
  ).toString();
  return s ? `?${s}` : "";
};

export const api = {
  health: () => request<Health>("GET", "/health"),
  settings: () => request<Settings>("GET", "/settings"),
  saveSettings: (s: Settings) => request<Settings>("PUT", "/settings", s),

  connections: () => request<Connection[]>("GET", "/connections"),
  createConnection: (body: { type: ConnectionType; label?: string; meta?: object; secret?: object }) =>
    request<Connection & { test: { ok: boolean; message: string } }>("POST", "/connections", body),
  updateConnection: (id: string, body: { label?: string; meta?: object; secret?: object }) =>
    request<Connection>("PUT", `/connections/${id}`, body),
  deleteConnection: (id: string) => request<{ ok: true }>("DELETE", `/connections/${id}`),
  testConnection: (id: string) =>
    request<{ ok: boolean; message: string }>("POST", `/connections/${id}/test`),

  authLinks: (gitlabUrl?: string) => request<AuthLinks>("GET", `/auth/links${q({ gitlab_url: gitlabUrl })}`),
  githubStart: () =>
    request<{ flow_id: string; user_code: string; verification_uri: string; interval: number; expires_in: number }>(
      "POST", "/auth/github/device/start"),
  githubPoll: (flowId: string) =>
    request<{ status: string; message?: string; connection?: Connection }>(
      "GET", `/auth/github/device/poll${q({ flow_id: flowId })}`),
  gitlabStart: (baseUrl: string) =>
    request<{ flow_id: string; authorize_url: string }>("POST", "/auth/gitlab/oauth/start", { base_url: baseUrl }),
  gitlabStatus: (flowId: string) =>
    request<{ status: string; message?: string; connection?: Connection }>(
      "GET", `/auth/gitlab/oauth/status${q({ flow_id: flowId })}`),
  slackStart: (clientId: string) =>
    request<{ flow_id: string; authorize_url: string }>("POST", "/auth/slack/oauth/start", { client_id: clientId }),
  slackStatus: (flowId: string) =>
    request<{ status: string; message?: string; connection?: Connection }>(
      "GET", `/auth/slack/oauth/status${q({ flow_id: flowId })}`),

  emailProviders: () => request<Record<string, EmailProvider>>("GET", "/email/providers"),
  emailThreads: (connId: string, query = "") =>
    request<MailThread[]>("GET", `/email/${connId}/threads${q({ q: query })}`),
  emailContacts: (connId: string, query = "") =>
    request<Contact[]>("GET", `/email/${connId}/contacts${q({ q: query })}`),
  slackConversations: (connId: string) =>
    request<SlackConversation[]>("GET", `/slack/${connId}/conversations`),
  codeProjects: (connId: string) => request<CodeProject[]>("GET", `/code/${connId}/projects`),

  profiles: () => request<ProfileView[]>("GET", "/profiles"),
  profile: (id: string) => request<ProfileView>("GET", `/profiles/${id}`),
  createProfile: (p: Partial<Profile>) => request<Profile>("POST", "/profiles", p),
  updateProfile: (p: Profile) => request<Profile>("PUT", `/profiles/${p.id}`, p),
  deleteProfile: (id: string) => request<{ ok: true }>("DELETE", `/profiles/${id}`),
  preview: (id: string, day?: string) => request<RunResult>("POST", `/profiles/${id}/preview`, { day }),
  testSend: (id: string, to?: string, day?: string) => request<RunResult>("POST", `/profiles/${id}/test-send`, { to, day }),
  sendNow: (id: string, day?: string) =>
    request<{ started: boolean }>("POST", `/profiles/${id}/send`, day ? { day } : {}),
  progress: (id: string) =>
    request<{ running: boolean; progress: RunProgress | null }>("GET", `/profiles/${id}/progress`),

  runs: (profileId?: string, limit = 100) =>
    request<Run[]>("GET", `/runs${q({ profile_id: profileId, limit: String(limit) })}`),
  run: (id: string) => request<Run>("GET", `/runs/${id}`),
};
