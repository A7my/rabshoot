import os
import sys
from pathlib import Path


def _base_dirs() -> tuple[Path, Path]:
    """(config_dir, data_dir) for the current OS; RABSHOOT_HOME overrides both."""
    override = os.environ.get("RABSHOOT_HOME")
    if override:
        root = Path(override)
        return root / "config", root / "data"
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "RabShoot"
        return root, root / "data"
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "RabShoot"
        return root, root / "data"
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "rabshoot"
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "rabshoot"
    return config, data


def config_dir() -> Path:
    path = _base_dirs()[0]
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    path = _base_dirs()[1]
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir() -> Path:
    path = data_dir() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(*parts: str) -> Path:
    """Bundled read-only files (templates, assets); works inside a PyInstaller binary."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidate = base / "rabshoot_engine" / Path(*parts)
    if candidate.exists():
        return candidate
    return Path(__file__).resolve().parent / Path(*parts)
