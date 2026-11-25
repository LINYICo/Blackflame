"""First-use preferences and monthly runtime maintenance for the Blackflame skill."""

import argparse
import calendar
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import file_digest
from importlib import metadata
from importlib.machinery import PathFinder
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(
    os.environ.get("BLACKFLAME_HOME", Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "blackflame")
).resolve()
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
    # Environment-wide installer target overrides must not redirect a venv write.
    env = os.environ.copy()
    for key in ("PIP_TARGET", "PIP_PREFIX", "PIP_USER", "UV_TARGET", "UV_PREFIX", "UV_SYSTEM_PYTHON"):
        env.pop(key, None)
    proc = subprocess.run(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=420)
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


PACKAGES = {"lxml": "lxml", "bs4": "beautifulsoup4", "epublib": "epublib"}


def brew_cellar():
    if brew := shutil.which("brew"):
        result = subprocess.run([brew, "--cellar"], capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    return None


def formula_owner(path, cellar):
    if path and cellar:
        resolved = Path(path).resolve()
        if resolved.is_relative_to(cellar):
            parts = resolved.relative_to(cellar).parts
            if len(parts) > 2 and (cellar / parts[0] / parts[1] / "INSTALL_RECEIPT.json").is_file():
                # A pip package inside a brewed interpreter does not own that formula.
                if parts[0] != "python" and not parts[0].startswith("python@"):
                    return parts[0]
    return None


def legacy_library(settings):
    runtime = settings.get("runtime", {})
    name = runtime.get("directory", "")
    if (
        Path(name).name == name
        and name.startswith("runtime-")
        and runtime.get("python_abi") == sys.implementation.cache_tag
    ):
        return ROOT / name / "python"
    return None


def discover(settings):
    cellar = brew_cellar()
    tools = {}
    legacy = legacy_library(settings)
    for module, package in PACKAGES.items():
        try:
            dist = metadata.distribution(package)
            spec = find_spec(module)
        except metadata.PackageNotFoundError:
            spec = None
        if spec and spec.origin:
            manager = (dist.read_text("INSTALLER") or "").strip() or "external"
            formula = formula_owner(spec.origin, cellar)
            tools[package] = dict(
                owner="homebrew" if formula else manager, formula=formula, version=dist.version, path=spec.origin
            )
        elif legacy and PathFinder.find_spec(module, [str(legacy)]):
            tools[package] = dict(owner="legacy", path=str(legacy))
        else:
            tools[package] = dict(
                owner="unsupported" if module == "epublib" and sys.version_info < (3, 13) else "missing"
            )
    exe = shutil.which("epubcheck")
    jar = os.environ.get("BLACKFLAME_CHECKER_JAR")
    managed = settings.get("checker", {}) or settings.get("runtime", {})
    if jar and Path(jar).is_file():
        checker = dict(owner="external-jar", jar=jar, java=os.environ.get("BLACKFLAME_JAVA", "java"))
    elif exe:
        formula = formula_owner(exe, cellar)
        checker = dict(owner="homebrew" if formula else "external", path=exe, formula=formula)
    elif managed.get("jar") and Path(managed["jar"]).is_file():
        checker = dict(
            owner="official" if settings.get("checker") else "legacy", jar=managed["jar"], java=managed["java"]
        )
    else:
        checker = dict(owner="missing")
    tools["EPUBCheck"] = checker
    return tools


def env_python(directory):
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def environment(settings):
    active = settings.get("environment", {})
    name = active.get("directory", "")
    if (
        Path(name).name == name
        and name.startswith("env-")
        and active.get("interpreter") == sys.executable
        and active.get("abi") == sys.implementation.cache_tag
        and env_python(ROOT / name).is_file()
    ):
        return env_python(ROOT / name)
    return Path(sys.executable)


def make_environment(settings, packages, dest):
    method = settings["python_manager"]
    python = env_python(dest)
    if method == "uv":
        run_quietly(["uv", "venv", "--python", sys.executable, str(dest)])
        install = ["uv", "pip", "install", "--python", str(python)]
    else:
        run_quietly([sys.executable, "-m", "venv", str(dest)])
        install = [
            str(python),
            "-m",
            "pip",
            "--disable-pip-version-check",
            "--no-input",
            "install",
            "--prefix",
            str(dest),
        ]
    # Expose existing distributions read-only to the resolver and to the skill.
    paths = [p for p in sys.path if p and Path(p).name in {"site-packages", "dist-packages"}]
    if legacy := legacy_library(settings):
        paths.append(str(legacy))
    target = subprocess.check_output(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True
    ).strip()
    (Path(target) / "blackflame-host.pth").write_text("\n".join(paths) + "\n", encoding="utf-8")
    run_quietly([*install, "--upgrade", *packages])
    modules = [module for module, package in PACKAGES.items() if package in packages]
    run_quietly([str(python), "-c", "import " + ", ".join(modules)])
    return dict(
        directory=dest.name,
        interpreter=sys.executable,
        abi=sys.implementation.cache_tag,
        manager=method,
        packages=packages,
    )


def dedicated_venv():
    prefix = Path(sys.prefix)
    if sys.prefix == sys.base_prefix or not (prefix / "pyvenv.cfg").is_file():
        return False
    markers = ("pyproject.toml", "uv.lock", "poetry.lock", "Pipfile", "conda-meta")
    return not any((parent / marker).exists() for parent in [prefix, *prefix.parents] for marker in markers)


def update_dedicated(settings, tools):
    if settings.get("dedicated_interpreter") != sys.executable:
        return
    if not dedicated_venv():
        raise ValueError("The selected interpreter is no longer a standalone virtual environment")
    for manager in ("pip", "uv"):
        owned = [
            p
            for p in PACKAGES.values()
            if tools[p]["owner"] == manager
            and Path(tools[p]["path"]).resolve().is_relative_to(Path(sys.prefix).resolve())
        ]
        if owned:
            command = (
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "--disable-pip-version-check",
                    "--no-input",
                    "install",
                    "--prefix",
                    sys.prefix,
                ]
                if manager == "pip"
                else ["uv", "pip", "install", "--python", sys.executable]
            )
            run_quietly([*command, "--upgrade", *owned])


