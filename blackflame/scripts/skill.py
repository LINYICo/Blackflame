"""CLI entry point and workflow dispatcher for the Blackflame EPUB skill."""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import bootstrap
import maintenance
import runtime
import settings as settings_mod

CLI = Path(__file__).with_name("epub_patch.py")


def _status_payload(settings, tools, py_info, first_use):
    core_missing = [p for p in runtime.CORE_PACKAGES.values() if tools[p]["owner"] in ("missing", "broken")]
    optional_missing = [p for p in runtime.OPTIONAL_PACKAGES.values() if tools[p]["owner"] in ("missing", "broken")]
    all_missing = [p for p, v in tools.items() if v["owner"] in ("missing", "broken")]
    return {
        "first_use": first_use,
        "interpreter": py_info["executable"] if py_info else sys.executable,
        "preferred_python": settings.get("preferred_python"),
        "python_version": ".".join(str(v) for v in py_info["version"]) if py_info else None,
        "abi": py_info["abi"] if py_info else sys.implementation.cache_tag,
        "arch": py_info["arch"] if py_info else None,
        "platform": settings.get("platform"),
        "auto_install": settings.get("auto_install"),
        "missing": all_missing,
        "missing_core": core_missing,
        "missing_optional": optional_missing,
        "update_due": maintenance.needs_refresh(settings, py_info) if settings else False,
        "tools": tools,
        "last_update_error": settings.get("last_update_error"),
    }


def _cmd_status(args):
    """Strictly read-only environment inspection; never installs or modifies settings."""
    settings = settings_mod.load_settings(allow_migration=True, recover_corrupt=False)
    first_use = not (settings_mod.ROOT / "settings.json").exists()
    tools, py_info = runtime.discover(settings, preferred_python=args.python, strict_preferred=bool(args.python))
    print(json.dumps(_status_payload(settings, tools, py_info, first_use), ensure_ascii=False))
    return 0


def _cmd_setup(args):
    """Explicitly prepare missing dependencies within authorized boundaries."""
    with settings_mod.settings_lock():
        settings = settings_mod.load_settings(allow_migration=True, recover_corrupt=True)
        if args.python:
            settings["preferred_python"] = os.path.abspath(args.python)
        tools, py_info = runtime.discover(settings, preferred_python=args.python, strict_preferred=bool(args.python))
        if args.platform:
            settings["platform"] = args.platform.strip() or "general"
        if args.python_manager:
            settings["python_manager"] = args.python_manager
        if args.checker_manager:
            settings["checker_manager"] = args.checker_manager
        settings["auto_install"] = args.auto_install == "yes"

        if args.packages == "core":
            wanted = list(runtime.CORE_PACKAGES.values())
        elif args.packages == "all":
            wanted = list(runtime.PACKAGES.values())
        else:
            wanted = list(args.package or runtime.CORE_PACKAGES.values())

        tools, py_info, old_env_dir = bootstrap.setup_environment(
            settings,
            tools,
            py_info,
            allow_system_install=args.allow_system_install,
            packages=wanted,
            install_epubcheck=args.install_epubcheck,
        )
        now = datetime.now(UTC)
        settings.setdefault("last_updated_at", now.isoformat())
        settings.setdefault("next_update_at", settings_mod.next_month(now).isoformat())
        settings.pop("last_update_error", None)
        settings_mod.save_settings(settings)
        if old_env_dir:
            settings_mod.safe_remove_env(old_env_dir)
        print(json.dumps(_status_payload(settings, tools, py_info, False), ensure_ascii=False))
        return 0


