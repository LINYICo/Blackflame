"""Monthly update checking, transactional managed-runtime upgrades, and safe rollback."""

import copy
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import bootstrap
import runtime
import settings as settings_mod


def needs_refresh(settings, py_info=None, now=None):
    """Check whether a monthly refresh is due without mutating anything."""
    now = now or datetime.now(UTC)
    active = settings.get("environment")
    if active and py_info and runtime.environment(settings, py_info) == Path(py_info["executable"]):
        return True
    checker = settings.get("checker")
    if checker and checker.get("jar") and not Path(checker["jar"]).is_file():
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


def maintain(settings, tools, py_info=None, *, force=False):
    """Transactional monthly maintenance for Blackflame-managed runtimes.

    1. Keep existing working environment and settings untouched during staging.
    2. Stage and verify new private venv (latest compatible packages) in a temp dir.
    3. Stage and verify new official EPUBCheck JAR if managed (or broken).
    4. Atomically commit updated settings.json.
    5. Only after commit succeeds, safely remove the superseded venv if not in use.
    On any error, roll back staged directories and keep the previous working environment intact.
    """
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

    staged_settings = copy.deepcopy(settings)
    staged_env_dir = None
    old_env_dir = None
    try:
        active = staged_settings.get("environment")
        if active and py_info and staged_settings.get("python_manager") != "manual":
            managed_pkgs = list(active.get("packages", []))
            if managed_pkgs:
                old_env_py = runtime.environment(settings, py_info)
                if old_env_py != Path(py_info["executable"]):
                    old_env_dir = old_env_py.parent.parent
                new_env, staged_env_dir = bootstrap.stage_private_packages(
                    staged_settings, managed_pkgs, py_info, upgrade=True
                )
                if new_env:
                    staged_settings["environment"] = new_env

        checker_info = tools.get("EPUBCheck", {})
        if staged_settings.get("checker") and checker_info.get("owner") in ("official", "broken"):
            staged_settings["checker"] = bootstrap.stage_official_checker()

        now = datetime.now(UTC)
        staged_settings.update(
            last_updated_at=now.isoformat(),
            next_update_at=settings_mod.next_month(now).isoformat(),
        )
        staged_settings.pop("last_update_error", None)

        # Atomic commit before removing any previous working environment.
        settings_mod.save_settings(staged_settings)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        if staged_env_dir and staged_env_dir.exists():
            shutil.rmtree(staged_env_dir, ignore_errors=True)
        settings["last_update_error"] = str(error)
        try:
            settings_mod.save_settings(settings)
        except OSError:
            pass
        return False

    settings.clear()
    settings.update(staged_settings)
    if old_env_dir and staged_env_dir and old_env_dir != staged_env_dir:
        settings_mod.safe_remove_env(old_env_dir)
    return True
