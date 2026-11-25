import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "blackflame/scripts"))
import skill


class MaintenanceTests(unittest.TestCase):
    def test_month_end(self):
        for year, day in [(2027, 28), (2028, 29)]:
            start = datetime(year, 1, 31, 9, 15, tzinfo=UTC)
            self.assertEqual(skill.next_month(start), start.replace(month=2, day=day))
        december = datetime(2026, 12, 22, tzinfo=UTC)
        self.assertEqual(skill.next_month(december), december.replace(year=2027, month=1))

    def test_first_use_skip_and_retry(self):
        settings = {"auto_install": False, "platform": "general"}
        with (
            TemporaryDirectory() as tmp,
            patch.object(skill, "ROOT", Path(tmp)),
            patch.object(skill, "refresh") as update,
        ):
            skill.maintain(settings, {})
            first = settings["last_updated_at"]
            skill.maintain(settings, {})
            self.assertEqual(update.call_count, 1)
            settings["next_update_at"] = "2000-01-01T00:00:00+00:00"
            update.side_effect = RuntimeError("offline")
            skill.maintain(settings, {})
            self.assertEqual(settings["last_updated_at"], first)
            update.side_effect = None
            skill.maintain(settings, {})
            self.assertEqual(update.call_count, 3)
            self.assertNotIn("last_update_error", settings)
            self.assertEqual(json.loads((Path(tmp) / "settings.json").read_text()), settings)

    def test_python_formula_does_not_own_pip_packages(self):
        with TemporaryDirectory() as tmp:
            cellar = Path(tmp).resolve()
            for formula in ["python@3.13", "epubcheck"]:
                keg = cellar / formula / "1.0"
                keg.mkdir(parents=True)
                (keg / "INSTALL_RECEIPT.json").touch()
                owner = skill.formula_owner(keg / "lib/file", cellar)
                self.assertEqual(owner, None if formula.startswith("python@") else formula)

    def test_shared_python_and_unknown_checker_remain_external(self):
        tools = {p: {"owner": "pip", "path": "/shared/site-packages"} for p in skill.PACKAGES.values()}
        tools["EPUBCheck"] = {"owner": "external", "path": "/tools/epubcheck"}
        with patch.object(skill, "run_quietly") as command, patch.object(skill, "make_environment") as create:
            skill.refresh({"auto_install": True, "python_manager": "uv", "checker_manager": "official"}, tools)
            command.assert_not_called()
            create.assert_not_called()

    def test_saved_install_preference_does_not_authorize_new_tools(self):
        tools = {p: {"owner": "missing"} for p in skill.PACKAGES.values()}
        tools["EPUBCheck"] = {"owner": "missing"}
        settings = {"auto_install": True, "python_manager": "pip", "checker_manager": "homebrew"}
        with patch.object(skill, "run_quietly") as command, patch.object(skill, "make_environment") as create:
            skill.refresh(settings, tools)
            command.assert_not_called()
            create.assert_not_called()

    def test_bootstrap_reuses_existing_host_environment(self):
        tools = {
            "Homebrew": {"owner": "homebrew", "path": "/opt/homebrew/bin/brew"},
            "Python": {"owner": "homebrew", "path": "/opt/homebrew/bin/python3", "version": "3.15"},
            "uv": {"owner": "homebrew", "path": "/opt/homebrew/bin/uv"},
            "EPUBCheck": {"owner": "homebrew", "path": "/opt/homebrew/bin/epubcheck"},
            **{p: {"owner": "uv", "path": f"/venv/{p}"} for p in skill.PACKAGES.values()},
        }
        settings = {}
        with (
            patch.object(skill, "install_homebrew_silently") as inst_brew,
            patch.object(skill, "install_python_silently") as inst_py,
            patch.object(skill, "install_uv_silently") as inst_uv,
            patch.object(skill, "install_epubcheck_silently") as inst_chk,
        ):
            skill.bootstrap_runtime(settings, tools)
            inst_brew.assert_not_called()
            inst_py.assert_not_called()
            inst_uv.assert_not_called()
            inst_chk.assert_not_called()
            self.assertEqual(settings["python_manager"], "uv")
            self.assertEqual(settings["checker_manager"], "homebrew")
            self.assertTrue(settings["auto_install"])

    def test_bootstrap_silently_installs_missing_tools(self):
        tools = {
            "Homebrew": {"owner": "missing"},
            "Python": {"owner": "missing"},
            "uv": {"owner": "missing"},
            "EPUBCheck": {"owner": "missing"},
            **{p: {"owner": "missing"} for p in skill.PACKAGES.values()},
        }
        settings = {}
        with (
            patch.object(skill, "install_homebrew_silently", return_value="/opt/homebrew/bin/brew") as inst_brew,
            patch.object(skill, "install_python_silently", return_value="/opt/homebrew/bin/python3") as inst_py,
            patch.object(skill, "install_uv_silently", return_value="/opt/homebrew/bin/uv") as inst_uv,
            patch.object(skill, "install_epubcheck_silently") as inst_chk,
        ):
            skill.bootstrap_runtime(settings, tools)
            inst_brew.assert_called_once()
            inst_py.assert_called_once_with("/opt/homebrew/bin/brew", None)
            inst_uv.assert_called_once_with("/opt/homebrew/bin/brew")
            inst_chk.assert_called_once_with(settings, "/opt/homebrew/bin/brew")
            self.assertEqual(settings["python_manager"], "uv")
            self.assertEqual(settings["checker_manager"], "homebrew")
