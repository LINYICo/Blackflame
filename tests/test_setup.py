"""Unit tests for runtime detection, authorization boundaries, maintenance, and settings recovery."""

import io
import json
import sys
import threading
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "blackflame/scripts"))
import bootstrap
import maintenance
import runtime
import settings as settings_mod
import skill


def _fake_py_info(executable="/usr/bin/python3", version=(3, 13), abi="cpython-313", installed=None):
    installed = set(installed or ())
    pkgs = {}
    for module, package in runtime.PACKAGES.items():
        if package in installed:
            pkgs[package] = {
                "installed": True,
                "manager": "pip",
                "version": "1.0.0",
                "path": f"/site/{module}/__init__.py",
            }
        else:
            min_ver = runtime.PACKAGE_MIN_PYTHON.get(module, runtime.MIN_PYTHON)
            pkgs[package] = {"installed": False, "unsupported": tuple(version) < min_ver}
    return {
        "executable": executable,
        "version": list(version),
        "abi": abi,
        "prefix": "/usr",
        "base_prefix": "/usr",
        "site_packages": ["/site"],
        "packages": pkgs,
    }


class SettingsAndMigrationTests(unittest.TestCase):
    def test_month_end(self):
        for year, day in [(2027, 28), (2028, 29)]:
            start = datetime(year, 1, 31, 9, 15, tzinfo=UTC)
            self.assertEqual(settings_mod.next_month(start), start.replace(month=2, day=day))
        december = datetime(2026, 12, 22, tzinfo=UTC)
        self.assertEqual(settings_mod.next_month(december), december.replace(year=2027, month=1))

    def test_corrupt_settings_recovery_and_atomic_write(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "settings.json").write_text("{corrupt json", encoding="utf-8")
            loaded = settings_mod.load_settings(root=root, allow_migration=False, recover_corrupt=True)
            self.assertEqual(loaded, {})
            self.assertTrue((root / "settings.json.corrupt").is_file())
            settings_mod.save_settings({"platform": "Apple Books"}, root=root)
            reloaded = settings_mod.load_settings(root=root, allow_migration=False)
            self.assertEqual(reloaded["platform"], "Apple Books")
            self.assertEqual(reloaded["schema_version"], settings_mod.SETTINGS_VERSION)

    def test_legacy_epublib_settings_migration(self):
        with TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "epublib"
            legacy.mkdir()
            (legacy / "settings.json").write_text(
                json.dumps({"platform": "Kindle", "auto_install": False, "python_manager": "uv"}),
                encoding="utf-8",
            )
            migrated = settings_mod.migrate_legacy_settings(legacy_root=legacy)
            self.assertEqual(migrated["platform"], "Kindle")
            self.assertFalse(migrated["auto_install"])
            self.assertEqual(migrated["python_manager"], "uv")

    def test_concurrent_settings_writes_stay_valid_json(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            errors = []

            def worker(idx):
                try:
                    for step in range(5):
                        with settings_mod.settings_lock(root):
                            data = settings_mod.load_settings(root=root, allow_migration=False)
                            data[f"k_{idx}"] = step
                            settings_mod.save_settings(data, root=root)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            final = settings_mod.load_settings(root=root, allow_migration=False)
            for i in range(4):
                self.assertEqual(final[f"k_{i}"], 4)


class RuntimeDiscoveryTests(unittest.TestCase):
    def test_python_formula_does_not_own_pip_packages(self):
        with TemporaryDirectory() as tmp:
            cellar = Path(tmp).resolve()
            for formula in ["python@3.13", "epubcheck"]:
                keg = cellar / formula / "1.0"
                keg.mkdir(parents=True)
                (keg / "INSTALL_RECEIPT.json").touch()
                owner = runtime.formula_owner(keg / "lib/file", cellar)
                self.assertEqual(owner, None if formula.startswith("python@") else formula)

    def test_select_python_with_multiple_versions(self):
        py39 = _fake_py_info("/usr/bin/python3", version=(3, 9), abi="cpython-39")
        py313 = _fake_py_info("/opt/python3.13/bin/python3", version=(3, 13), abi="cpython-313")
        with (
            patch.object(
                runtime,
                "find_executable",
                side_effect=lambda n: "/opt/python3.13/bin/python3" if n == "python3.13" else None,
            ),
            patch.object(runtime, "probe_python", side_effect=lambda p: py313 if "3.13" in str(p) else py39),
        ):
            selected = runtime.select_python(preferred="/usr/bin/python3")
            self.assertIsNotNone(selected)
            self.assertEqual(selected["version"], [3, 13])

    def test_abi_mismatch_does_not_reuse_managed_venv(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_dir = root / "env-old" / "bin"
            env_dir.mkdir(parents=True)
            (env_dir / "python").touch()
            settings = {
                "environment": {
                    "directory": "env-old",
                    "interpreter": "/usr/bin/python3",
                    "python_version": "3.12",
                    "abi": "cpython-312",
                    "packages": ["lxml"],
                }
            }
            py313 = _fake_py_info("/usr/bin/python3", version=(3, 13), abi="cpython-313")
            with patch.object(settings_mod, "ROOT", root):
                chosen = runtime.environment(settings, py313)
                self.assertEqual(chosen, Path("/usr/bin/python3"))

    def test_unsupported_dependency_on_older_python(self):
        py311 = _fake_py_info("/usr/bin/python3.11", version=(3, 11), abi="cpython-311", installed=["lxml"])
        with (
            patch.object(runtime, "brew_cellar", return_value=None),
            patch.object(runtime, "find_executable", return_value=None),
            patch.object(runtime, "select_python", return_value=py311),
        ):
            tools, _ = runtime.discover({})
            self.assertEqual(tools["lxml"]["owner"], "pip")
            self.assertEqual(tools["epublib"]["owner"], "unsupported")
            self.assertEqual(tools["ebook-convert"]["owner"], "unsupported")


class BootstrapAndStatusTests(unittest.TestCase):
    def test_first_use_status_is_strictly_read_only(self):
        py313 = _fake_py_info(installed=["lxml"])
        with (
            TemporaryDirectory() as tmp,
            patch.object(settings_mod, "ROOT", Path(tmp)),
            patch.object(runtime, "brew_cellar", return_value=None),
            patch.object(runtime, "find_executable", return_value=None),
            patch.object(runtime, "select_python", return_value=py313),
            patch.object(bootstrap, "setup_environment") as setup_call,
            patch.object(bootstrap, "install_homebrew") as brew_call,
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = skill.main(["status"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["first_use"])
            self.assertFalse((Path(tmp) / "settings.json").exists())
            setup_call.assert_not_called()
            brew_call.assert_not_called()

    def test_existing_complete_environment_without_homebrew_never_installs_homebrew(self):
        py313 = _fake_py_info(installed=runtime.PACKAGES.values())
        tools = {
            "Homebrew": {"owner": "missing"},
            "Python": {"owner": "external", "path": py313["executable"], "version": "3.13", "abi": "cpython-313"},
            "uv": {"owner": "external", "path": "/usr/local/bin/uv"},
            "EPUBCheck": {"owner": "external", "path": "/usr/local/bin/epubcheck"},
            **{p: {"owner": "pip", "path": f"/site/{p}"} for p in runtime.PACKAGES.values()},
        }
        settings = {}
        with (
            patch.object(bootstrap, "install_homebrew") as inst_brew,
            patch.object(bootstrap, "install_python") as inst_py,
            patch.object(bootstrap, "ensure_private_packages") as priv_pkg,
            patch.object(runtime, "discover", return_value=(tools, py313)),
        ):
            bootstrap.setup_environment(
                settings,
                tools,
                py313,
                allow_system_install=False,
                packages=list(runtime.PACKAGES.values()),
                install_epubcheck=True,
            )
            inst_brew.assert_not_called()
            inst_py.assert_not_called()
            priv_pkg.assert_not_called()

    def test_unauthorized_system_install_is_blocked(self):
        tools = {
            "Homebrew": {"owner": "missing"},
            "Python": {"owner": "missing"},
            "uv": {"owner": "missing"},
            "EPUBCheck": {"owner": "missing"},
            **{p: {"owner": "missing"} for p in runtime.PACKAGES.values()},
        }
        with patch.object(bootstrap, "install_homebrew") as inst_brew:
            with self.assertRaisesRegex(RuntimeError, "allow-system-install"):
                bootstrap.setup_environment({}, tools, None, allow_system_install=False)
            inst_brew.assert_not_called()


class MaintenanceAndOfflineTests(unittest.TestCase):
    def test_shared_and_homebrew_tools_are_not_modified_during_maintenance(self):
        tools = {p: {"owner": "pip", "path": "/shared/site-packages"} for p in runtime.PACKAGES.values()}
        tools["EPUBCheck"] = {"owner": "homebrew", "path": "/opt/homebrew/bin/epubcheck", "formula": "epubcheck"}
        settings = {"auto_install": True, "platform": "general"}
        with (
            TemporaryDirectory() as tmp,
            patch.object(settings_mod, "ROOT", Path(tmp)),
            patch.object(bootstrap, "run_quietly") as cmd,
            patch.object(bootstrap, "make_environment") as mk,
        ):
            maintenance.maintain(settings, tools, _fake_py_info(), force=True)
            cmd.assert_not_called()
            mk.assert_not_called()
            self.assertNotIn("last_update_error", settings)

    def test_private_update_failure_preserves_working_environment_offline(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_env_dir = root / "env-working" / "bin"
            old_env_dir.mkdir(parents=True)
            (old_env_dir / "python").touch()
            py313 = _fake_py_info("/usr/bin/python3", version=(3, 13), abi="cpython-313")
            settings = {
                "platform": "general",
                "environment": {
                    "directory": "env-working",
                    "interpreter": "/usr/bin/python3",
                    "python_version": "3.13",
                    "abi": "cpython-313",
                    "manager": "uv",
                    "packages": ["lxml"],
                },
                "next_update_at": "2000-01-01T00:00:00+00:00",
            }
            tools = {p: {"owner": "managed"} for p in runtime.PACKAGES.values()}
            tools["EPUBCheck"] = {"owner": "external", "path": "/usr/bin/epubcheck"}
            with (
                patch.object(settings_mod, "ROOT", root),
                patch.object(bootstrap, "make_environment", side_effect=RuntimeError("offline: no network")),
            ):
                updated = maintenance.maintain(settings, tools, py313)
                self.assertFalse(updated)
                self.assertIn("offline", settings["last_update_error"])
                # Previous working environment must remain intact and active!
                self.assertEqual(settings["environment"]["directory"], "env-working")
                self.assertTrue((root / "env-working" / "bin" / "python").is_file())
                self.assertEqual(runtime.environment(settings, py313), root / "env-working" / "bin" / "python")
