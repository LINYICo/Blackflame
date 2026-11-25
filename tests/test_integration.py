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
from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "blackflame/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_epub_safe import make_bilingual_epub2, make_bilingual_epub3, make_valid_png

import epub_safe

REQUIRE_EPUBCHECK = os.environ.get("BLACKFLAME_REQUIRE_EPUBCHECK") == "1"
REQUIRE_RELEASE_ZIP = os.environ.get("BLACKFLAME_REQUIRE_RELEASE_ZIP") == "1"


def _epubcheck_available() -> bool:
    return REQUIRE_EPUBCHECK or bool(shutil.which("epubcheck"))


class RealToolIntegrationTests(unittest.TestCase):
    def test_surgical_metadata_edit_changes_only_opf_and_preserves_all_other_resources(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "book.epub"
            out = root / "edited-meta.epub"
            make_bilingual_epub3(src, title="旧书名 Old Title")
            src_sha = epub_safe.sha256_file(src)

            # Recommended minimal metadata-only workflow: locate OPF via container.xml + lxml + replace_members.
            with ZipFile(src) as zf:
                container = epub_safe.parse_xml(zf.read(epub_safe.CONTAINER))
                opf_member = container.xpath(
                    "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
                    namespaces={"c": "urn:oasis:names:tc:opendocument:xmlns:container"},
                )[0]
                opf_tree = epub_safe.parse_xml(zf.read(opf_member))

            title_el = opf_tree.find(".//{http://purl.org/dc/elements/1.1/}title")
            self.assertIsNotNone(title_el)
            title_el.text = "修订书名 Verified Title"
            new_opf = etree.tostring(opf_tree, xml_declaration=True, encoding="utf-8")
            epub_safe.replace_members(src, out, {opf_member: new_opf})

            self.assertEqual(epub_safe.sha256_file(src), src_sha)
            diff = epub_safe.compare_epubs(
                src,
                out,
                expected_changed={opf_member},
                expected_added=set(),
                expected_removed=set(),
                preserve_spine=True,
                preserve_text=True,
            )
            self.assertEqual(diff["changed"], [opf_member])

            # Verify updated title plus preserved unrelated metadata, images, and footnotes.
            with EPUB(out, generator_tag=False) as updated:
                self.assertEqual(updated.metadata.title, "修订书名 Verified Title")
                self.assertEqual(updated.metadata.language, "zh-CN")
                self.assertEqual(updated.metadata.identifier, "urn:uuid:12345678-1234-5678-1234-567812345678")
            with ZipFile(out) as zf:
                opf_text = zf.read(opf_member).decode("utf-8")
                self.assertIn("Test Author 测试作者", opf_text)
                self.assertIn("Copyright 2026 Test Fixture", opf_text)
                self.assertEqual(epub_safe.image_dimensions(zf.read("OPS/cover.png")), (24, 36))
                self.assertEqual(epub_safe.image_dimensions(zf.read("OPS/figure.png")), (16, 16))
                ch1_text = zf.read("OPS/ch1.xhtml").decode("utf-8")
                self.assertIn("脚注内容", ch1_text)
                self.assertIn('href="#ref1"', ch1_text)

            # Verify epublib high-level write also preserves spine, text, and non-package resources.
            out_lib = root / "edited-epublib.epub"
            with EPUB(src, generator_tag=False) as book:
                book.metadata.title = "High-Level Verified Title"
                book.write(out_lib)
            lib_diff = epub_safe.compare_epubs(src, out_lib, preserve_spine=True, preserve_text=True)
            self.assertEqual(lib_diff["added"], [])
            self.assertEqual(lib_diff["removed"], [])
            self.assertTrue(set(lib_diff["changed"]).issubset({opf_member, epub_safe.CONTAINER}))

            if _epubcheck_available():
                before = epub_safe.run_epubcheck(src, root / "before.json")
                after = epub_safe.run_epubcheck(out, root / "after.json")
                after_lib = epub_safe.run_epubcheck(out_lib, root / "after-lib.json")
                epub_safe.assert_no_new_diagnostics(before, after)
                epub_safe.assert_no_new_diagnostics(before, after_lib)
                self.assertFalse(after.has_errors)
                self.assertFalse(after_lib.has_errors)

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

    def test_format_conversion_with_ebook_convert_retains_chapters_images_and_text(self):
        converter = shutil.which("ebook-convert") or str(Path(sys.executable).with_name("ebook-convert"))
        self.assertTrue(Path(converter).is_file(), f"ebook-convert CLI not found at {converter}")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "illustration.png").write_bytes(make_valid_png(32, 32))
            src_html = root / "draft.html"
            src_html.write_text(
                '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/><title>转换测试 Converted</title></head>'
                "<body>"
                "<h1>第一章 Chapter One</h1>"
                "<p>第一段中文正文与 English paragraph one.</p>"
                '<p><img src="illustration.png" alt="Sample Illustration"/></p>'
                "<h1>第二章 Chapter Two</h1>"
                "<p>第二段中文正文与 English paragraph two.</p>"
                "</body></html>",
                encoding="utf-8",
            )
            out_epub = root / "converted.epub"
            proc = subprocess.run(
                [
                    converter,
                    str(src_html),
                    str(out_epub),
                    "--title",
                    "转换测试 Converted",
                    "--authors",
                    "Test Author",
                    "--language",
                    "zh",
                    "--epub-version",
                    "3",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertTrue(out_epub.is_file() and out_epub.stat().st_size > 0)

            with EPUB(out_epub, generator_tag=False) as book:
                self.assertEqual(book.metadata.title, "转换测试 Converted")
                combined_text = "\n".join(doc.soup.get_text() for doc in book.documents)
                self.assertIn("第一段中文正文", combined_text)
                self.assertIn("English paragraph one", combined_text)
                self.assertIn("第二段中文正文", combined_text)
                self.assertIn("English paragraph two", combined_text)
            with ZipFile(out_epub) as zf:
                png_members = [n for n in zf.namelist() if n.lower().endswith(".png")]
                self.assertTrue(png_members, "Expected embedded PNG illustration to survive HTML -> EPUB conversion")
                self.assertEqual(epub_safe.image_dimensions(zf.read(png_members[0])), (32, 32))

            # Verify EPUB -> TXT preserves body paragraphs (format-appropriate expectations).
            out_txt = root / "converted.txt"
            proc_txt = subprocess.run(
                [converter, str(out_epub), str(out_txt)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc_txt.returncode, 0, msg=proc_txt.stdout + proc_txt.stderr)
            txt_content = out_txt.read_text(encoding="utf-8")
            self.assertIn("第一段中文正文", txt_content)
            self.assertIn("English paragraph two", txt_content)

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
                    "LICENSE",
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
                license_text = zf.read("LICENSE").decode("utf-8")
                self.assertIn("MIT License", license_text)
                self.assertIn("Copyright", license_text)
                forbidden = ("__pycache__", ".venv", "tests/", "skill.py", "runtime.py", "audit.py", "uv.lock")
                for name in names:
                    for marker in forbidden:
                        self.assertNotIn(marker, name, f"Forbidden entry in Blackflame.zip: {name}")
                extract_dir = root / "standalone"
                zf.extractall(extract_dir)

            skill_dir = extract_dir / "blackflame"
            uv_exe = shutil.which("uv")
            self.assertIsNotNone(uv_exe, "uv must be available to verify standalone skill dependency setup")

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

            # Run real metadata edit, real EPUB body edit, format conversion, and EPUBCheck outside the repo.
            work = root / "work"
            work.mkdir()
            src = work / "book.epub"
            make_bilingual_epub3(src, body_zh="独立包测试错别字。")
            run_ec = _epubcheck_available()
            smoke_script = f"""
from pathlib import Path
from zipfile import ZipFile
import sys
sys.path.insert(0, str(Path({str(skill_dir / "scripts")!r})))
import epub_safe
from bs4 import BeautifulSoup
from lxml import etree

work = Path({str(work)!r})
src = work / "book.epub"
meta_out = work / "meta-edited.epub"
body_out = work / "body-edited.epub"

# 1. Real surgical metadata edit
with ZipFile(src) as zf:
    c = epub_safe.parse_xml(zf.read(epub_safe.CONTAINER))
    opf_member = c.xpath(
        "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
        namespaces={{"c": "urn:oasis:names:tc:opendocument:xmlns:container"}},
    )[0]
    opf = epub_safe.parse_xml(zf.read(opf_member))
opf.find(".//{{http://purl.org/dc/elements/1.1/}}title").text = "Standalone Verified"
epub_safe.replace_members(src, meta_out, {{opf_member: etree.tostring(opf, xml_declaration=True, encoding="utf-8")}})
epub_safe.compare_epubs(src, meta_out, expected_changed={{opf_member}}, preserve_spine=True, preserve_text=True)

# 2. Real EPUB body chapter edit
with ZipFile(meta_out) as zf:
    raw = zf.read("OPS/ch1.xhtml")
soup = BeautifulSoup(raw, "xml")
assert any("独立包测试错别字" in p.get_text() for p in soup.select("p"))
updated_ch = raw.replace("独立包测试错别字".encode(), "独立包已校对".encode(), 1)
epub_safe.parse_xml(updated_ch)
epub_safe.replace_members(meta_out, body_out, {{"OPS/ch1.xhtml": updated_ch}})
epub_safe.compare_epubs(meta_out, body_out, expected_changed={{"OPS/ch1.xhtml"}}, preserve_spine=True)

if {run_ec!r}:
    b = epub_safe.run_epubcheck(src, work / "ec-src.json")
    a = epub_safe.run_epubcheck(body_out, work / "ec-body.json")
    epub_safe.assert_no_new_diagnostics(b, a)
    assert not a.has_errors
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

            # 3. Verify ebook-convert + EPUBCheck from the standalone extracted skill environment.
            html_in = work / "in.html"
            html_in.write_text(
                '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><title>Standalone</title></head>'
                "<body><h1>Chapter 1</h1><p>Standalone convert body.</p></body></html>",
                encoding="utf-8",
            )
            epub_out = work / "converted.epub"
            subprocess.run(
                [
                    uv_exe,
                    "run",
                    "--project",
                    str(skill_dir),
                    "--no-sync",
                    "ebook-convert",
                    str(html_in),
                    str(epub_out),
                    "--title",
                    "Standalone",
                    "--language",
                    "en",
                    "--epub-version",
                    "3",
                ],
                cwd=extract_dir,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertTrue(epub_out.is_file() and epub_out.stat().st_size > 0)
            if run_ec:
                diag = epub_safe.run_epubcheck(epub_out, work / "ec-conv.json")
                self.assertFalse(diag.has_errors)
