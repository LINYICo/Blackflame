"""Real integration tests for epublib, BeautifulSoup4, lxml, ebook-convert, EPUBCheck, and Blackflame.zip."""

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from bs4 import BeautifulSoup
from epublib import EPUB

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "blackflame/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_epub_safe import make_epub3

import epub_safe

REQUIRE_EPUBCHECK = os.environ.get("BLACKFLAME_REQUIRE_EPUBCHECK") == "1"


def _epubcheck_available() -> bool:
    return REQUIRE_EPUBCHECK or bool(shutil.which("epubcheck"))


class RealToolIntegrationTests(unittest.TestCase):
    def test_metadata_editing_with_epublib_and_epubcheck(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "book.epub"
            out = root / "edited-meta.epub"
            make_epub3(src, title="Old Title")
            src_sha = epub_safe.sha256_file(src)

            with EPUB(src, generator_tag=False) as book:
                self.assertEqual(book.metadata.title, "Old Title")
                book.metadata.title = "Corrected Title"
                book.write(out)

            # Verify source untouched, reading text and spine preserved, and metadata updated.
            self.assertEqual(epub_safe.sha256_file(src), src_sha)
            with EPUB(out, generator_tag=False) as updated:
                self.assertEqual(updated.metadata.title, "Corrected Title")
            epub_safe.compare_epubs(src, out, preserve_spine=True, preserve_text=True)

            if _epubcheck_available():
                before = epub_safe.run_epubcheck(src, root / "before.json")
                after = epub_safe.run_epubcheck(out, root / "after.json")
                epub_safe.assert_no_new_diagnostics(before, after)
                self.assertFalse(after.has_errors)

    def test_body_editing_with_bs4_lxml_surgical_replace_and_epubcheck(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "book.epub"
            out = root / "edited-body.epub"
            make_epub3(src, body="A teh typo in the chapter.")
            src_sha = epub_safe.sha256_file(src)

            with ZipFile(src) as zf:
                raw_xhtml = zf.read("OPS/ch1.xhtml")

            # Use BeautifulSoup4 to locate the target passage, then apply a surgical XML edit.
            soup = BeautifulSoup(raw_xhtml, "xml")
            paragraphs = [p.get_text() for p in soup.select("p")]
            self.assertEqual(paragraphs, ["A teh typo in the chapter."])

            updated_xhtml = raw_xhtml.replace(b"teh typo", b"the typo", 1)
            epub_safe.parse_xml(updated_xhtml)  # strict XML check before write

            change_report = epub_safe.replace_members(src, out, {"OPS/ch1.xhtml": updated_xhtml})
            self.assertEqual(list(change_report["changed"]), ["OPS/ch1.xhtml"])
            self.assertEqual(epub_safe.sha256_file(src), src_sha)

            diff = epub_safe.compare_epubs(src, out, expected_changed={"OPS/ch1.xhtml"}, preserve_spine=True)
            self.assertEqual(diff["unchanged_entries"], 5)

            if _epubcheck_available():
                before = epub_safe.run_epubcheck(src, root / "before.json")
                after = epub_safe.run_epubcheck(out, root / "after.json")
                epub_safe.assert_no_new_diagnostics(before, after)
                self.assertFalse(after.has_errors)

    def test_format_conversion_with_ebook_convert_and_epubcheck(self):
        converter = shutil.which("ebook-convert") or str(Path(sys.executable).with_name("ebook-convert"))
        self.assertTrue(Path(converter).is_file(), f"ebook-convert CLI not found at {converter}")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_html = root / "draft.html"
            src_html.write_text(
                "<!DOCTYPE html><html><head><title>Converted Book</title></head>"
                "<body><h1>Chapter One</h1><p>Converted body content.</p></body></html>",
                encoding="utf-8",
            )
            out_epub = root / "converted.epub"
            proc = subprocess.run(
                [converter, str(src_html), str(out_epub), "--title", "Converted Book", "--language", "en"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertTrue(out_epub.is_file() and out_epub.stat().st_size > 0)

            with EPUB(out_epub, generator_tag=False) as book:
                self.assertEqual(book.metadata.title, "Converted Book")

            if _epubcheck_available():
                diag = epub_safe.run_epubcheck(out_epub, root / "converted-check.json")
                self.assertFalse(diag.has_errors)


class ReleasePackageIntegrityTests(unittest.TestCase):
    def test_release_zip_is_clean_and_self_contained(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            official_zip = REPO_ROOT / "Blackflame.zip"
            if official_zip.is_file():
                bundle = official_zip
            else:
                bundle = root / "Blackflame.zip"
                skill_dir = REPO_ROOT / "blackflame"
                with ZipFile(bundle, "w") as zf:
                    for file in skill_dir.rglob("*"):
                        if (
                            file.is_file()
                            and "__pycache__" not in file.parts
                            and ".venv" not in file.parts
                            and file.suffix != ".pyc"
                            and file.name not in {".DS_Store", "uv.lock"}
                        ):
                            zf.write(file, file.relative_to(REPO_ROOT))

            with ZipFile(bundle) as zf:
                names = set(zf.namelist())
                required = {
                    "blackflame/SKILL.md",
                    "blackflame/pyproject.toml",
                    "blackflame/agents/openai.yaml",
                    "blackflame/references/metadata.md",
                    "blackflame/references/editing.md",
                    "blackflame/references/conversion.md",
                    "blackflame/references/validation.md",
                    "blackflame/scripts/epub_safe.py",
                }
                self.assertTrue(required.issubset(names), f"Missing files: {required - names}")
                forbidden_markers = ("__pycache__", ".venv", "tests/", "skill.py", "runtime.py", "audit.py", "uv.lock")
                for name in names:
                    for marker in forbidden_markers:
                        self.assertNotIn(marker, name, f"Forbidden file in release ZIP: {name}")

                extract_dir = root / "extracted"
                zf.extractall(extract_dir)

            # Verify extracted epub_safe helper imports and runs cleanly in isolation.
            proc = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.path.insert(0, 'blackflame/scripts'); import epub_safe; "
                    "print(epub_safe.APPLE_MAX_IMAGE_PIXELS)",
                ],
                cwd=extract_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(proc.stdout.strip(), str(epub_safe.APPLE_MAX_IMAGE_PIXELS))
