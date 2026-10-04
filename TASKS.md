# RabShoot — Desktop App Plan

> **Collect • Combine • Send** — a Windows/Linux desktop app that collects the day's work from
> GitLab/GitHub and Slack, summarizes it with AI in clear English, and emails it on a schedule.

This file is the source of truth for what will be built. Nothing here is implemented yet except
what is marked **(exists)**, which comes from the current `daily_report` Python prototype.

---

## 1. Decisions

| Topic | Decision |
|---|---|
| Platforms | Windows 10/11, Linux (Ubuntu 22.04+ and similar). macOS out of scope for v1. |
| UI | **Tauri 2 + React + TypeScript + Vite + Tailwind + shadcn/ui** |
| Engine | **Existing Python code** refactored into `rabshoot-engine`, shipped as a Tauri **sidecar** binary (PyInstaller). No rewrite. |
| UI ↔ engine | Local HTTP API (FastAPI) on `127.0.0.1`, random port, per-launch auth token. |
| Email (v1) | SMTP/IMAP with **App Password** (guided) — presets for Gmail, Outlook/365, Yahoo, custom SMTP. Google OAuth is v2 (needs Google restricted-scope verification). |
| Recipients | **Required**: explicit To/CC/BCC **or** reply-all inside an existing thread (picked from a list). |
| Code sources | **At least one required**: GitLab (gitlab.com or self-hosted) and/or GitHub. |
| Slack | **Optional.** Any workspace. **One shared app per workspace** (created once from a pre-filled manifest, PKCE on, redirect `http://127.0.0.1:47114/slack/callback`). Teammates paste its Client ID ("team code") and sign in with PKCE (no client secret, user scopes only), so the free-plan 10-app limit is hit once at most. Pasting an `xoxp-` token stays as an advanced fallback. Marketplace app is v2. |
| AI | **Required.** Google Gemini key from Google AI Studio (OpenAI-compatible API, fallback models) **(exists)**. |
| UI language | **Arabic + English**, full RTL support. Reports themselves are always English (configurable). |
| Reports | **Multiple profiles**: each with its own sender, recipients/thread, sources, Slack chats, schedule. |
| Secrets | OS keychain (Windows Credential Manager / Linux Secret Service), never plain files. |
| Background | Tray app, autostart at login, runs missed reports on next launch (optional). |

---

## 2. Architecture

```
┌──────────────────────────── RabShoot (Tauri) ────────────────────────────┐
│  React UI (wizard, dashboard, profiles, connections, history, settings)  │
│        │ fetch() with bearer token                                       │
│        ▼                                                                  │
│  rabshoot-engine (Python sidecar, FastAPI on 127.0.0.1:<random>)          │
│    ├─ connections/   gitlab · github · slack · email(smtp/imap) · ai      │
│    ├─ collectors/    commits+diffs · MRs/PRs · issues · slack threads     │
│    ├─ ai/            summaries, small-talk filter, English output         │
│    ├─ render/        HTML email (branded) + text                          │
│    ├─ delivery/      smtp send, thread reply-all                          │
│    ├─ scheduler/     APScheduler, one job per profile, catch-up           │
│    └─ storage/       config dir (JSON) · SQLite run history · keyring     │
│  Rust shell: spawn/stop sidecar, tray, autostart, single instance,        │
│              native notifications, open external links                    │
└──────────────────────────────────────────────────────────────────────────┘
```

