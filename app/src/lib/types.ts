export type ConnectionType = "email" | "gitlab" | "github" | "slack" | "ai";

export interface Connection {
  id: string;
  type: ConnectionType;
  label: string;
  meta: Record<string, any>;
  created_at: string;
  status: "ok" | "error" | "unknown";
  status_message: string;
}

export interface ThreadRef {
  subject: string;
  message_id: string;
  gm_thrid: string;
  participants: string[];
}

export interface Delivery {
  mode: "recipients" | "thread";
  to: string[];
  cc: string[];
  bcc: string[];
  thread: ThreadRef | null;
  reply_all: boolean;
  subject: string;
  sender_name: string;
}

export interface CodeSource {
  connection_id: string;
  projects: "all" | string[];
  exclude: string[];
  authors: string[];
  include_merge_commits: boolean;
}

export interface ConversationRef {
  id: string;
  name: string;
}

export interface SlackSelection {
  connection_id: string | null;
  conversations: ConversationRef[];
  ignore_messages: string[];
  ignore_leftover_words: number;
  thread_lookback_days: number;
  include_bots: boolean;
}

export type ScheduleMode = "recurring" | "once" | "now";

export interface Schedule {
  mode: ScheduleMode;
  time: string;
  days: string;
  once_date: string | null;
  timezone: string;
  catch_up: boolean;
  skip_empty: boolean;
}

export interface Sections {
  code_changes: boolean;
  commits: boolean;
  merge_requests: boolean;
  issues: boolean;
  slack: boolean;
}

export interface ReportOptions {
  title: string;
  language: string;
  extra_instructions: string;
  max_points: number;
  max_diff_chars_per_project: number;
  max_items_per_section: number;
  sections: Sections;
  branding: boolean;
}

export interface Profile {
  id: string;
  name: string;
  enabled: boolean;
  sender_connection_id: string | null;
  delivery: Delivery;
  code_sources: CodeSource[];
  slack: SlackSelection;
  ai_connection_id: string | null;
  schedule: Schedule;
  report: ReportOptions;
  created_at?: string;
  updated_at?: string;
}

export type Problem = "sender" | "recipients" | "thread" | "code_source" | "slack" | "ai";

export interface Step {
  key: "code" | "slack" | "ai" | "email";
  status: "ok" | "warn" | "error" | "skipped";
  message: string;
  source?: string;
  model?: string;
}

export interface Run {
  id: string;
  profile_id: string;
  profile_name: string;
  trigger: "schedule" | "catch_up" | "manual" | "test" | "preview";
  report_day: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "sent" | "previewed" | "skipped" | "failed";
  error: string | null;
  subject: string | null;
  recipients: string[];
  steps: Step[];
  html?: string;
}

export type RunStage = "prepare" | "code" | "slack" | "ai" | "render" | "email";

export interface RunProgress {
  run_id: string;
  trigger: Run["trigger"];
  sending: boolean;
  stage: RunStage;
  percent: number;
  current: number;
  total: number;
  item: string;
  status: "running" | "sent" | "previewed" | "skipped" | "failed";
  error: string;
  started_at: string;
  finished_at: string | null;
  steps: Step[];
}

export interface SkippedRun {
  at: string;
  sent_at: string;
  run_id: string;
}

export interface ProfileView extends Profile {
  problems: Problem[];
  next_run: string | null;
  skipped_run: SkippedRun | null;
  last_run: Run | null;
  running: boolean;
  progress: RunProgress | null;
}

export interface RunResult {
  status: string;
  steps: Step[];
  subject: string;
  recipients: string[];
  error: string;
  run_id: string;
  html?: string;
  text?: string;
  stats?: Record<string, number>;
  draft?: { id: string; content: DraftContent };
}

export interface DraftContent {
  subject: string;
  body: string;
}

export interface DraftView {
  html: string;
  subject: string;
  stats: Record<string, number>;
}

export interface Settings {
  language: "en" | "ar";
  autostart: boolean;
  catch_up_default: boolean;
  onboarding_done: boolean;
  paused: boolean;
  notifications: boolean;
}

export interface Health {
  ok: boolean;
  version: string;
  secrets_backend: "keychain" | "file";
  secrets_secure: boolean;
  oauth: { github_device: boolean; github_app_install_url: string; gitlab_oauth: boolean };
  paths: { config: string; data: string; logs: string };
}

export interface EmailProvider {
  label: string;
  smtp_host: string;
  smtp_port: number;
  imap_host: string;
  imap_port: number;
  app_password_url?: string;
  two_factor_url?: string;
  domains: string[];
  note?: string;
}

export interface MailThread {
  key: string;
  subject: string;
  message_id: string;
  gm_thrid: string;
  count: number;
  last_date: string | null;
  participants: string[];
  last_from: string;
}

export interface Contact {
  email: string;
  count: number;
}

export interface CodeProject {
  id: string;
  name: string;
  url: string;
  last_activity_at: string | null;
  private?: boolean;
}

export interface SlackConversation {
  id: string;
  name: string;
  kind: "channel" | "private" | "group" | "dm";
  members?: number;
}

export interface AuthLinks {
  github_token_page: string;
  gitlab_token_page: string;
  slack_manifest_url: string;
  slack_manifest: Record<string, unknown>;
  slack_redirect_url: string;
  ai_key_page: string;
  github_device: boolean;
  github_app_install_url: string;
  gitlab_oauth: boolean;
}
