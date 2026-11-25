"""Read-only runtime, interpreter, tool, and dependency discovery for Blackflame."""

import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
from importlib import metadata
from importlib.machinery import PathFinder
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

_PROBE_SCRIPT = """
import importlib
import json
import os
import platform
import sys
from importlib import metadata
from pathlib import Path

pkgs = json.loads(sys.argv[1])
mins = {k: tuple(v) for k, v in json.loads(sys.argv[2]).items()}
out = {}

for mod_name, pkg_name in pkgs.items():
    min_ver = mins.get(mod_name, (3, 11))
    version = None
    manager = "external"
    try:
        dist = metadata.distribution(pkg_name)
        version = dist.version
        manager = (dist.read_text("INSTALLER") or "").strip() or "external"
    except metadata.PackageNotFoundError:
        dist = None

    import_ok = False
    origin = None
    import_error = None
    try:
        mod = importlib.import_module(mod_name)
        if mod_name == "lxml":
            from lxml import etree  # noqa: F401
        origin = getattr(mod, "__file__", None)
        import_ok = True
    except Exception as exc:
        import_error = f"{type(exc).__name__}: {exc}"

    if import_ok and origin:
        out[pkg_name] = {
            "installed": True,
            "importable": True,
            "manager": manager,
            "version": version,
            "path": origin,
        }
    elif dist is not None and not import_ok:
        out[pkg_name] = {
            "installed": False,
            "importable": False,
            "broken": True,
            "version": version,
            "error": import_error,
        }
    else:
        out[pkg_name] = {
            "installed": False,
            "importable": False,
            "unsupported": sys.version_info[:2] < min_ver,
        }

print(json.dumps({
    "executable": os.path.abspath(sys.executable),
    "real_executable": os.path.realpath(sys.executable),
    "version": [sys.version_info[0], sys.version_info[1]],
    "abi": sys.implementation.cache_tag,
    "arch": platform.machine(),
    "prefix": os.path.abspath(sys.prefix),
    "base_prefix": os.path.abspath(sys.base_prefix),
    "site_packages": [p for p in sys.path if p and Path(p).name in {"site-packages", "dist-packages"}],
    "packages": out,
}))
"""


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
        version = None
        manager = "external"
        try:
            dist = metadata.distribution(package)
            version = dist.version
            manager = (dist.read_text("INSTALLER") or "").strip() or "external"
        except metadata.PackageNotFoundError:
            dist = None

        import_ok = False
        origin = None
        import_error = None
        try:
            mod = importlib.import_module(module)
            if module == "lxml":
                from lxml import etree  # noqa: F401
            origin = getattr(mod, "__file__", None)
            import_ok = True
        except Exception as exc:
            import_error = f"{type(exc).__name__}: {exc}"

        if import_ok and origin:
            pkgs[package] = {
                "installed": True,
                "importable": True,
                "manager": manager,
                "version": version,
                "path": origin,
            }
        elif dist is not None and not import_ok:
            pkgs[package] = {
                "installed": False,
                "importable": False,
                "broken": True,
                "version": version,
                "error": import_error,
            }
        else:
            pkgs[package] = {
                "installed": False,
                "importable": False,
                "unsupported": sys.version_info[:2] < min_ver,
            }
    return {
        "executable": os.path.abspath(sys.executable),
        "real_executable": os.path.realpath(sys.executable),
        "version": [sys.version_info[0], sys.version_info[1]],
        "abi": sys.implementation.cache_tag,
        "arch": platform.machine(),
        "prefix": os.path.abspath(sys.prefix),
        "base_prefix": os.path.abspath(sys.base_prefix),
        "site_packages": [p for p in sys.path if p and Path(p).name in {"site-packages", "dist-packages"}],
        "packages": pkgs,
    }


