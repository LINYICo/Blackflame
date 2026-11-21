import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "epublib/scripts"))
import skill


class MaintenanceTests(unittest.TestCase):
    def test_month_end(self):
        for year, day in [(2027, 28), (2028, 29)]:
            start = datetime(year, 1, 31, 9, 15, tzinfo=timezone.utc)
            self.assertEqual(skill.next_month(start), start.replace(month=2, day=day))
        december = datetime(2026, 12, 22, tzinfo=timezone.utc)
        self.assertEqual(skill.next_month(december), december.replace(year=2027, month=1))

    def test_first_use_skip_and_retry(self):
        settings = {"auto_install": False, "platform": "general", "update_interval_months": 1}
        def refresh(_, dest):
            return {"directory": dest.name, "python_abi": sys.implementation.cache_tag}
        with TemporaryDirectory() as tmp, patch.object(skill, "ROOT", Path(tmp)), patch.object(skill, "refresh", side_effect=refresh) as update:
            skill.maintain(settings)
            first = settings.copy()
            skill.maintain(settings)
            self.assertEqual(update.call_count, 1)
            settings["next_update_at"] = "2000-01-01T00:00:00+00:00"
            update.side_effect = RuntimeError("offline")
            skill.maintain(settings)
            self.assertEqual(settings["last_updated_at"], first["last_updated_at"])
            self.assertTrue((Path(tmp) / first["runtime"]["directory"]).exists())
            update.side_effect = refresh
            skill.maintain(settings)
            self.assertEqual(update.call_count, 3)
            self.assertNotIn("last_update_error", settings)
            self.assertFalse((Path(tmp) / first["runtime"]["directory"]).exists())
            self.assertEqual(json.loads((Path(tmp)/"settings.json").read_text()), settings)
