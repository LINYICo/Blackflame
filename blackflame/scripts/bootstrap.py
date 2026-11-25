"""Environment bootstrap, private venv creation, dependency merging, and authorized tool setup."""

import json
import os
import shutil
import subprocess
import sys
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZipFile

import runtime
import settings as settings_mod


def run_quietly(args, extra_env=None):
    """Run a subprocess quietly without inheriting global pip/uv target overrides."""
    env = os.environ.copy()
    env["PATH"] = runtime.search_path()
    for key in ("PIP_TARGET", "PIP_PREFIX", "PIP_USER", "UV_TARGET", "UV_PREFIX", "UV_SYSTEM_PYTHON"):
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
    except OSError as exc:
        raise RuntimeError(f"Failed to execute {args[0]}: {exc}") from exc
    if proc.returncode:
        output = proc.stdout.strip()[-1800:]
        raise RuntimeError(output or f"{args[0]} exited with status {proc.returncode}")


def install_checker(dest):
    """Download and SHA-256-verify the latest official EPUBCheck release JAR."""
    try:
        with urlopen("https://api.github.com/repos/w3c/epubcheck/releases/latest", timeout=45) as response:
            release = json.load(response)
    except (URLError, OSError) as exc:
        raise RuntimeError(f"Offline or unable to reach EPUBCheck releases: {exc}") from exc
    name = f"epubcheck-{release['tag_name'].removeprefix('v')}"
    asset = next(a for a in release["assets"] if a["name"] == name + ".zip")
    with TemporaryDirectory(dir=dest) as tmp:
        bundle = Path(tmp) / "release.zip"
        try:
            with urlopen(asset["browser_download_url"], timeout=120) as response, bundle.open("wb") as out:
                shutil.copyfileobj(response, out)
        except (URLError, OSError) as exc:
            raise RuntimeError(f"Offline or failed to download EPUBCheck archive: {exc}") from exc
        with bundle.open("rb") as stream:
            if "sha256:" + file_digest(stream, "sha256").hexdigest() != asset.get("digest"):
                raise ValueError("EPUBCheck release digest mismatch")
        with ZipFile(bundle) as archive:
            for item in archive.namelist():
                path = Path(item)
                if path.parts[:1] == (name,) and ".." not in path.parts and path.suffix == ".jar":
                    archive.extract(item, dest)
    return dest / name / "epubcheck.jar"


def stage_official_checker():
    """Download and verify the official EPUBCheck JAR without mutating settings yet."""
    java = runtime.java_executable()
    if not java:
        raise RuntimeError("Official EPUBCheck requires an existing Java runtime")
    settings_mod.ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    with TemporaryDirectory(dir=settings_mod.ROOT) as tmp:
        jar = install_checker(Path(tmp))
        run_quietly([java, "-jar", str(jar), "--version"])
        parent = settings_mod.ROOT / "checker" / jar.parent.name
        parent.parent.mkdir(exist_ok=True)
        if not parent.exists():
            jar.parent.rename(parent)
        return dict(java=java, jar=str(parent / jar.name))


def install_official_checker(settings):
    settings["checker"] = stage_official_checker()
    return settings["checker"]


def install_homebrew():
    if sys.platform == "win32":
        return None
    run_quietly(
        [
            "/bin/bash",
            "-c",
            "curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | /bin/bash",
        ],
        extra_env={"NONINTERACTIVE": "1"},
    )
    brew = runtime.find_executable("brew")
    runtime.ensure_on_path(brew)
    return brew


def install_python(brew, uv_exe):
    if uv_exe:
        run_quietly([uv_exe, "python", "install", "3.13"])
    elif brew:
        run_quietly([brew, "install", "--quiet", "python"], extra_env={"HOMEBREW_NO_AUTO_UPDATE": "1"})
    info = runtime.select_python()
    if info:
        runtime.ensure_on_path(info["executable"])
    return info


