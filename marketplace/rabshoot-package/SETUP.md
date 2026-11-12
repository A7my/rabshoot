# RabShoot Setup

Two ways to get RabShoot running: the installer (easiest) or from source.

## Option 1: Installer

| System | File | Install |
|---|---|---|
| Windows 10 / 11 (64-bit) | `RabShoot-windows-x64-setup.exe` | Run it. If Windows shows "Windows protected your PC", click **More info, then Run anyway** (the app is not code-signed yet). |
| Ubuntu 22.04+, Debian 12+, Mint 21+, Pop!_OS 22.04+ | `RabShoot-linux-amd64.deb` | `sudo apt install ./RabShoot-linux-amd64.deb` |

Downloads: https://github.com/A7my/rabshoot/releases/latest

Open **RabShoot** from the Start menu / apps menu. It lives in the system tray; closing the window does
not stop scheduled reports (use **Quit** in the tray menu). On GNOME, the tray icon needs the
"AppIndicator" extension.

## Option 2: Run from source

Requirements: Python 3.11+, Node 20+. For the desktop shell also Rust (stable) and the
[Tauri system libraries](https://tauri.app/start/prerequisites/).

```bash
cd src

# 1. Engine + tests
python -m venv .venv
.venv/bin/pip install -e "engine[dev]"          # Windows: .venv\Scripts\pip
cd engine && ../.venv/bin/python -m pytest -q && cd ..

# 2. Start a dev engine (no keychain needed)
RABSHOOT_HOME=$PWD/.rabshoot-dev RABSHOOT_SECRETS=file PYTHONPATH=engine \
  .venv/bin/python -m rabshoot_engine serve --port 8765 --token dev --no-catch-up

# 3. UI in a browser (new terminal)
cd app && npm ci && npm run dev                 # http://localhost:1420
```

### Build the installers

```bash
python scripts/build_engine.py     # engine sidecar -> app/src-tauri/binaries/
cd app && npx tauri build          # Windows: .exe  |  Linux: .deb + .AppImage
```

## First-run setup (inside the app)

The app opens a short wizard (about 5 minutes):

1. **Sender email**: Gmail, Outlook, Yahoo, iCloud, Zoho or any IMAP/SMTP, with an *app password*.
2. **Recipients**: To / CC / BCC, or reply-all in an existing email thread.
3. **Code sources**: GitLab and/or GitHub.
4. **Slack** (optional): workspace and channels to read.
5. **AI key**: a free Google Gemini key from https://aistudio.google.com/apikey
6. **Schedule**: repeating, one time, or send now.
7. **Preview**: see the exact email, or send a test to yourself.

## Notes

- No license key and no RabShoot account are needed.
- Passwords and tokens are stored in the system keychain.
- Free Gemini keys may use data to improve Google products. Read `src/docs/privacy.md` before using
  one with company code.
- Optional OAuth sign-in: set `RABSHOOT_GITHUB_CLIENT_ID`, `RABSHOOT_GITHUB_APP_SLUG` and
  `RABSHOOT_GITLAB_CLIENT_ID`. Without them the app guides you to create a personal access token.

Full guide: `src/docs/user-guide.md` (English), `src/docs/user-guide.ar.md` (Arabic).