def _cmd_update(args):
    """Explicitly check or refresh Blackflame-managed runtimes."""
    with settings_mod.settings_lock():
        settings = settings_mod.load_settings(allow_migration=True, recover_corrupt=True)
        tools, py_info = runtime.discover(settings, preferred_python=args.python, strict_preferred=bool(args.python))
        due = maintenance.needs_refresh(settings, py_info)
        if args.check:
            print(
                json.dumps(
                    {
                        "update_due": due,
                        "managed_components": maintenance.has_managed_components(settings),
                        "last_updated_at": settings.get("last_updated_at"),
                        "next_update_at": settings.get("next_update_at"),
                        "last_update_error": settings.get("last_update_error"),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        maintenance.maintain(settings, tools, py_info, force=args.force or due)
        if settings.get("last_update_error"):
            sys.stderr.write(
                f"blackflame: update failed (previous environment kept): {settings['last_update_error']}\n"
            )
            return 1
        return 0


def _cmd_configure(args, parser):
    """Persist user preferences and optionally prepare approved private dependencies."""
    with settings_mod.settings_lock():
        settings = settings_mod.load_settings(allow_migration=True, recover_corrupt=True)
        if args.python:
            settings["preferred_python"] = os.path.abspath(args.python)
        tools, py_info = runtime.discover(settings, preferred_python=args.python, strict_preferred=bool(args.python))
        updates = {
            "auto_install": args.auto_install == "yes",
            "platform": args.platform.strip() or "general",
        }
        if args.dedicated_venv:
            if args.dedicated_venv == "yes" and not runtime.dedicated_venv(py_info):
                parser.error("--dedicated-venv yes requires a standalone virtual environment")
            updates["dedicated_interpreter"] = py_info["executable"] if args.dedicated_venv == "yes" else None
        for key in ("python_manager", "checker_manager"):
            if value := getattr(args, key):
                updates[key] = value
        if args.auto_install == "no" and (args.package or args.install_epubcheck):
            parser.error("Installation requires --auto-install yes")
        settings.update(updates, update_interval_months=1)
        old_env_dir = None
        if args.package or args.install_epubcheck:
            tools, py_info, old_env_dir = bootstrap.setup_environment(
                settings,
                tools,
                py_info,
                allow_system_install=args.allow_system_install,
                packages=args.package or [],
                install_epubcheck=args.install_epubcheck,
            )
        now = datetime.now(UTC)
        settings.setdefault("last_updated_at", now.isoformat())
        settings.setdefault("next_update_at", settings_mod.next_month(now).isoformat())
        settings_mod.save_settings(settings)
        if old_env_dir:
            settings_mod.safe_remove_env(old_env_dir)
        return 0


def _cmd_forward(command, extra_args):
    """Forward `run` or `python` to the verified local or managed Python runtime."""
    managed_env_dir = None
    with settings_mod.settings_lock():
        settings = settings_mod.load_settings(allow_migration=True, recover_corrupt=True)
        tools, py_info = runtime.discover(settings)
        if not py_info:
            raise RuntimeError("No Python >= 3.11 interpreter found. Run `skill.py setup --allow-system-install`.")
        missing_core = [p for p in runtime.CORE_PACKAGES.values() if tools[p]["owner"] in ("missing", "broken")]
        if missing_core:
            if settings.get("auto_install") and settings.get("python_manager") != "manual":
                tools, py_info, old_env_dir = bootstrap.setup_environment(
                    settings,
                    tools,
                    py_info,
                    allow_system_install=False,
                    packages=missing_core,
                )
                settings_mod.save_settings(settings)
                if old_env_dir:
                    settings_mod.safe_remove_env(old_env_dir)
            else:
                raise RuntimeError(
                    f"Missing or broken required core dependencies: {', '.join(missing_core)}. "
                    "Run `skill.py setup` or install them in your Python environment."
                )
        elif settings and maintenance.needs_refresh(settings, py_info):
            maintenance.maintain(settings, tools, py_info)
            tools, py_info = runtime.discover(settings, preferred_python=py_info["executable"])

        python = runtime.environment(settings, py_info)
        if os.path.abspath(str(python)) != os.path.abspath(py_info["executable"]):
            managed_env_dir = python.parent.parent
        env = os.environ.copy()
        env["PATH"] = runtime.search_path()
        if (legacy := runtime.legacy_library(settings, py_info["abi"])) and python == Path(py_info["executable"]):
            paths = list(py_info.get("site_packages", []))
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [env.get("PYTHONPATH"), *paths, str(legacy)]))
        checker = tools["EPUBCheck"]
        if checker.get("jar"):
            env.update(BLACKFLAME_CHECKER_JAR=checker["jar"], BLACKFLAME_JAVA=checker["java"])

    cmd = [str(python)] + ([str(CLI)] if command == "run" else []) + extra_args
    with settings_mod.env_in_use_lock(managed_env_dir):
        return subprocess.run(cmd, env=env).returncode


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="Read-only inspection of local runtime and dependencies")
    status.add_argument("--python", help="Explicit Python interpreter path to inspect")

    setup = commands.add_parser("setup", help="Explicitly prepare missing runtime dependencies")
    setup.add_argument("--python", help="Explicit Python interpreter path to use and persist")
    setup.add_argument("--platform", default="general", help="Reading platform, or general")
    setup.add_argument("--auto-install", default="yes", choices=("yes", "no"))
    setup.add_argument("--allow-system-install", action="store_true", help="Authorize Homebrew/system installs")
    setup.add_argument("--packages", choices=("core", "all"), help="Install missing core or all EPUB packages")
    setup.add_argument("--package", action="append", choices=list(runtime.PACKAGES.values()))
    setup.add_argument("--install-epubcheck", action="store_true", help="Install EPUBCheck if missing")
    setup.add_argument("--python-manager", choices=("uv", "pip", "manual"))
    setup.add_argument("--checker-manager", choices=("homebrew", "official", "manual"))

    update = commands.add_parser("update", help="Check or update Blackflame-managed runtimes")
    update.add_argument("--python", help="Explicit Python interpreter path")
    update.add_argument("--check", action="store_true", help="Check if an update is due without applying it")
    update.add_argument("--force", action="store_true", help="Force refresh of Blackflame-managed runtimes")

    cfg = commands.add_parser("configure", help="Save reader platform and dependency preferences")
    cfg.add_argument("--python", help="Explicit Python interpreter path to persist")
    cfg.add_argument("--auto-install", default="yes", choices=("yes", "no"))
    cfg.add_argument("--platform", required=True, help="Reading platform, or general")
    cfg.add_argument("--dedicated-venv", choices=("yes", "no"))
    cfg.add_argument("--allow-system-install", action="store_true")
    cfg.add_argument("--python-manager", choices=("pip", "uv", "manual"))
    cfg.add_argument("--package", action="append", choices=list(runtime.PACKAGES.values()))
    cfg.add_argument("--install-epubcheck", action="store_true")
    cfg.add_argument("--checker-manager", choices=("homebrew", "official", "manual"))

    for name in ("run", "python"):
        commands.add_parser(name, add_help=False).add_argument("args", nargs=argparse.REMAINDER)
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    forwarded = argv[:1] in (["run"], ["python"])
    args = parser.parse_args(argv[:1] if forwarded else argv)
    if args.command == "status":
        return _cmd_status(args)
    if args.command == "setup":
        return _cmd_setup(args)
    if args.command == "update":
        return _cmd_update(args)
    if args.command == "configure":
        return _cmd_configure(args, parser)
    return _cmd_forward(args.command, argv[1:])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError, StopIteration, KeyError) as exc:
        sys.exit(f"blackflame: dependency setup failed: {exc}")
