"""Real subprocess and virtual-environment integration tests (no mocked Python probes)."""

import json
import os
import shutil
import subprocess
import sys
import unittest
import venv
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "blackflame/scripts"
sys.path.insert(0, str(SCRIPTS))

import runtime
from publication import CONTAINER, MEDIA_TYPE, OPF, XHTML


def _venv_python(venv_dir):
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _site_packages(py_exe):
    return Path(
        subprocess.check_output(
            [str(py_exe), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            text=True,
        ).strip()
    )


def _install_fake_dist(site_dir, pkg_name, mod_name, body):
    dist_info = site_dir / f"{pkg_name.replace('-', '_')}-0.1.0.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {pkg_name}\nVersion: 0.1.0\n", encoding="utf-8")
    (dist_info / "INSTALLER").write_text("pip\n", encoding="utf-8")
    mod_dir = site_dir / mod_name
    mod_dir.mkdir(parents=True, exist_ok=True)
    (mod_dir / "__init__.py").write_text(body, encoding="utf-8")


def _build_valid_epub3(path):
    chapter = (
        f'<html xmlns="{XHTML}" xml:lang="en"><head><title>Chapter</title></head>'
        "<body><p>Original text.</p></body></html>"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MEDIA_TYPE, compress_type=ZIP_STORED)
        archive.writestr(
            CONTAINER,
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="book.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "book.opf",
            f'<package xmlns="{OPF}" version="3.0" unique-identifier="id" xml:lang="en">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>Sample</dc:title><dc:identifier id='id'>urn:example:zip-test</dc:identifier>"
            "<dc:language>en</dc:language><meta property='dcterms:modified'>2026-11-25T00:00:00Z</meta></metadata>"
            "<manifest>"
            '<item id="ch" href="c.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
            "</manifest><spine><itemref idref='ch'/></spine></package>",
        )
        archive.writestr(
            "nav.xhtml",
            f'<html xmlns="{XHTML}" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en">'
            "<head><title>Contents</title></head>"
            '<body><nav epub:type="toc"><ol><li><a href="c.xhtml">Chapter</a></li></ol></nav></body></html>',
        )
        archive.writestr("c.xhtml", chapter)
    return chapter


class RealVenvIntegrationTests(unittest.TestCase):
    def test_two_venvs_sharing_base_python_are_probed_independently(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            venv_a = root / "venv-a"
            venv_b = root / "venv-b"
            venv.create(venv_a, with_pip=False, symlinks=True)
            venv.create(venv_b, with_pip=False, symlinks=True)
            py_a = _venv_python(venv_a)
            py_b = _venv_python(venv_b)

            # Install a working fake beautifulsoup4 ONLY in venv-a.
            _install_fake_dist(_site_packages(py_a), "beautifulsoup4", "bs4", "MARKER = 'a'\n")

            info_a = runtime.probe_python(str(py_a))
            info_b = runtime.probe_python(str(py_b))
            self.assertIsNotNone(info_a)
            self.assertIsNotNone(info_b)
            self.assertNotEqual(info_a["executable"], info_b["executable"])
            self.assertNotEqual(info_a["prefix"], info_b["prefix"])
            self.assertTrue(info_a["packages"]["beautifulsoup4"]["installed"])
            self.assertTrue(info_a["packages"]["beautifulsoup4"]["importable"])
            self.assertFalse(info_b["packages"]["beautifulsoup4"]["installed"])

    def test_broken_core_lxml_import_is_detected_by_real_probe(self):
        with TemporaryDirectory() as tmp:
            venv_dir = Path(tmp) / "venv-broken"
            venv.create(venv_dir, with_pip=False, symlinks=True)
            py = _venv_python(venv_dir)
            _install_fake_dist(
                _site_packages(py),
                "lxml",
                "lxml",
                "raise ImportError('broken native etree')\n",
            )
            info = runtime.probe_python(str(py))
            self.assertIsNotNone(info)
            self.assertTrue(info["packages"]["lxml"].get("broken"))
            self.assertFalse(info["packages"]["lxml"]["importable"])

    def test_explicit_python_persistence_across_processes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            venv_dir = root / "venv-target"
            venv.create(venv_dir, with_pip=False, symlinks=True)
            py_target = _venv_python(venv_dir)
            home = root / "blackflame-home"
            env = {**os.environ, "BLACKFLAME_HOME": str(home)}

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "skill.py"),
                    "configure",
                    "--platform",
                    "Apple Books",
                    "--python",
                    str(py_target),
                ],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            status_proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "skill.py"), "status"],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            data = json.loads(status_proc.stdout)
            self.assertEqual(os.path.abspath(data["preferred_python"]), os.path.abspath(str(py_target)))
            self.assertEqual(os.path.abspath(data["interpreter"]), os.path.abspath(str(py_target)))


