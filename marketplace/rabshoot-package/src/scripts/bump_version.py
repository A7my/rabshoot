"""Set the app version everywhere it is written.

Usage: python scripts/bump_version.py 0.1.4
Then: git commit -am "v0.1.4" && git tag v0.1.4 && git push origin main v0.1.4
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sub(path: str, pattern: str, version: str, count: int = 1) -> None:
    file = ROOT / path
    text, n = re.subn(pattern, rf"\g<1>{version}\g<2>", file.read_text(encoding="utf-8"),
                      count=count, flags=re.M)
    if n == 0:
        sys.exit(f"Version not found in {path}")
    file.write_text(text, encoding="utf-8")
    print(f"{path}: {version}")


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        sys.exit(__doc__)
    v = sys.argv[1]
    sub("app/package.json", r'^(  "version": ")[^"]+(")', v)
    sub("app/package-lock.json", r'^(  "version": ")[^"]+(")', v)
    sub("app/package-lock.json", r'^(      "version": ")[^"]+(")', v)
    sub("app/src-tauri/tauri.conf.json", r'^(  "version": ")[^"]+(")', v)
    sub("app/src-tauri/Cargo.toml", r'^(version = ")[^"]+(")', v)
    sub("app/src-tauri/Cargo.lock", r'(name = "rabshoot"\nversion = ")[^"]+(")', v)
    sub("engine/pyproject.toml", r'^(version = ")[^"]+(")', v)
    sub("engine/rabshoot_engine/__init__.py", r'^(__version__ = ")[^"]+(")', v)
    json.loads((ROOT / "app/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
