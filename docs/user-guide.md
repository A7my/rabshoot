# RabShoot — User guide

RabShoot writes your daily work report for you. It reads the day's real code changes from GitLab or
GitHub and the work messages from Slack, has AI summarize them in clear English, and emails the
report at the time you choose.

## Install

- **Windows:** run `RabShoot_x.y.z_x64-setup.exe`. If Windows shows "Windows protected your PC", click
  **More info → Run anyway** (the app is not code-signed yet).
- **Linux (Ubuntu 22.04+, Debian 12+, Linux Mint 21+, Pop!_OS 22.04+, 64-bit):** open a terminal in
  the folder with the file and run `sudo apt install ./RabShoot_x.y.z_amd64.deb` (the `./` matters;
  apt then installs the needed libraries too). Start it from the apps menu or with `rabshoot`.
  Remove it with `sudo apt remove rab-shoot`. On GNOME, the tray icon needs the "AppIndicator"
  extension. Passwords and tokens are kept in the system keyring (GNOME Keyring / KWallet).

RabShoot starts with your computer and keeps running in the tray. Closing the window does not stop
the reports; use **Quit** in the tray menu for that.

## First-time setup

The wizard walks you through 8 steps. Every step explains what to do, and the button next to it
opens the right page for you. You can change everything later.

1. **Welcome** — choose Arabic or English for the app. Reports are written in English.
2. **Sender email** (required) — the account the report is sent from.
   - Gmail: turn on 2-Step Verification, then create an *App Password* (the button opens the page)
     and paste the 16 characters. Your normal password does not work here.
   - Outlook, Yahoo, Zoho, iCloud and custom SMTP servers are supported too. For a company server,
     open **Advanced settings** and enter the host and port from your IT team.
   - RabShoot tests the login before continuing.
3. **Recipients** (required) — choose one of two options:
   - **Send to people:** type addresses for To / CC / BCC. Suggestions come from people you email.
   - **Reply in a thread:** pick an existing email conversation. Each day's report is sent as
     *reply-all* inside it. The screen shows exactly who will receive it.
4. **Code sources** (at least one) — connect GitHub, GitLab.com or a self-hosted GitLab.
   - If one-click sign-in is available, click the button and approve in the browser.
   - Otherwise click **Open the page**. The token page opens with the right name and read-only
     permissions already filled in. Create the token, copy it and paste it here.
   - Then choose **All projects with activity that day** or pick specific projects.
5. **Slack** (optional, you can skip it) — works with any workspace.
   - A workspace needs **one** RabShoot Slack app, shared by everyone. Each person signs in with their
     own Slack account, so nobody sees anyone else's messages.
   - **Your team already has it:** paste the *team code* a teammate shared (the app's Client ID, like
     `1234567890123.1234567890123`) and click **Sign in with Slack**, then approve in the browser.
   - **You're the first:** click **Create the Slack app**. Slack opens with the app filled in; choose
     your workspace, then **Create** (no need to install). If Slack shows "Demo App" or an empty form,
     choose **From a manifest** and paste what **Copy manifest** gives you. Copy the **Client ID** from
     *Basic Information*, paste it as the team code, sign in, and share the code with your team. The
     team code is shown under the Slack account in **Accounts**.
   - **Reusing an older app:** in its *OAuth & Permissions* page, turn on **PKCE** and add the redirect
     URL `http://127.0.0.1:47114/slack/callback`. Then use its Client ID as the team code.
   - Pasting a *User OAuth Token* (`xoxp-…`) is still available under **Advanced**.
   - Pick the channels, private chats and group chats to read. Threads inside them are always included.
   - Greetings and small talk are ignored automatically.
   - Free Slack workspaces allow 10 apps. Because RabShoot uses one app per workspace, it takes only one.
6. **AI key** (required) — click the button to open Google AI Studio, create an API key, and paste it.
   RabShoot tries several models automatically if one is busy.
   See [privacy](privacy.md) before using a free key with company code.
7. **Schedule** — choose how the report goes out:
   - **Repeating:** the time, days (Sun–Thu, Mon–Fri, every day, or custom) and time zone.
   - **One time:** a single send on the date and time you pick.
   - **Send now:** no schedule. The report is sent once as soon as you press **Finish & send now**,
     and afterwards only when you press **Send now** on the dashboard.

   With "send when the computer starts" on, a scheduled report missed while the PC was off is
   sent at the next start.
8. **Preview** — build today's report and see the email exactly as it will be sent. **Send test to me**
   sends it only to your own address. Nothing goes to recipients until the scheduled time or
   **Send now**.

## Daily use

- **Reports:** each report card shows the next send time and the last result. It has buttons for
  **Send now**, **Preview**, and **Pause/Resume**. While a report is being built and sent, a progress
  bar shows each step (code, Slack, AI summary, email) and which project or chat it is on.
- **Today's scheduled sends:** the top of the Reports page lists the reports still due today. Press
  **Send now** to send one early: today's scheduled send is then skipped (for example, sent at 16:00
  means the 18:00 send doesn't happen today), and the next send moves to the next scheduled day.
  Test emails and previews never cause a skip, and if the early send fails the schedule still runs.
- **Send old report:** a separate button on each report card. It opens its own page: pick a day that
  already passed and press **Send the report of …**. RabShoot collects that day's commits and Slack
  messages and sends the report to the usual recipients. You can build a preview of that day first on
  the same page. Normal **Send now**, **Preview** and the schedule always use today.
- **Quiet days:** with "Don't send on days with no activity" on (Schedule tab, on by default), a
  scheduled send is skipped when there are no commits, merge requests, issues or Slack messages that
  day; the card shows "No activity that day". If a source failed (for example an expired token), the
  run is marked failed instead, so a problem never looks like a quiet day. **Send now** always sends.
- **New report:** create more reports, for example one per team, each with its own sender,
  recipients, sources and time.
- **Edit:** open a report to change any part. The tabs are Delivery, Code, Slack, AI, Schedule,
  Report (title, sections, extra AI instructions, how many points) and Preview.
- **Accounts:** add, test, update or remove connected accounts. An account used by a report cannot
  be deleted until you remove it from that report.
- **History:** every run, with its steps, recipients, the email as sent, and error details.
  **Send this day again** re-sends a past day.
- **Settings:** app language, appearance (light, dark or same as the system; zoom; text size), start
  with the computer, notifications, pause all reports, and where your data is stored. Zoom also works
  from the keyboard: **Ctrl +**, **Ctrl −**, and **Ctrl 0** to reset.

## Troubleshooting

| Message | What to do |
|---|---|
| Email login failed | Use an App Password, not your normal password. Check that 2-Step Verification is on. |
| Could not reach the server | Check your internet connection or the host name in Advanced settings. |
| GitLab/GitHub token rejected | The token expired or was revoked. Create a new one and use *Accounts → Update password / token*. |
| Slack `missing_scope` or `not_in_channel` | Check that the app has the user scopes from the manifest, or join the channel. |
| Slack "app belongs to a different workspace" | The team code is from another workspace. Ask someone in your workspace for its code, or create the app there. |
| Slack "PKCE" / `bad_redirect_uri` | In the app's *OAuth & Permissions*, turn on PKCE and add `http://127.0.0.1:47114/slack/callback`. |
| AI models busy | RabShoot retries other models. If it keeps failing, try again later or use a paid key. |
| No activity today | No commits or messages were found for that day; the report says so. |

Logs are in the *Logs* folder shown in **Settings**.
