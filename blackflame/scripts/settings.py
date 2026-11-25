"""Settings storage, file locking, atomic writes, and legacy migration for Blackflame."""

import calendar
import json
import os
from contextlib import contextmanager
from pathlib import Path

CONFIG_BASE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
ROOT = Path(os.environ.get("BLACKFLAME_HOME", CONFIG_BASE / "blackflame")).resolve()
LEGACY_ROOT = (CONFIG_BASE / "epublib").resolve()
SETTINGS_VERSION = 2


def next_month(date):
    year, month = date.year + (date.month == 12), date.month % 12 + 1
    return date.replace(year=year, month=month, day=min(date.day, calendar.monthrange(year, month)[1]))


@contextmanager
def settings_lock(root=None):
    target = Path(root) if root is not None else ROOT
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (target / "settings.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _read_json_dict(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Settings file must contain a JSON object")
    return data


def migrate_legacy_settings(legacy_root=None):
    """Import non-path preferences from a legacy EpubLib settings.json if present."""
    source = (Path(legacy_root) if legacy_root is not None else LEGACY_ROOT) / "settings.json"
    if not source.is_file():
        return {}
    try:
        legacy = _read_json_dict(source)
    except (OSError, ValueError):
        return {}
    migrated = {}
    for key in ("platform", "auto_install", "python_manager", "checker_manager", "update_interval_months"):
        if key in legacy:
            migrated[key] = legacy[key]
    if migrated:
        migrated["migrated_from"] = str(source)
        migrated["schema_version"] = SETTINGS_VERSION
    return migrated


def load_settings(root=None, *, allow_migration=True, recover_corrupt=False):
    """Load settings.json; optionally migrate legacy config or quarantine corrupt JSON."""
    target = Path(root) if root is not None else ROOT
    path = target / "settings.json"
    if path.exists():
        try:
            data = _read_json_dict(path)
            data.setdefault("schema_version", SETTINGS_VERSION)
            return data
        except (OSError, ValueError):
            if recover_corrupt:
                corrupt = target / "settings.json.corrupt"
                try:
                    path.replace(corrupt)
                except OSError:
                    pass
            return {}
    if allow_migration and root is None and not os.environ.get("BLACKFLAME_HOME"):
        return migrate_legacy_settings()
    return {}


def save_settings(settings, root=None):
    """Atomically persist settings.json with owner-only permissions."""
    target = Path(root) if root is not None else ROOT
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = dict(settings)
    payload.setdefault("schema_version", SETTINGS_VERSION)
    tmp = target / f"settings.{os.getpid()}.tmp"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(target / "settings.json")