Data locations:
- Windows: `%APPDATA%\RabShoot\` · Linux: `~/.config/rabshoot/` (config) and `~/.local/share/rabshoot/` (history, logs, saved reports)

### Data model

- **Connection** — an authenticated account, reusable across profiles.
  `{id, type: email|gitlab|github|slack|ai, label, meta (host, username, workspace…)}`;
  secret stored in keyring under `rabshoot/<connection_id>`.
- **Profile** (a report) —
  `{id, name, enabled, sender_connection, delivery: {mode: recipients|thread, to[], cc[], bcc[], thread_ref},
    code_sources: [{connection, projects: all|[ids], exclude[]}], slack: {connection?, conversations[]},
    ai_connection, schedule: {mode: recurring|once|now, time, days, once_date, timezone, catch_up, skip_empty}, report: {title, language, sections, extra_instructions}}`
- **Run** — `{id, profile_id, started_at, status, error?, subject, recipients, html_path}`

---

## 3. First-run wizard

Every step has: a short explanation, a visual guide (screenshots/illustration), a primary action
button that opens the right page, a **Test** button, and clear error messages. Steps can be revisited
later from Settings. Required steps block "Next" until validated.

| # | Step | Required | How it connects |
|---|---|---|---|
| 0 | Welcome + language (AR/EN) | — | — |
| 1 | **Sender email** | ✅ | Pick provider → guided App Password (button opens Google/Microsoft page, 2-Step Verification check-list) → Test SMTP + IMAP login |
| 2 | **Recipients or Thread** | ✅ | Tab A: To/CC/BCC chips with autocomplete from recent correspondents (IMAP). Tab B: list of recent threads from the sender mailbox (search), pick one → preview who will receive the reply-all |
| 3 | **Code sources** | ✅ (≥1) | **GitHub**: Device Flow (show code, open github.com/login/device, auto-detect success). **GitLab.com**: OAuth + PKCE via loopback redirect. **Self-hosted GitLab**: enter URL → button opens pre-filled token page (`?name=RabShoot&scopes=read_api`) → paste. Then pick projects: "all active" or checklist |
| 4 | **Slack** | ❌ (Skip) | Button opens `api.slack.com/apps?new_app=1&manifest_json=…` pre-filled → user picks workspace → Create → Install → paste User OAuth Token. Explain the free-plan 10-app limit and what to do. Then checklist of channels / DMs / group chats with search |
| 5 | **AI key** | ✅ | Button opens aistudio.google.com/apikey → paste → Test (tries fallback models). Privacy note about the free tier |
| 6 | **Schedule** | ✅ | Mode: repeating (time + days: Sun–Thu, Mon–Fri, every day, custom), one time (date + time), or send now (no schedule; sent when the wizard finishes). Timezone auto-detected. Quiet days (no code/Slack activity) skip scheduled sends unless turned off. Any past day can be previewed or sent from the dashboard |
| 7 | **Preview & test send** | — | Build today's report, show the email preview, "Send test to me", finish |

---

## 4. Tasks

Legend: `[ ]` todo · effort in ideal dev-days (rough).

### Phase 0 — Repository & engine refactor (≈3d)
- [ ] Monorepo layout: `app/` (Tauri + React), `engine/` (Python package `rabshoot_engine`), `assets/`, `.github/workflows/`
- [ ] Move `daily_report/*` into `engine/rabshoot_engine/` **(exists → refactor)**
- [ ] Replace `config.yaml` + `.env` with JSON storage: `connections.json`, `profiles/*.json`, `settings.json`
- [ ] Keyring layer (`keyring` lib) with fallback to an encrypted file when no Secret Service is available on Linux
- [ ] SQLite run history + saved report HTML files
- [ ] Engine settings: data dir resolution per OS, rotating logs
- [ ] Unit tests for collectors/render/filter with recorded fixtures (no network)

### Phase 1 — Engine features (≈8d)
- [ ] **Profiles**: one scheduler job per enabled profile; hot reload on change **(exists for single config)**
- [ ] Catch-up: if a run was missed (PC off), run on next start when `catch_up` is on
- [ ] **Email providers**: presets (Gmail, Outlook/365, Yahoo, custom host/port/SSL) **(SMTP exists)**
- [ ] IMAP: list recent threads (grouped by Gmail `X-GM-THRID` / References), recent correspondents for autocomplete **(thread lookup exists)**
- [ ] **GitHub source**: Device Flow auth (GitHub App, read-only: Contents, Metadata, Pull requests, Issues); list repos; commits (all branches), PRs, issues, commit diffs → same structure as GitLab
- [ ] GitHub fallback: pre-filled classic/fine-grained token page
- [ ] **GitLab**: OAuth + PKCE for gitlab.com (loopback `http://127.0.0.1:<port>/callback`); PAT for self-hosted **(PAT flow exists)**
- [ ] Project picker APIs: list projects/repos with last activity
- [ ] **Slack**: build manifest link, validate token (`auth.test`), list conversations with names **(exists: `list`)**, multiple workspaces
- [ ] **AI**: key validation, model fallback **(exists)**, per-profile language + extra instructions
- [ ] Filters: greetings list per profile **(exists)**, secret masking in diffs **(exists)**
- [ ] Run pipeline returns structured status per step (collected N commits, M messages, AI ok/failed, sent to …)

### Phase 2 — Local API (FastAPI) (≈3d)
- [ ] Startup: bind `127.0.0.1:0`, print `{port, token}` to stdout for the Rust shell
- [ ] Auth: bearer token on every request; reject non-localhost
- [ ] Endpoints:
  - `GET/POST/PUT/DELETE /connections` · `POST /connections/{id}/test`
  - `POST /auth/github/device/start` · `GET /auth/github/device/poll`
  - `POST /auth/gitlab/oauth/start` (returns URL, runs loopback listener) · `GET /auth/gitlab/oauth/status`
  - `GET /slack/manifest-url` · `GET /slack/{conn}/conversations`
  - `GET /email/{conn}/threads?q=` · `GET /email/{conn}/contacts?q=`
  - `GET /code/{conn}/projects`
  - `GET/POST/PUT/DELETE /profiles` · `POST /profiles/{id}/preview` · `POST /profiles/{id}/send`
  - `GET /runs?profile=` · `GET /runs/{id}` (HTML)
  - `GET /scheduler/next` · `GET /health`
- [ ] OpenAPI schema → generate TypeScript client for the UI

### Phase 3 — Tauri shell (Rust) (≈3d)
- [ ] Tauri 2 project, app id `com.rabshoot.app`, name **RabShoot**
- [ ] Sidecar: spawn engine on start, read `{port, token}`, restart on crash, stop on quit
- [ ] System tray: Open, Send now (per profile), Pause all, Quit; closing the window hides to tray
- [ ] Autostart at login (`tauri-plugin-autostart`), single instance (`tauri-plugin-single-instance`)
- [ ] Native notifications: report sent / failed (click → run details)
- [ ] Open external links in the default browser (`tauri-plugin-opener`)

### Phase 4 — UI (React) (≈10d)
- [ ] Design system from `logo.png`:
  - Background `#0A0B10`, surface `#12141C`, border `#23263A`, text `#E6E8F0`, muted `#9AA3B2`
  - Primary blue `#2F7BFF`, brand gradient `#2F7BFF → #8B5CF6`
  - Source accents: blue `#2F7BFF` (code), green `#10B981` (cloud/sync), violet `#7C3AED` (Slack/web), orange `#F59E0B` (AI/docs)
  - Fonts: Inter (EN), IBM Plex Sans Arabic or Cairo (AR); light theme optional later
- [ ] i18n with `react-i18next`, AR/EN, `dir="rtl"` switching, Tailwind logical properties, mirrored icons where needed
- [ ] Screens:
  - [ ] Onboarding wizard (section 3) with stepper "Collect • Combine • Send"
  - [ ] Dashboard: profiles cards (next run, last status), Send now, Preview, pause/resume
  - [ ] Profile editor (tabs: Delivery · Code · Slack · AI · Schedule · Look) — same components as the wizard
  - [ ] Connections manager (add/test/remove/re-auth, expiry warnings)
  - [ ] History: list of runs, open sent email (HTML), error details, re-send
  - [ ] Settings: language, autostart, catch-up default, data folder, logs, about
- [ ] Empty/error states and guidance copy (AR + EN) for every step
- [ ] Guide illustrations/screenshots for: Google App Password, Slack app creation, GitLab token, AI Studio key

### Phase 5 — Branded email (≈1d)
- [ ] Header with RabShoot mark, brand gradient accent, dark-friendly but email-safe (inline styles)
- [ ] Footer "Sent with RabShoot" (toggle)
- [ ] Keep text fallback **(exists)**

### Phase 6 — Packaging & release (≈4d)
- [ ] Icons: crop the envelope + plane mark from `logo.png` (no text) → `.ico` (16–256), PNG set, Linux `.desktop`
- [ ] PyInstaller one-file engine per OS, named with target triple for Tauri `externalBin`
- [ ] Windows: NSIS installer `RabShoot-Setup-x64.exe` (+ MSI optional)
- [x] Linux `.deb`; `scripts/build_linux_deb.sh` builds it in Docker on Ubuntu 22.04 so it runs on 22.04+ / Debian 12+ (glibc 2.35)
- [ ] GitHub Actions matrix (windows-latest, ubuntu-22.04): build engine → build Tauri → upload artifacts / release
- [ ] Code signing: document SmartScreen warning for unsigned builds; add signing step when a certificate is available
- [ ] Auto-update via Tauri updater (v1.1)

### Phase 7 — QA (≈3d)
- [ ] Engine unit + API tests in CI
- [ ] Manual test matrix: Windows 10, Windows 11, Ubuntu 22.04, Ubuntu 24.04 (GNOME + KDE for tray/keyring)
- [ ] Scenarios: first run, skip Slack, two profiles at the same time, PC off at send time, token revoked, AI model busy, thread reply-all, Arabic UI

### Phase 8 — Docs (≈1d)
- [ ] User guide (AR + EN) with screenshots
- [ ] Privacy note: what is sent to AI, where secrets are stored

**Rough total: ~36 dev-days** for v1.

---

## 5. Risks & limits to communicate in the UI

- **Slack free workspaces allow only 10 apps** — creating the RabShoot app may need an admin to free a slot.
- **Slack distributed-app rate limits** (non-Marketplace) make a shared "Add to Slack" app impractical — hence per-user apps in v1.
- **Gmail App Passwords** require 2-Step Verification; some Google Workspace admins disable them → offer Outlook/custom SMTP.
- **Gemini free tier** may use submitted data to improve Google products — warn before enabling on company code; allow paid keys.
- **Unsigned Windows builds** show a SmartScreen warning until a code-signing certificate is used.
- **Linux**: tray icons need AppIndicator support on GNOME; keyring needs a Secret Service (fallback provided); `.deb` depends on WebKitGTK 4.1.
- **GitHub App** must be installed on the user's orgs/repos to read private code — the wizard must guide that step.

## 6. Out of scope for v1 (candidates for v2)
- Slack Marketplace app with one-click "Add to Slack"
- "Sign in with Google" / Microsoft OAuth for email (Gmail API)
- macOS build
- Jira / Trello / Notion sources
- Team/shared reports via a server