def install_uv(brew):
    if brew:
        run_quietly([brew, "install", "--quiet", "uv"], extra_env={"HOMEBREW_NO_AUTO_UPDATE": "1"})
    elif sys.platform != "win32":
        run_quietly(["/bin/sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"])
    uv_exe = runtime.find_executable("uv")
    runtime.ensure_on_path(uv_exe)
    return uv_exe


def _compatible_packages(packages, py_version):
    result = []
    seen = set()
    pkg_to_mod = {pkg: mod for mod, pkg in runtime.PACKAGES.items()}
    for pkg in packages:
        if pkg in seen:
            continue
        mod = pkg_to_mod.get(pkg)
        min_ver = runtime.PACKAGE_MIN_PYTHON.get(mod, runtime.MIN_PYTHON) if mod else runtime.MIN_PYTHON
        if tuple(py_version) >= min_ver:
            seen.add(pkg)
            result.append(pkg)
    return result


def make_environment(settings, packages, dest, py_info=None, *, upgrade=False):
    """Create and verify a skill-private venv, reusing host site-packages only when ABI & arch match."""
    method = settings.get("python_manager")
    if method == "manual":
        raise RuntimeError("Python package management is set to manual; automatic installation is disabled")
    if not method:
        method = "uv" if runtime.find_executable("uv") else "pip"

    info = py_info or runtime.select_python()
    if not info:
        raise RuntimeError("No compatible Python >= 3.11 interpreter found")
    base_python = info["executable"]
    python = runtime.env_python(dest)
    if method == "uv" and (uv_exe := runtime.find_executable("uv")):
        run_quietly([uv_exe, "venv", "--python", base_python, str(dest)])
        install = [uv_exe, "pip", "install", "--python", str(python)]
    else:
        method = "pip"
        run_quietly([base_python, "-m", "venv", str(dest)])
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

    # Verify the new venv matches the selected interpreter's version, ABI, and CPU architecture.
    venv_info = runtime.probe_python(str(python))
    if not venv_info:
        raise RuntimeError("Created virtual environment failed Python probe")
    if (
        venv_info["abi"] == info["abi"]
        and venv_info["version"] == info["version"]
        and venv_info["arch"] == info["arch"]
    ):
        paths = list(info.get("site_packages", []))
        if legacy := runtime.legacy_library(settings, venv_info["abi"]):
            paths.append(str(legacy))
        if paths:
            target = subprocess.check_output(
                [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                text=True,
            ).strip()
            (Path(target) / "blackflame-host.pth").write_text("\n".join(paths) + "\n", encoding="utf-8")

    cmd = [*install, *(["--upgrade"] if upgrade else []), *packages]
    run_quietly(cmd)

    # Verify every installed package is genuinely importable (including lxml.etree).
    modules = [module for module, package in runtime.PACKAGES.items() if package in packages]
    if modules:
        verify_lines = [f"import {m}" for m in modules]
        if "lxml" in modules:
            verify_lines.append("from lxml import etree")
        run_quietly([str(python), "-c", "; ".join(verify_lines)])

    return dict(
        directory=dest.name,
        interpreter=base_python,
        python_version=".".join(str(v) for v in venv_info["version"]),
        abi=venv_info["abi"],
        arch=venv_info["arch"],
        manager=method,
        packages=list(packages),
    )


def merge_private_packages(settings, requested, py_info):
    """Merge existing managed packages with newly requested ones, skipping host-satisfied or unsupported ones."""
    existing = list(settings.get("environment", {}).get("packages", []))
    combined = _compatible_packages([*existing, *requested], py_info["version"])
    # Do not duplicate packages already safely installed and importable in the host interpreter.
    needed = []
    for pkg in combined:
        host_pkg = py_info["packages"].get(pkg, {})
        if not (host_pkg.get("installed") and host_pkg.get("importable")):
            needed.append(pkg)
    return needed


def stage_private_packages(settings, packages, py_info, *, upgrade=False):
    """Build and verify a new skill-private venv in a temp dir without mutating settings or removing old env."""
    merged = merge_private_packages(settings, packages, py_info)
    if not merged:
        return None, None
    settings_mod.ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    dest = Path(mkdtemp(prefix="env-", dir=settings_mod.ROOT))
    try:
        new_env = make_environment(settings, merged, dest, py_info=py_info, upgrade=upgrade)
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return new_env, dest


def ensure_private_packages(settings, packages, py_info):
    """Transactionally build, verify, and stage a private venv preserving prior managed packages."""
    old_env_py = runtime.environment(settings, py_info)
    old_env_dir = old_env_py.parent.parent if old_env_py != Path(py_info["executable"]) else None
    new_env, _ = stage_private_packages(settings, packages, py_info, upgrade=False)
    if not new_env:
        return None
    settings["environment"] = new_env
    return old_env_dir


def setup_environment(
    settings,
    tools,
    py_info,
    *,
    allow_system_install=False,
    packages=None,
    install_epubcheck=False,
):
    """Reuse existing host tools; install only missing items within authorized boundaries.

    Returns (tools, py_info, old_env_dir_to_clean) so callers can persist settings first
    and safely remove any superseded environment only after commit succeeds.
    """
    brew = tools["Homebrew"].get("path")
    uv_exe = tools["uv"].get("path")
    need_python = tools["Python"]["owner"] == "missing"
    need_checker = install_epubcheck and tools["EPUBCheck"]["owner"] in ("missing", "broken")

    # Never install Homebrew if existing Python/uv/EPUBCheck already satisfy requirements.
    need_system_tool = need_python or (need_checker and not runtime.java_executable())
    if not brew and need_system_tool and sys.platform != "win32":
        if not allow_system_install:
            raise RuntimeError(
                "System-level installation (Homebrew/Python/EPUBCheck) requires explicit authorization "
                "(--allow-system-install)"
            )
        brew = install_homebrew()

    if need_python:
        if not allow_system_install and not uv_exe:
            raise RuntimeError("Installing Python requires explicit authorization (--allow-system-install)")
        py_info = install_python(brew, uv_exe)
        if not py_info:
            raise RuntimeError("Python >= 3.11 installation completed but no compatible interpreter was found")
        tools, py_info = runtime.discover(settings, preferred_python=py_info["executable"])

    if not uv_exe and allow_system_install and brew:
        uv_exe = install_uv(brew)

    if need_checker:
        checker_method = settings.get("checker_manager") or ("homebrew" if brew else "official")
        if checker_method == "homebrew":
            if not allow_system_install:
                raise RuntimeError("Installing EPUBCheck via Homebrew requires --allow-system-install")
            if not brew:
                brew = install_homebrew()
            run_quietly([brew, "install", "--quiet", "epubcheck"], extra_env={"HOMEBREW_NO_AUTO_UPDATE": "1"})
            if exe := runtime.find_executable("epubcheck"):
                runtime.ensure_on_path(exe)
            else:
                raise RuntimeError("Homebrew installed EPUBCheck but it is unavailable on PATH")
        elif checker_method == "official":
            install_official_checker(settings)
        else:
            raise RuntimeError("EPUBCheck is set to manual management")

    settings.setdefault("auto_install", True)
    settings.setdefault("platform", "general")
    settings.setdefault("python_manager", "uv" if uv_exe else "pip")
    settings.setdefault("checker_manager", "homebrew" if brew else "official")
    settings.setdefault("update_interval_months", 1)

    old_env_dir = None
    target_packages = list(packages) if packages is not None else []
    missing_or_broken = [p for p in target_packages if tools.get(p, {}).get("owner") in ("missing", "broken")]
    if missing_or_broken:
        if settings.get("python_manager") == "manual":
            raise RuntimeError(
                f"Missing packages ({', '.join(missing_or_broken)}) while python_manager is set to manual"
            )
        old_env_dir = ensure_private_packages(settings, missing_or_broken, py_info)

    tools, py_info = runtime.discover(settings, preferred_python=py_info["executable"] if py_info else None)
    return tools, py_info, old_env_dir
