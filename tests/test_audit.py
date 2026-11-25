"""Tests for structured EPUB quality audit, EPUB 2/3 structures, security, and release ZIP execution."""

import json
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / "blackflame/scripts"
sys.path.insert(0, str(SCRIPTS))

from audit import audit_epub, detect_image_info
from publication import CONTAINER, MEDIA_TYPE, OPF, XHTML, parse_xml


def _make_png(width, height):
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
    )


def _write_epub(path, members):
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MEDIA_TYPE, compress_type=ZIP_STORED)
        for name, data in members.items():
            archive.writestr(name, data)


class AuditTests(unittest.TestCase):
    def test_detect_image_info_png(self):
        info = detect_image_info(_make_png(1200, 1800))
        self.assertEqual(info["format"], "png")
        self.assertEqual((info["width"], info["height"], info["pixels"]), (1200, 1800, 2_160_000))

    def test_epub3_clean_with_cover_and_bidirectional_footnotes(self):
        with TemporaryDirectory() as tmp:
            epub = Path(tmp) / "clean.epub"
            _write_epub(
                epub,
                {
                    CONTAINER: (
                        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                        '<rootfiles><rootfile full-path="OPS/package.opf" '
                        'media-type="application/oebps-package+xml"/></rootfiles></container>'
                    ),
                    "OPS/package.opf": (
                        f'<package xmlns="{OPF}" version="3.0" unique-identifier="id" xml:lang="en">'
                        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                        "<dc:title>Book</dc:title><dc:identifier id='id'>urn:test:1</dc:identifier>"
                        "<dc:language>en</dc:language><dc:rights>Copyright 2026</dc:rights>"
                        '<meta property="dcterms:modified">2026-11-25T00:00:00Z</meta>'
                        "</metadata>"
                        "<manifest>"
                        '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
                        '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
                        '<item id="cov" href="cover.png" properties="cover-image" media-type="image/png"/>'
                        '<item id="css" href="style.css" media-type="text/css"/>'
                        "</manifest>"
                        '<spine><itemref idref="c1"/></spine></package>'
                    ),
                    "OPS/nav.xhtml": (
                        f'<html xmlns="{XHTML}" xmlns:epub="http://www.idpf.org/2007/ops">'
                        "<head><title>TOC</title></head>"
                        '<body><nav epub:type="toc"><ol><li><a href="ch1.xhtml#s1">One</a></li></ol></nav></body></html>'
                    ),
                    "OPS/ch1.xhtml": (
                        f'<html xmlns="{XHTML}" xmlns:epub="http://www.idpf.org/2007/ops">'
                        '<head><title>Ch1</title><link rel="stylesheet" href="style.css"/></head>'
                        '<body><h1 id="s1">One</h1><img src="cover.png" alt="cover"/>'
                        '<p>Text<a id="ref1" epub:type="noteref" href="#fn1">1</a></p>'
                        '<aside id="fn1" epub:type="footnote"><p>Note <a href="#ref1">back</a></p></aside>'
                        "</body></html>"
                    ),
                    "OPS/style.css": "body { font-family: serif; }",
                    "OPS/cover.png": _make_png(1000, 1500),
                },
            )
            report = audit_epub(epub)
            self.assertTrue(report["structural_integrity"]["passed"])
            self.assertEqual(report["reader_compatibility"]["footnote_issues"], [])
            self.assertEqual(report["reader_compatibility"]["remote_resources"], [])
            self.assertEqual(report["reader_compatibility"]["covers"][0]["format"], "png")
            self.assertFalse(report["reader_compatibility"]["covers"][0]["exceeds_apple_books_pixel_limit"])

    def test_epub2_ncx_broken_links_missing_assets_remote_and_footnote_issues(self):
        with TemporaryDirectory() as tmp:
            epub = Path(tmp) / "broken.epub"
            _write_epub(
                epub,
                {
                    CONTAINER: (
                        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                        '<rootfiles><rootfile full-path="book.opf" '
                        'media-type="application/oebps-package+xml"/></rootfiles></container>'
                    ),
                    "book.opf": (
                        f'<package xmlns="{OPF}" version="2.0" unique-identifier="id">'
                        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                        "<dc:title>EPUB2</dc:title><dc:identifier id='id'>urn:test:2</dc:identifier>"
                        "<dc:language>en</dc:language><meta name='cover' content='cov'/>"
                        "</metadata>"
                        "<manifest>"
                        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
                        '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
                        '<item id="c1" href="missing.xhtml" media-type="application/xhtml+xml"/>'
                        '<item id="cov" href="cover.png" media-type="image/png"/>'
                        '<item id="css" href="style.css" media-type="text/css"/>'
                        "</manifest>"
                        '<spine toc="ncx"><itemref idref="c1"/><itemref idref="ghost"/></spine></package>'
                    ),
                    "toc.ncx": (
                        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
                        '<navMap><navPoint id="p1"><navLabel><text>Ch1</text></navLabel>'
                        '<content src="c1.xhtml#missing-frag"/></navPoint></navMap></ncx>'
                    ),
                    "c1.xhtml": (
                        f'<html xmlns="{XHTML}" xmlns:epub="http://www.idpf.org/2007/ops">'
                        '<head><title>Ch1</title><link rel="stylesheet" href="style.css"/></head>'
                        '<body><img src="absent.png" alt="x"/>'
                        '<a href="https://example.com/remote.jpg">remote</a>'
                        '<a id="r1" epub:type="noteref" href="#fn1">1</a>'
                        '<aside id="fn1" epub:type="footnote"><p>No return link</p></aside>'
                        "</body></html>"
                    ),
                    "style.css": "@font-face { src: url('fonts/missing.woff2'); }",
                    "cover.png": _make_png(3000, 2000),  # 6M pixels > 5.6M Apple Books limit
                },
            )
            report = audit_epub(epub)
            si = report["structural_integrity"]
            rc = report["reader_compatibility"]
            self.assertFalse(si["passed"])
            self.assertTrue(any(i["type"] == "duplicate_manifest_id" for i in si["manifest_issues"]))
            self.assertTrue(any(i["type"] == "missing_manifest_resource" for i in si["manifest_issues"]))
            self.assertTrue(any(i["type"] == "invalid_spine_idref" for i in si["spine_issues"]))
            self.assertTrue(any(i["type"] == "missing_ncx_fragment" for i in si["navigation_issues"]))
            self.assertTrue(any(i["type"] == "missing_image" for i in si["asset_issues"]))
            self.assertTrue(any(i["type"] == "missing_css_asset" for i in si["asset_issues"]))
            self.assertTrue(any(i["type"] == "footnote_missing_return_link" for i in rc["footnote_issues"]))
            self.assertTrue(len(rc["remote_resources"]) >= 1)
            self.assertTrue(rc["covers"][0]["exceeds_apple_books_pixel_limit"])

    def test_xml_external_entity_is_not_resolved(self):
        xxe = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><root>&xxe;</root>'
        tree = parse_xml(xxe)
        self.assertNotIn("root:", tree.getroot().text or "")


class ReleaseZipStandaloneTests(unittest.TestCase):
    def test_packaged_skill_runs_independently_after_extraction(self):
        repo_root = Path(__file__).resolve().parents[1]
        skill_dir = repo_root / "blackflame"
        with TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "Blackflame.zip"
            with ZipFile(bundle, "w") as zf:
                for file in skill_dir.rglob("*"):
                    if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                        zf.write(file, file.relative_to(repo_root))
            extract_dir = Path(tmp) / "extracted"
            with ZipFile(bundle) as zf:
                zf.extractall(extract_dir)
            standalone_skill = extract_dir / "blackflame" / "scripts" / "skill.py"
            self.assertTrue(standalone_skill.is_file())
            env_home = Path(tmp) / "home"
            proc = subprocess.run(
                [sys.executable, str(standalone_skill), "status"],
                cwd=extract_dir,
                env={**__import__("os").environ, "BLACKFLAME_HOME": str(env_home)},
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(proc.stdout)
            self.assertTrue(data["first_use"])
            self.assertFalse((env_home / "settings.json").exists())
            self.assertIn("lxml", data["tools"])