class OfficialReleaseZipWorkflowTests(unittest.TestCase):
    def test_release_zip_full_standalone_workflow(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Use official Blackflame.zip if present at repo root, otherwise build exact release archive.
            official_zip = REPO_ROOT / "Blackflame.zip"
            if official_zip.is_file():
                bundle = official_zip
            else:
                bundle = root / "Blackflame.zip"
                skill_dir = REPO_ROOT / "blackflame"
                with ZipFile(bundle, "w") as zf:
                    for file in skill_dir.rglob("*"):
                        if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                            zf.write(file, file.relative_to(REPO_ROOT))

            extract_dir = root / "extracted"
            with ZipFile(bundle) as zf:
                names = zf.namelist()
                self.assertFalse(any("__pycache__" in n or ".venv" in n or "tests/" in n for n in names))
                zf.extractall(extract_dir)

            skill_cli = extract_dir / "blackflame" / "scripts" / "skill.py"
            self.assertTrue(skill_cli.is_file())
            home = root / "home"
            env = {**os.environ, "BLACKFLAME_HOME": str(home)}

            # 1. Read-only status
            status_out = subprocess.run(
                [sys.executable, str(skill_cli), "status"],
                cwd=extract_dir,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            status_data = json.loads(status_out.stdout)
            self.assertTrue(status_data["first_use"])
            self.assertFalse((home / "settings.json").exists())

            # 2. Inspect & audit synthetic EPUB 3
            work = root / "work"
            work.mkdir()
            source = work / "source.epub"
            chapter = _build_valid_epub3(source)

            inv_out = subprocess.run(
                [sys.executable, str(skill_cli), "run", "inspect", str(source)],
                cwd=extract_dir,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            digest = json.loads(inv_out.stdout)["source_sha256"]

            audit_out = subprocess.run(
                [sys.executable, str(skill_cli), "run", "audit", str(source)],
                cwd=extract_dir,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(json.loads(audit_out.stdout)["structural_integrity"]["passed"])

            # 3. Apply & verify when EPUBCheck is available (required in CI)
            if os.environ.get("BLACKFLAME_REQUIRE_EPUBCHECK") == "1" or shutil.which("epubcheck"):
                (work / "c.xhtml").write_text(chapter.replace("Original text.", "Updated text."), encoding="utf-8")
                (work / "plan.json").write_text(
                    json.dumps(
                        {
                            "source_sha256": digest,
                            "replacements": {"c.xhtml": "c.xhtml"},
                            "text_edits": {"c.xhtml": [{"old": "Original text.", "new": "Updated text.", "count": 1}]},
                        }
                    ),
                    encoding="utf-8",
                )
                edited = work / "edited.epub"
                subprocess.run(
                    [
                        sys.executable,
                        str(skill_cli),
                        "run",
                        "apply",
                        str(source),
                        str(edited),
                        "--plan",
                        str(work / "plan.json"),
                        "--report-dir",
                        str(work / "apply-report"),
                    ],
                    cwd=extract_dir,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                (work / "scope.json").write_text(
                    json.dumps({"source_sha256": digest, "added": [], "removed": [], "changed": ["c.xhtml"]}),
                    encoding="utf-8",
                )
                subprocess.run(
                    [
                        sys.executable,
                        str(skill_cli),
                        "run",
                        "verify",
                        str(source),
                        str(edited),
                        "--expected-changes",
                        str(work / "scope.json"),
                        "--preserve-spine",
                        "--report-dir",
                        str(work / "verify-report"),
                    ],
                    cwd=extract_dir,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
