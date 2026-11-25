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

from test_epub_safe import make_bilingual_epub2, make_bilingual_epub3

import epub_safe

REQUIRE_EPUBCHECK = os.environ.get("BLACKFLAME_REQUIRE_EPUBCHECK") == "1"
REQUIRE_RELEASE_ZIP = os.environ.get("BLACKFLAME_REQUIRE_RELEASE_ZIP") == "1"


def _epubcheck_available() -> bool:
    return REQUIRE_EPUBCHECK or bool(shutil.which("epubcheck"))


class RealToolIntegrationTests(unittest.TestCase):
    def test_epub3_metadata_editing_preserves_content_images_and_footnotes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "book.epub"
            out = root / "edited-meta.epub"
            make_bilingual_epub3(src, title="旧书名 Old Title")
            src_sha = epub_safe.sha256_file(src)

            with EPUB(src, generator_tag=False) as book:
                self.assertEqual(book.metadata.title, "旧书名 Old Title")
                book.metadata.title = "修订书名 Verified Title"
                book.write(out)

            self.assertEqual(epub_safe.sha256_file(src), src_sha)
            with EPUB(out, generator_tag=False) as updated:
                self.assertEqual(updated.metadata.title, "修订书名 Verified Title")
            epub_safe.compare_epubs(src, out, preserve_spine=True, preserve_text=True)

            # Verify cover, figure, and footnotes remain intact.
            with ZipFile(out) as zf:
                self.assertEqual(epub_safe.image_dimensions(zf.read("OPS/cover.png")), (24, 36))
                self.assertEqual(epub_safe.image_dimensions(zf.read("OPS/figure.png")), (16, 16))
                ch1_text = zf.read("OPS/ch1.xhtml").decode("utf-8")
                self.assertIn("脚注内容", ch1_text)
                self.assertIn('href="#ref1"', ch1_text)

            if _epubcheck_available():
                before = epub_safe.run_epubcheck(src, root / "before.json")
                after = epub_safe.run_epubcheck(out, root / "after.json")
                epub_safe.assert_no_new_diagnostics(before, after)
                self.assertFalse(after.has_errors)

    def test_epub2_and_epub3_surgical_body_editing_with_bs4_lxml(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 1. EPUB 3 surgical copyedit
            src3 = root / "book3.epub"
            out3 = root / "edited3.epub"
            make_bilingual_epub3(src3, body_zh="这里有一个错别字需要修正。")
            with ZipFile(src3) as zf:
                raw3 = zf.read("OPS/ch1.xhtml")
            soup3 = BeautifulSoup(raw3, "xml")
            self.assertTrue(any("错别字" in p.get_text() for p in soup3.select("p")))
            self.assertEqual(raw3.count("错别字".encode()), 1)
            new3 = raw3.replace("错别字".encode(), "准确词".encode(), 1)
            epub_safe.parse_xml(new3)
            epub_safe.replace_members(src3, out3, {"OPS/ch1.xhtml": new3})
            diff3 = epub_safe.compare_epubs(src3, out3, expected_changed={"OPS/ch1.xhtml"}, preserve_spine=True)
            self.assertEqual(diff3["unchanged_entries"], 6)

            # 2. EPUB 2 (with NCX) surgical copyedit
            src2 = root / "book2.epub"
            out2 = root / "edited2.epub"
            make_bilingual_epub2(src2, body="EPUB2 原始段落。")
            with ZipFile(src2) as zf:
                raw2 = zf.read("OEBPS/ch1.xhtml")
            new2 = raw2.replace("原始段落".encode(), "校对段落".encode(), 1)
            epub_safe.parse_xml(new2)
            epub_safe.replace_members(src2, out2, {"OEBPS/ch1.xhtml": new2})
            diff2 = epub_safe.compare_epubs(src2, out2, expected_changed={"OEBPS/ch1.xhtml"}, preserve_spine=True)
            self.assertEqual(diff2["unchanged_entries"], 5)

            if _epubcheck_available():
                for s, o, tag in ((src3, out3, "e3"), (src2, out2, "e2")):
                    b = epub_safe.run_epubcheck(s, root / f"{tag}-before.json")
                    a = epub_safe.run_epubcheck(o, root / f"{tag}-after.json")
                    epub_safe.assert_no_new_diagnostics(b, a)
                    self.assertFalse(a.has_errors)

    def test_format_conversion_with_ebook_convert_retains_body_text_and_passes_epubcheck(self):
        converter = shutil.which("ebook-convert") or str(Path(sys.executable).with_name("ebook-convert"))
        self.assertTrue(Path(converter).is_file(), f"ebook-convert CLI not found at {converter}")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_html = root / "draft.html"
            src_html.write_text(
                '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/><title>转换测试 Converted</title></head>'
                "<body><h1>第一章 Chapter One</h1><p>保留中文正文与 English body text。</p></body></html>",
                encoding="utf-8",
            )
            out_epub = root / "converted.epub"
            proc = subprocess.run(
                [converter, str(src_html), str(out_epub), "--title", "转换测试 Converted", "--language", "zh"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertTrue(out_epub.is_file() and out_epub.stat().st_size > 0)

            with EPUB(out_epub, generator_tag=False) as book:
                self.assertEqual(book.metadata.title, "转换测试 Converted")
                combined_text = "\n".join(doc.soup.get_text() for doc in book.documents)
                self.assertIn("保留中文正文", combined_text)
                self.assertIn("English body text", combined_text)

            if _epubcheck_available():
                diag = epub_safe.run_epubcheck(out_epub, root / "converted-check.json")
                self.assertFalse(diag.has_errors)


class OfficialReleaseZipTests(unittest.TestCase):
    def test_official_release_zip_installs_and_runs_independently_with_uv(self):
        official_zip = REPO_ROOT / "Blackflame.zip"
        if not official_zip.is_file():
            if REQUIRE_RELEASE_ZIP:
                self.fail(f"Required official release artifact missing: {official_zip}")
            self.skipTest("Blackflame.zip not built locally; build it before release verification")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with ZipFile(official_zip) as zf:
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
                forbidden = ("__pycache__", ".venv", "tests/", "skill.py", "runtime.py", "audit.py", "uv.lock")
                for name in names:
                    for marker in forbidden:
                        self.assertNotIn(marker, name, f"Forbidden entry in Blackflame.zip: {name}")
                extract_dir = root / "standalone"
                zf.extractall(extract_dir)

            skill_dir = extract_dir / "blackflame"
            uv_exe = shutil.which("uv")
            self.assertIsNotNone(uv_exe, "uv must be available to verify standalone skill dependency setup")

            # Prepare dependencies inside the extracted skill using uv (offline cache first, online fallback).
            sync_offline = subprocess.run(
                [uv_exe, "sync", "--project", str(skill_dir), "--offline"],
                cwd=extract_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if sync_offline.returncode != 0:
                subprocess.run(
                    [uv_exe, "sync", "--project", str(skill_dir)],
                    cwd=extract_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )

            # Run representative metadata edit, body edit, and format conversion completely outside the repo.
            work = root / "work"
            work.mkdir()
            src = work / "book.epub"
            make_bilingual_epub3(src)
            smoke_script = f"""
from pathlib import Path
import sys
sys.path.insert(0, "blackflame/scripts")
import epub_safe
from epublib import EPUB
from bs4 import BeautifulSoup

src = Path({str(src)!r})
out = Path({str(work / "out.epub")!r})
with EPUB(src, generator_tag=False) as b:
    b.metadata.title = "Standalone Verified"
    b.write(out)
epub_safe.compare_epubs(src, out, preserve_spine=True, preserve_text=True)
assert BeautifulSoup("<p>ok</p>", "xml").find("p").text == "ok"
print("STANDALONE_OK")
"""
            proc = subprocess.run(
                [uv_exe, "run", "--project", str(skill_dir), "--no-sync", "python", "-c", smoke_script],
                cwd=extract_dir,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertIn("STANDALONE_OK", proc.stdout)

            # Verify ebook-convert works directly from the standalone extracted skill environment.
            html_in = work / "in.html"
            html_in.write_text("<!DOCTYPE html><html><body><p>Standalone convert</p></body></html>", encoding="utf-8")
            epub_out = work / "converted.epub"
            subprocess.run(
                [uv_exe, "run", "--project", str(skill_dir), "--no-sync", "ebook-convert", str(html_in), str(epub_out)],
                cwd=extract_dir,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertTrue(epub_out.is_file() and epub_out.stat().st_size > 0)
