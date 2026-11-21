"""First-use preferences and monthly runtime maintenance for the EpubLib skill."""

import argparse
import calendar
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import file_digest
from importlib.machinery import PathFinder
from importlib.util import find_spec
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory, mkdtemp
from urllib.request import urlopen
from zipfile import ZipFile


ROOT = Path(os.environ.get("EPUBLIB_HOME", Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "epublib")).resolve()
CLI = Path(__file__).with_name("epub_patch.py")


def next_month(date):
    year, month = date.year + (date.month == 12), date.month % 12 + 1
    return date.replace(year=year, month=month, day=min(date.day, calendar.monthrange(year, month)[1]))


@contextmanager
def settings_lock():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (ROOT / "settings.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def save(settings):
    tmp = ROOT / "settings.tmp"
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(ROOT / "settings.json")


def run_quietly(args):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=420)
    if proc.returncode:
        raise RuntimeError(proc.stdout.strip()[-1800:] or f"{args[0]} exited with status {proc.returncode}")


def java_executable():
    candidates = []
    if os.environ.get("JAVA_HOME"):
        candidates.append(str(Path(os.environ["JAVA_HOME"]) / "bin" / "java"))
    candidates += [shutil.which("java"), "/opt/homebrew/opt/openjdk/bin/java", "/usr/local/opt/openjdk/bin/java"]
    for java in candidates:
        if java and Path(java).is_file() and subprocess.run([java, "-version"], capture_output=True).returncode == 0:
            return java
    return None


def install_checker(dest):
    with urlopen("https://api.github.com/repos/w3c/epubcheck/releases/latest", timeout=45) as response:
        release = json.load(response)
    name = f"epubcheck-{release['tag_name'].removeprefix('v')}"
    asset = next(a for a in release["assets"] if a["name"] == name + ".zip")
    with TemporaryDirectory(dir=dest) as tmp:
        bundle = Path(tmp) / "release.zip"
        with urlopen(asset["browser_download_url"], timeout=120) as response, bundle.open("wb") as out:
            shutil.copyfileobj(response, out)
        with bundle.open("rb") as stream:
            if "sha256:" + file_digest(stream, "sha256").hexdigest() != asset.get("digest"):
                raise ValueError("EPUBCheck release digest mismatch")
        with ZipFile(bundle) as archive:
            for item in archive.namelist():
                path = Path(item)
                if path.parts[:1] == (name,) and ".." not in path.parts and path.suffix == ".jar":
                    archive.extract(item, dest)
    return dest / name / "epubcheck.jar"


def refresh(settings, dest):
    install = settings["auto_install"]
    packages = {"lxml": "lxml", "ebooklib": "EbookLib", "bs4": "beautifulsoup4"}
    if sys.version_info >= (3, 13):
        packages["epublib"] = "epublib"
    previous = settings.get("runtime", {})
    previous_lib = ROOT / previous.get("directory", "") / "python"
    selected = [pkg for mod, pkg in packages.items()
                if install or find_spec(mod) or PathFinder.find_spec(mod, [str(previous_lib)])]
    checker = install or previous.get("jar") or shutil.which("epubcheck")
    java = java_executable() if checker else None
    if checker and not java:
        if not install and not previous.get("java"):
            raise RuntimeError("A working Java runtime is required to update EPUBCheck")
        selected.append("jdk4py")
    if selected:
        run_quietly([sys.executable, "-m", "pip", "--disable-pip-version-check", "--no-input", "install",
                     "--upgrade", "--target", str(dest / "python"), *selected])
    runtime = {"directory": dest.name, "python_abi": sys.implementation.cache_tag}
    if checker:
        jar = install_checker(dest)
        if not java:
            binaries = list((dest / "python" / "jdk4py").rglob("java.exe" if os.name == "nt" else "java"))
            java = str(next(path for path in binaries if path.is_file() and path.parent.name == "bin"))
        run_quietly([java, "-jar", str(jar), "--version"])
        runtime.update(java=java, jar=str(jar))
    return runtime


def maintain(settings):
    now = datetime.now(timezone.utc)
    active = settings.get("runtime", {})
    usable = (active.get("python_abi") == sys.implementation.cache_tag
              and (ROOT / active["directory"]).is_dir())
    if usable and settings.get("next_update_at") and now < datetime.fromisoformat(settings["next_update_at"]):
        return
    dest = Path(mkdtemp(prefix="runtime-", dir=ROOT))
    old = settings.get("runtime", {}).get("directory")
    try:
        runtime = refresh(settings, dest)
    except Exception as error:
        shutil.rmtree(dest)
        settings["last_update_error"] = str(error)
        save(settings)
        if not usable:
            raise
        return
    now = datetime.now(timezone.utc)
    settings.update(runtime=runtime, last_updated_at=now.isoformat(), next_update_at=next_month(now).isoformat())
    settings.pop("last_update_error", None)
    save(settings)
    if old and Path(old).name == old and old.startswith("runtime-"):
        shutil.rmtree(ROOT / old, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    setup = commands.add_parser("configure")
    setup.add_argument("--auto-install", required=True, choices=["yes", "no"])
    setup.add_argument("--platform", required=True, help="Reading platform, or general")
    for name in ("run", "python"):
        commands.add_parser(name, add_help=False).add_argument("args", nargs=argparse.REMAINDER)
    # Forward downstream flags verbatim, including python -c and CLI --help.
    forwarded = sys.argv[1:2] in (["run"], ["python"])
    args = parser.parse_args(sys.argv[1:2] if forwarded else None)
    with settings_lock():
        path = ROOT / "settings.json"
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if args.command == "status":
            if settings:
                maintain(settings)
            print(json.dumps({"first_use": not settings, "platform": settings.get("platform")}, ensure_ascii=False))
            return 0
        if args.command == "configure":
            allow_install = args.auto_install == "yes"
            if allow_install and not settings.get("auto_install"):
                settings["next_update_at"] = None
            settings.update(auto_install=allow_install, platform=args.platform.strip() or "general",
                            update_interval_months=1)
            save(settings)
        if not settings:
            parser.exit(2, "First use: configure automatic installation and your reading platform first.\n")
        maintain(settings)
        if not forwarded:
            return 0
        runtime = settings["runtime"]
        env = os.environ.copy()
        lib = str(ROOT / runtime["directory"] / "python")
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [lib, env.get("PYTHONPATH")]))
        if runtime.get("jar"):
            env.update(EPUBLIB_CHECKER_JAR=runtime["jar"], EPUBLIB_JAVA=runtime["java"])
        cmd = [sys.executable] + ([str(CLI)] if args.command == "run" else []) + sys.argv[2:]
        return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError, StopIteration, KeyError) as exc:
        sys.exit(f"epublib: dependency setup failed: {exc}")