def probe_python(executable):
    """Inspect version, ABI, arch, prefix, site-packages, and real importability of a Python executable.

    Uses os.path.abspath (not Path.resolve) so distinct virtualenvs symlinking to the same
    base Python binary are always probed separately in their own subprocess.
    """
    if not executable:
        return None
    invoked = os.path.abspath(str(executable))
    if invoked == os.path.abspath(sys.executable):
        return _probe_current_python()
    if not Path(invoked).is_file():
        return None
    try:
        proc = subprocess.run(
            [
                invoked,
                "-c",
                _PROBE_SCRIPT,
                json.dumps(PACKAGES),
                json.dumps({k: list(v) for k, v in PACKAGE_MIN_PYTHON.items()}),
            ],
            capture_output=True,
            text=True,
            timeout=25,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    try:
        info = json.loads(proc.stdout)
        info["executable"] = invoked
        return info
    except ValueError:
        return None


def _uv_managed_pythons():
    uv_exe = find_executable("uv")
    if not uv_exe:
        return []
    try:
        proc = subprocess.run([uv_exe, "python", "find", ">=3.11"], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0 and proc.stdout.strip():
            return [proc.stdout.strip()]
    except OSError:
        pass
    return []


def select_python(preferred=None, *, strict_preferred=False):
    """Select a compatible Python >= MIN_PYTHON.

    When strict_preferred is True (explicit --python), fail with a clear diagnostic
    instead of silently falling back to a different interpreter.
    """
    if preferred:
        info = probe_python(preferred)
        if info and tuple(info["version"]) >= MIN_PYTHON:
            return info
        if strict_preferred:
            if not Path(preferred).exists():
                raise RuntimeError(f"Specified Python interpreter does not exist: {preferred}")
            if not info:
                raise RuntimeError(f"Specified Python interpreter could not be executed: {preferred}")
            ver = ".".join(str(v) for v in info["version"])
            raise RuntimeError(f"Specified Python interpreter {preferred} (v{ver}) is older than required 3.11")

    candidates = [sys.executable]
    for name in ("python3.15", "python3.14", "python3.13", "python3.12", "python3.11", "python3"):
        if exe := find_executable(name):
            candidates.append(exe)
    candidates.extend(_uv_managed_pythons())

    seen = set()
    for candidate in candidates:
        key = os.path.abspath(str(candidate))
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
    """Return the managed venv Python only when interpreter, prefix, version, ABI, and arch match."""
    active = settings.get("environment", {})
    name = active.get("directory", "")
    info = python_info or _probe_current_python()
    current_exe = info["executable"]
    current_abi = info["abi"]
    current_arch = info.get("arch") or platform.machine()
    current_ver = ".".join(str(v) for v in info["version"])
    if (
        Path(name).name == name
        and name.startswith("env-")
        and os.path.abspath(active.get("interpreter", "")) == os.path.abspath(current_exe)
        and active.get("abi") == current_abi
        and active.get("arch", current_arch) == current_arch
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


def discover(settings, preferred_python=None, *, strict_preferred=False):
    """Read-only inspection of host tools and dependencies using the selected Python interpreter."""
    cellar = brew_cellar()
    tools = {}
    brew = find_executable("brew")
    tools["Homebrew"] = dict(owner="homebrew", path=brew) if brew else dict(owner="missing")

    effective_preferred = preferred_python or settings.get("preferred_python")
    py_info = select_python(effective_preferred, strict_preferred=strict_preferred)
    if py_info:
        py_formula = formula_owner(py_info["real_executable"], cellar)
        tools["Python"] = dict(
            owner="homebrew" if py_formula else "external",
            path=py_info["executable"],
            prefix=py_info["prefix"],
            version=".".join(str(v) for v in py_info["version"]),
            abi=py_info["abi"],
            arch=py_info["arch"],
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
        probe_python(str(managed_py))
        if managed_py and py_info and os.path.abspath(str(managed_py)) != os.path.abspath(py_info["executable"])
        else None
    )
    legacy = legacy_library(settings, py_info["abi"] if py_info else None)

    for module, package in PACKAGES.items():
        tier = "core" if module in CORE_PACKAGES else "optional"
        pkg_data = py_info["packages"].get(package, {}) if py_info else {}
        managed_pkg = managed_info["packages"].get(package, {}) if managed_info else {}
        if pkg_data.get("installed") and pkg_data.get("importable"):
            formula = formula_owner(pkg_data["path"], cellar)
            tools[package] = dict(
                owner="homebrew" if formula else pkg_data["manager"],
                formula=formula,
                version=pkg_data["version"],
                path=pkg_data["path"],
                tier=tier,
            )
        elif managed_pkg.get("installed") and managed_pkg.get("importable"):
            tools[package] = dict(
                owner="managed",
                version=managed_pkg["version"],
                path=managed_pkg["path"],
                tier=tier,
            )
        elif pkg_data.get("broken"):
            tools[package] = dict(
                owner="broken",
                version=pkg_data.get("version"),
                error=pkg_data.get("error"),
                tier=tier,
            )
        elif legacy and PathFinder.find_spec(module, [str(legacy)]):
            tools[package] = dict(owner="legacy", path=str(legacy), tier=tier)
        else:
            status = "unsupported" if pkg_data.get("unsupported") else "missing"
            tools[package] = dict(owner=status, tier=tier)

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
    elif managed.get("jar"):
        checker = dict(owner="broken", jar=managed["jar"], error="Managed EPUBCheck JAR is missing or corrupted")
    else:
        checker = dict(owner="missing")
    tools["EPUBCheck"] = checker
    return tools, py_info