def refresh(settings, tools, approved=(), install_checker_now=False):
    update_dedicated(settings, tools)
    # Only a proven Homebrew owner may update an existing formula.
    formulas = sorted({v["formula"] for v in tools.values() if v.get("formula")})
    if formulas:
        pinned = subprocess.check_output(["brew", "list", "--pinned"], text=True).splitlines()
        for formula in formulas:
            if formula not in pinned:
                run_quietly(["brew", "upgrade", "--formula", formula])
    active = settings.get("environment", {})
    missing = [
        p
        for p in PACKAGES.values()
        if tools[p]["owner"] == "missing"
        or (tools[p]["owner"] == "legacy" and settings.get("python_manager") in ("pip", "uv"))
    ]
    packages = [p for p in missing if p in approved or p in active.get("packages", [])]
    if settings.get("python_manager") == "homebrew":
        mappings = settings.get("brew_formulas", {})
        for package in packages:
            if package not in mappings:
                raise ValueError(f"Provide --brew-formula {package}=FORMULA or select only mapped packages")
            run_quietly(["brew", "install", "--formula", mappings[package]])
        if packages:
            visible = discover(settings)
            for package in packages:
                if visible[package].get("formula") != mappings[package].split("/")[-1]:
                    raise ValueError(f"{package} is unavailable from its requested keg in {sys.executable}")
    checker = tools["EPUBCheck"]
    method = settings.get("checker_manager")
    if checker["owner"] == "missing" and install_checker_now and method == "homebrew":
        run_quietly(["brew", "install", "--formula", "epubcheck"])
        if not shutil.which("epubcheck"):
            raise RuntimeError("Homebrew installed EPUBCheck but it is unavailable on PATH")
    elif (checker["owner"] in ("official", "legacy") and method == "official") or (
        checker["owner"] == "missing" and install_checker_now and method == "official"
    ):
        java = java_executable()
        if not java:
            raise RuntimeError("Official EPUBCheck requires an existing Java runtime")
        with TemporaryDirectory(dir=ROOT) as tmp:
            jar = install_checker(Path(tmp))
            run_quietly([java, "-jar", str(jar), "--version"])
            # Each verified version has its own immutable directory.
            parent = ROOT / "checker" / jar.parent.name
            parent.parent.mkdir(exist_ok=True)
            if not parent.exists():
                jar.parent.rename(parent)
            settings["checker"] = dict(java=java, jar=str(parent / jar.name))
    if packages and settings.get("python_manager") in ("pip", "uv"):
        dest = Path(mkdtemp(prefix="env-", dir=ROOT))
        try:
            settings["environment"] = make_environment(settings, packages, dest)
        except BaseException:
            shutil.rmtree(dest)
            raise
    elif not packages:
        settings.pop("environment", None)


