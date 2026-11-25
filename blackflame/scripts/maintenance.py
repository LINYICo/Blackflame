"""Monthly update checking, safe managed-runtime upgrades, and rollback on failure."""

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp

import bootstrap
import runtime
import settings as settings_mod


def needs_refresh(settings, py_info=None, now=None):
    """Check whether a monthly refresh is due without mutating anything."""
    now = now or datetime.now(UTC)
    active = settings.get("environment")
    if active and py_info and runtime.environment(settings, py_info) == Path(py_info["executable"]):
        return True
    next_at = settings.get("next_update_at")
    if not next_at:
        return True
    try:
        return now >= datetime.fromisoformat(next_at)
    except ValueError:
        return True


def has_managed_components(settings):
    """Return True if Blackflame manages a private venv or official EPUBCheck JAR."""
    return bool(settings.get("environment") or settings.get("checker"))


def refresh_managed(settings, tools, py_info):
    """Update ONLY Blackflame-managed environments (private venv and official EPUBCheck JAR).

    External Python environments and Homebrew formulas remain under their own package managers.
    New environments are verified before switching; failures preserve the previous working runtime.
    """
    active = settings.get("environment")
    if active and py_info:
        managed_pkgs = [
            p for p in active.get("packages", []) if tools.get(p, {}).get("owner") in ("managed", "missing", "legacy")
        ]
        if managed_pkgs:
            old_env = runtime.environment(settings, py_info)
            settings_mod.ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
            dest = Path(mkdtemp(prefix="env-", dir=settings_mod.ROOT))
            try:
                new_env = bootstrap.make_environment(settings, managed_pkgs, dest, py_info=py_info)
            except BaseException:
                shutil.rmtree(dest, ignore_errors=True)
                raise
            settings["environment"] = new_env
            if old_env != Path(py_info["executable"]) and old_env != runtime.env_python(dest):
                shutil.rmtree(old_env.parent.parent, ignore_errors=True)

    checker = tools.get("EPUBCheck", {})
    if checker.get("owner") == "official" and settings.get("checker"):
        bootstrap.install_official_checker(settings)


def maintain(settings, tools, py_info=None, *, force=False):
    """Run monthly maintenance for Blackflame-managed runtimes with rollback on error."""
    if not force and not needs_refresh(settings, py_info):
        return False
    if not has_managed_components(settings):
        now = datetime.now(UTC)
        settings.update(
            last_updated_at=now.isoformat(),
            next_update_at=settings_mod.next_month(now).isoformat(),
        )
        settings.pop("last_update_error", None)
        settings_mod.save_settings(settings)
        return False
    try:
        refresh_managed(settings, tools, py_info)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        settings["last_update_error"] = str(error)
        settings_mod.save_settings(settings)
        return False
    now = datetime.now(UTC)
    settings.update(
        last_updated_at=now.isoformat(),
        next_update_at=settings_mod.next_month(now).isoformat(),
    )
    settings.pop("last_update_error", None)
    settings_mod.save_settings(settings)
    return True
