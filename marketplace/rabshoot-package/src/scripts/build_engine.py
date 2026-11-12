"""Build the engine as a single-file binary and place it where Tauri expects the sidecar.

Output: app/src-tauri/binaries/rabshoot-engine-<target-triple>[.exe]
Usage:  python scripts/build_engine.py [--target <triple>]
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OAUTH_KEYS = ("RABSHOOT_GITHUB_CLIENT_ID", "RABSHOOT_GITHUB_APP_SLUG", "RABSHOOT_GITLAB_CLIENT_ID")
FALLBACK_TRIPLES = {
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("win32", "amd64"): "x86_64-pc-windows-msvc",
    ("win32", "arm64"): "aarch64-pc-windows-msvc",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("darwin", "arm64"): "aarch64-apple-darwin",
}


def host_triple() -> str:
    try:
        out = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
        for line in out.splitlines():
            if line.startswith("host:"):
                return line.split(":", 1)[1].strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    key = (sys.platform, platform.machine().lower())
    if key not in FALLBACK_TRIPLES:
        sys.exit(f"Unknown platform {key}; pass --target explicitly")
    return FALLBACK_TRIPLES[key]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", help="Rust target triple (default: host)")
    args = parser.parse_args()
    triple = args.target or host_triple()

    oauth = {k: os.environ[k] for k in OAUTH_KEYS if os.environ.get(k)}
    oauth_file = ROOT / "engine" / "rabshoot_engine" / "assets" / "oauth.json"
    oauth_file.write_text(json.dumps(oauth, indent=2), encoding="utf-8")
    print(f"OAuth client ids baked in: {', '.join(oauth) or 'none (token sign-in only)'}")

    work = ROOT / "engine" / "build"
    dist = ROOT / "engine" / "dist"
    try:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                        "--workpath", str(work), "--distpath", str(dist),
                        str(ROOT / "packaging" / "rabshoot-engine.spec")], check=True)
    finally:
        oauth_file.unlink(missing_ok=True)

    ext = ".exe" if sys.platform == "win32" else ""
    built = dist / f"rabshoot-engine{ext}"
    target_dir = ROOT / "app" / "src-tauri" / "binaries"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"rabshoot-engine-{triple}{ext}"
    # Unlink first: overwriting in place fails with "Text file busy" while an engine runs from it.
    target.unlink(missing_ok=True)
    shutil.copy2(built, target)
    print(f"Sidecar ready: {target} ({target.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
