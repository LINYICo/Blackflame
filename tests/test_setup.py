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