def maintain(settings, tools, approved=(), install_checker_now=False):
    now = datetime.now(UTC)
    runtime_ok = not settings.get("environment") or environment(settings) != Path(sys.executable)
    if (
        not (approved or install_checker_now)
        and runtime_ok
        and settings.get("next_update_at")
        and now < datetime.fromisoformat(settings["next_update_at"])
    ):
        return
    old = environment(settings)
    try:
        refresh(settings, tools, approved, install_checker_now)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        settings["last_update_error"] = str(error)
        save(settings)
        return
    now = datetime.now(UTC)
    settings.update(last_updated_at=now.isoformat(), next_update_at=next_month(now).isoformat())
    settings.pop("last_update_error", None)
    save(settings)
    if old != Path(sys.executable) and old != environment(settings):
        shutil.rmtree(old.parent.parent, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    setup = commands.add_parser("configure")
    setup.add_argument("--auto-install", required=True, choices=["yes", "no"])
    setup.add_argument("--platform", required=True, help="Reading platform, or general")
    setup.add_argument("--dedicated-venv", choices=("yes", "no"), help="Allow owner updates in this standalone venv")
    setup.add_argument("--python-manager", choices=("pip", "uv", "homebrew", "manual"))
    setup.add_argument("--package", action="append", choices=PACKAGES.values(), help="Limit missing Python installs")
    setup.add_argument("--install-epubcheck", action="store_true", help="Approve this EPUBCheck installation")
    setup.add_argument("--brew-formula", action="append", default=[], metavar="PACKAGE=FORMULA")
    setup.add_argument("--checker-manager", choices=("homebrew", "official", "manual"))
    for name in ("run", "python"):
        commands.add_parser(name, add_help=False).add_argument("args", nargs=argparse.REMAINDER)
    # Forward downstream flags verbatim, including python -c and CLI --help.
    forwarded = sys.argv[1:2] in (["run"], ["python"])
    args = parser.parse_args(sys.argv[1:2] if forwarded else None)
    with settings_lock():
        path = ROOT / "settings.json"
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        tools = discover(settings)
        if args.command == "configure":
            updates = {"auto_install": args.auto_install == "yes", "platform": args.platform.strip() or "general"}
            if args.brew_formula:
                formulas = dict(settings.get("brew_formulas", {}))
                for mapping in args.brew_formula:
                    package, _, formula = mapping.partition("=")
                    if package not in PACKAGES.values() or not re.fullmatch(
                        r"[a-z0-9][a-z0-9@+._-]*(/[a-z0-9][a-z0-9@+._-]*){0,2}", formula
                    ):
                        parser.error("Expected --brew-formula PACKAGE=FORMULA")
                    formulas[package] = formula
                updates["brew_formulas"] = formulas
            if args.dedicated_venv:
                if args.dedicated_venv == "yes" and not dedicated_venv():
                    parser.error("--dedicated-venv yes requires a standalone virtual environment")
                updates["dedicated_interpreter"] = sys.executable if args.dedicated_venv == "yes" else None
            for key in ("python_manager", "checker_manager"):
                if value := getattr(args, key):
                    updates[key] = value
            if args.auto_install == "yes":
                if not (args.package or args.install_epubcheck):
                    parser.error("Name each approved installation with --package or --install-epubcheck")
                if args.package and not args.python_manager:
                    parser.error("Choose --python-manager for this installation")
                if args.install_epubcheck and not args.checker_manager:
                    parser.error("Choose --checker-manager for this installation")
            elif args.package or args.install_epubcheck:
                parser.error("Installation requires --auto-install yes")
            if any(settings.get(k) != v for k, v in updates.items() if k != "platform"):
                settings["next_update_at"] = None
            settings.update(updates, update_interval_months=1)
            save(settings)
        if settings:
            approved = args.package or () if args.command == "configure" else ()
            install_checker_now = args.command == "configure" and args.install_epubcheck
            maintain(settings, tools, approved, install_checker_now)
            tools = discover(settings)
        if args.command == "status":
            active = settings.get("environment", {})
            if environment(settings) != Path(sys.executable):
                for package in active["packages"]:
                    if tools[package]["owner"] == "missing":
                        tools[package] = dict(owner=active["manager"], path=str(environment(settings)))
            print(
                json.dumps(
                    dict(
                        first_use=not settings,
                        interpreter=sys.executable,
                        platform=settings.get("platform"),
                        missing=[p for p, v in tools.items() if v["owner"] == "missing"],
                        tools=tools,
                        last_update_error=settings.get("last_update_error"),
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        if not settings:
            parser.exit(2, "First use: run status and configure reader preferences.\n")
        if not forwarded:
            if settings.get("last_update_error"):
                parser.exit(1, settings["last_update_error"] + "\n")
            return 0
        env = os.environ.copy()
        python = environment(settings)
        if (legacy := legacy_library(settings)) and python == Path(sys.executable):
            # Host packages take precedence over a compatible 1.2.0 fallback.
            paths = [p for p in sys.path if p and Path(p).name in {"site-packages", "dist-packages"}]
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [env.get("PYTHONPATH"), *paths, str(legacy)]))
        checker = tools["EPUBCheck"]
        if checker.get("jar"):
            env.update(BLACKFLAME_CHECKER_JAR=checker["jar"], BLACKFLAME_JAVA=checker["java"])
        cmd = [str(python)] + ([str(CLI)] if args.command == "run" else []) + sys.argv[2:]
        return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError, StopIteration, KeyError) as exc:
        sys.exit(f"blackflame: dependency setup failed: {exc}")
