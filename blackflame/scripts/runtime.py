"""Read-only runtime, interpreter, tool, and dependency discovery for Blackflame."""

import json
import os
import shutil
import subprocess
import sys
from importlib import metadata
from importlib.machinery import PathFinder
from importlib.util import find_spec
from pathlib import Path

import settings as settings_mod

MIN_PYTHON = (3, 11)
COMMON_BIN_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/home/linuxbrew/.linuxbrew/bin",
    str(Path.home() / ".local/bin"),
)
CORE_PACKAGES = {"lxml": "lxml"}
OPTIONAL_PACKAGES = {
    "bs4": "beautifulsoup4",
    "epublib": "epublib",
    "ebook_convert": "ebook-convert",
}
PACKAGES = {**CORE_PACKAGES, **OPTIONAL_PACKAGES}
PACKAGE_MIN_PYTHON = {
    "epublib": (3, 13),
    "ebook_convert": (3, 12),
}


def search_path():
    entries = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    for directory in COMMON_BIN_DIRS:
        if directory not in entries and Path(directory).is_dir():
            entries.append(directory)
    return os.pathsep.join(entries)


def find_executable(name):
    return shutil.which(name, path=search_path())


def ensure_on_path(executable):
    if not executable:
        return
    directory = str(Path(executable).parent)
    entries = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    if directory not in entries:
        os.environ["PATH"] = os.pathsep.join([directory, *entries]) if entries else directory


def java_executable():
    candidates = []
    if os.environ.get("JAVA_HOME"):
        candidates.append(str(Path(os.environ["JAVA_HOME"]) / "bin" / "java"))
    candidates += [find_executable("java"), "/opt/homebrew/opt/openjdk/bin/java", "/usr/local/opt/openjdk/bin/java"]
    for java in candidates:
        if java and Path(java).is_file() and subprocess.run([java, "-version"], capture_output=True).returncode == 0:
            return java
    return None


def brew_cellar():
    if brew := find_executable("brew"):
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


def _probe_current_python():
    pkgs = {}
    for module, package in PACKAGES.items():
        min_ver = PACKAGE_MIN_PYTHON.get(module, MIN_PYTHON)
        try:
            dist = metadata.distribution(package)
            spec = find_spec(module)
        except metadata.PackageNotFoundError:
            spec = None
        if spec and spec.origin:
            manager = (dist.read_text("INSTALLER") or "").strip() or "external"
            pkgs[package] = {
                "installed": True,
                "manager": manager,
                "version": dist.version,
                "path": spec.origin,
            }
        else:
            pkgs[package] = {
                "installed": False,
                "unsupported": sys.version_info[:2] < min_ver,
            }
    return {
        "executable": sys.executable,
        "version": [sys.version_info[0], sys.version_info[1]],
        "abi": sys.implementation.cache_tag,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "site_packages": [p for p in sys.path if p and Path(p).name in {"site-packages", "dist-packages"}],
        "packages": pkgs,
    }


def probe_python(executable):
    """Inspect version, ABI, site-packages, and package availability of a specific Python interpreter."""
    if not executable:
        return None
    try:
        if Path(executable).resolve() == Path(sys.executable).resolve():
            return _probe_current_python()
    except OSError:
        pass
    snippet = (
        "import json, sys; from importlib import metadata; from importlib.util import find_spec; "
        "from pathlib import Path; "
        f"pkgs = {PACKAGES!r}; mins = {PACKAGE_MIN_PYTHON!r}; out = {{}}; "
        "for m, p in pkgs.items():\n"
        "  try:\n"
        "    d = metadata.distribution(p); s = find_spec(m)\n"
        "  except metadata.PackageNotFoundError:\n"
        "    s = None\n"
        "  if s and s.origin:\n"
        "    out[p] = {'installed': True, 'manager': (d.read_text('INSTALLER') or '').strip() or 'external', "
        "'version': d.version, 'path': s.origin}\n"
        "  else:\n"
        "    out[p] = {'installed': False, 'unsupported': sys.version_info[:2] < mins.get(m, (3, 11))}\n"
        "print(json.dumps({'executable': sys.executable, 'version': [sys.version_info[0], sys.version_info[1]], "
        "'abi': sys.implementation.cache_tag, 'prefix': sys.prefix, 'base_prefix': sys.base_prefix, "
        "'site_packages': [p for p in sys.path if p and Path(p).name in {'site-packages', 'dist-packages'}], "
        "'packages': out}))"
    )
    try:
        proc = subprocess.run([str(executable), "-c", snippet], capture_output=True, text=True, timeout=20)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def select_python(preferred=None):
    """Select the best available Python >= MIN_PYTHON, preferring the active interpreter."""
    candidates = []
    if preferred:
        candidates.append(str(preferred))
    candidates.append(sys.executable)
    for name in ("python3.15", "python3.14", "python3.13", "python3.12", "python3.11", "python3"):
        if exe := find_executable(name):
            candidates.append(exe)
    seen = set()
    for candidate in candidates:
        try:
            key = str(Path(candidate).resolve())
        except OSError:
            key = candidate
        if key in seen:
            continue
        seen.add(key)
        info = probe_python(candidate)
        if info and tuple(info["version"]) >= MIN_PYTHON:
            return info
    return None


def legacy_library(settings, abi=None):
    runtime = settings.get("runtime", {})
    name = runtime.get("directory", "")
    target_abi = abi or sys.implementation.cache_tag
    if Path(name).name == name and name.startswith("runtime-") and runtime.get("python_abi") == target_abi:
        return settings_mod.ROOT / name / "python"
    return None


def env_python(directory):
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def environment(settings, python_info=None):
    """Return the managed venv Python only when its interpreter, version, and ABI match."""
    active = settings.get("environment", {})
    name = active.get("directory", "")
    info = python_info or _probe_current_python()
    current_exe = info["executable"]
    current_abi = info["abi"]
    current_ver = ".".join(str(v) for v in info["version"])
    if (
        Path(name).name == name
        and name.startswith("env-")
        and active.get("interpreter") == current_exe
        and active.get("abi") == current_abi
        and active.get("python_version", current_ver) == current_ver
        and env_python(settings_mod.ROOT / name).is_file()
    ):
        return env_python(settings_mod.ROOT / name)
    return Path(current_exe)


def dedicated_venv(python_info=None):
    info = python_info or _probe_current_python()
    prefix = Path(info["prefix"])
    if info["prefix"] == info["base_prefix"] or not (prefix / "pyvenv.cfg").is_file():
        return False
    markers = ("pyproject.toml", "uv.lock", "poetry.lock", "Pipfile", "conda-meta")
    return not any((parent / marker).exists() for parent in [prefix, *prefix.parents] for marker in markers)


def discover(settings, preferred_python=None):
    """Read-only inspection of host tools and dependencies using the selected Python interpreter."""
    cellar = brew_cellar()
    tools = {}
    brew = find_executable("brew")
    tools["Homebrew"] = dict(owner="homebrew", path=brew) if brew else dict(owner="missing")

    py_info = select_python(preferred_python)
    if py_info:
        py_formula = formula_owner(py_info["executable"], cellar)
        tools["Python"] = dict(
            owner="homebrew" if py_formula else "external",
            path=py_info["executable"],
            version=".".join(str(v) for v in py_info["version"]),
            abi=py_info["abi"],
            formula=py_formula,
        )
    else:
        tools["Python"] = dict(owner="missing")

    uv_exe = find_executable("uv")
    if uv_exe:
        uv_formula = formula_owner(uv_exe, cellar)
        tools["uv"] = dict(owner="homebrew" if uv_formula else "external", path=uv_exe, formula=uv_formula)
    else:
        tools["uv"] = dict(owner="missing")

    managed_py = environment(settings, py_info) if py_info else None
    managed_info = (
        probe_python(str(managed_py)) if managed_py and py_info and str(managed_py) != py_info["executable"] else None
    )
    legacy = legacy_library(settings, py_info["abi"] if py_info else None)

    for module, package in PACKAGES.items():
        pkg_data = py_info["packages"].get(package, {}) if py_info else {}
        managed_pkg = managed_info["packages"].get(package, {}) if managed_info else {}
        if pkg_data.get("installed"):
            formula = formula_owner(pkg_data["path"], cellar)
            tools[package] = dict(
                owner="homebrew" if formula else pkg_data["manager"],
                formula=formula,
                version=pkg_data["version"],
                path=pkg_data["path"],
                tier="core" if module in CORE_PACKAGES else "optional",
            )
        elif managed_pkg.get("installed"):
            tools[package] = dict(
                owner="managed",
                version=managed_pkg["version"],
                path=managed_pkg["path"],
                tier="core" if module in CORE_PACKAGES else "optional",
            )
        elif legacy and PathFinder.find_spec(module, [str(legacy)]):
            tools[package] = dict(
                owner="legacy",
                path=str(legacy),
                tier="core" if module in CORE_PACKAGES else "optional",
            )
        else:
            status = "unsupported" if pkg_data.get("unsupported") else "missing"
            tools[package] = dict(owner=status, tier="core" if module in CORE_PACKAGES else "optional")

    exe = find_executable("epubcheck")
    jar = os.environ.get("BLACKFLAME_CHECKER_JAR")
    managed = settings.get("checker", {}) or settings.get("runtime", {})
    if jar and Path(jar).is_file():
        checker = dict(owner="external-jar", jar=jar, java=os.environ.get("BLACKFLAME_JAVA", "java"))
    elif exe:
        formula = formula_owner(exe, cellar)
        checker = dict(owner="homebrew" if formula else "external", path=exe, formula=formula)
    elif managed.get("jar") and Path(managed["jar"]).is_file():
        checker = dict(
            owner="official" if settings.get("checker") else "legacy",
            jar=managed["jar"],
            java=managed["java"],
        )
    else:
        checker = dict(owner="missing")
    tools["EPUBCheck"] = checker
    return tools, py_info
