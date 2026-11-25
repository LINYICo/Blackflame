"""Tests for hardened EPUB quality audit: XML safety, images/MIME, CSS, footnotes, and EPUB 2/3 nav."""

import struct
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / "blackflame/scripts"
sys.path.insert(0, str(SCRIPTS))

from audit import audit_epub, detect_image_info
from publication import CONTAINER, MEDIA_TYPE, OPF, XHTML, parse_xml


def _make_png(width, height, *, truncated=False):
    header = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00"
    )
    if truncated:
        return header
    return header + struct.pack(">I", 0) + b"IEND\xaeB`\x82"


def _make_jpeg(width, height, *, truncated=False):
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + sof0 + (b"" if truncated else b"\xff\xd9")


def _write_epub(path, members):
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MEDIA_TYPE, compress_type=ZIP_STORED)
        for name, data in members.items():
            archive.writestr(name, data)


class AuditTests(unittest.TestCase):
    def test_detect_image_info_valid_and_corrupted(self):
        valid_png = detect_image_info(_make_png(1200, 1800))
        self.assertTrue(valid_png["valid"])
        self.assertEqual((valid_png["format"], valid_png["width"], valid_png["height"]), ("png", 1200, 1800))

        bad_png = detect_image_info(_make_png(1200, 1800, truncated=True))
        self.assertFalse(bad_png["valid"])
        self.assertEqual(bad_png["width"], "unknown")

        valid_jpg = detect_image_info(_make_jpeg(800, 600))
        self.assertTrue(valid_jpg["valid"])
        self.assertEqual((valid_jpg["format"], valid_jpg["width"], valid_jpg["height"]), ("jpeg", 800, 600))

        bad_jpg = detect_image_info(_make_jpeg(800, 600, truncated=True))
        self.assertFalse(bad_jpg["valid"])

    def test_epub3_with_xml_comments_pis_svg_multitoken_footnotes_and_external_links(self):
        with TemporaryDirectory() as tmp:
            epub = Path(tmp) / "rich.epub"
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
                        "<dc:language>en</dc:language>"
                        '<meta property="dcterms:modified">2026-11-25T00:00:00Z</meta>'
                        "</metadata>"
                        "<manifest>"
                        '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
                        '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
                        '<item id="cov" href="cover.png" properties="cover-image" media-type="image/png"/>'
                        '<item id="fig" href="fig.jpg" media-type="image/jpeg"/>'
                        '<item id="css" href="style.css" media-type="text/css"/>'
                        '<item id="sub" href="sub.css" media-type="text/css"/>'
                        "</manifest>"
                        '<spine><itemref idref="c1"/></spine></package>'
                    ),
                    "OPS/nav.xhtml": (
                        f'<html xmlns="{XHTML}" xmlns:epub="http://www.idpf.org/2007/ops">'
                        "<head><title>TOC</title></head>"
                        '<body><nav epub:type="toc landmark"><ol><li><a href="ch1.xhtml#s1">One</a></li></ol></nav>'
                        "</body></html>"
                    ),
                    "OPS/ch1.xhtml": (
                        '<?xml version="1.0" encoding="utf-8"?>'
                        '<?custom-pi test="1"?>'
                        f'<html xmlns="{XHTML}" xmlns:epub="http://www.idpf.org/2007/ops" '
                        'xmlns:xlink="http://www.w3.org/1999/xlink">'
                        '<head><title>Ch1</title><link rel="stylesheet" href="style.css"/></head>'
                        '<body><!-- leading comment --><h1 id="s1">One</h1>'
                        "<div style=\"background-image: url('fig.jpg')\"></div>"
                        '<svg xmlns="http://www.w3.org/2000/svg"><image xlink:href="cover.png"/></svg>'
                        '<p>See <a href="https://example.org/ref">Reference</a>'
                        '<a id="ref1" epub:type="noteref ref-marker" href="#fn1">1</a></p>'
                        '<aside id="fn1" epub:type="footnote custom-note"><p>Note <a href="#ref1">back</a></p></aside>'
                        "</body></html>"
                    ),
                    "OPS/style.css": '/* @import "ignored.css"; */ @import "sub.css"; body { color: #111; }',
                    "OPS/sub.css": "p { margin: 0; }",
                    "OPS/cover.png": _make_png(1000, 1500),
                    "OPS/fig.jpg": _make_jpeg(1200, 800),
                },
            )
            report = audit_epub(epub)
            self.assertTrue(report["structural_integrity"]["passed"])
            self.assertEqual(report["reader_compatibility"]["footnote_issues"], [])
            # Normal <a> hyperlink is classified under external_links, NOT remote_resources!
            self.assertEqual(report["reader_compatibility"]["remote_resources"], [])
            self.assertEqual(len(report["reader_compatibility"]["external_links"]), 1)
            # Missing dc:rights is optional (does NOT fail structural_integrity).
            self.assertEqual(report["structural_integrity"]["required_metadata_issues"], [])
            self.assertEqual(
                report["reader_compatibility"]["optional_metadata_notes"][0]["compliance_impact"],
                "none",
            )
            self.assertEqual(report["epubcheck_conformance"]["status"], "not_run")
            self.assertEqual(report["content_fidelity"]["status"], "not_verified")

    def test_broken_images_mime_mismatch_oversized_inline_css_import_and_empty_toc(self):
        with TemporaryDirectory() as tmp:
            epub = Path(tmp) / "issues.epub"
            _write_epub(
                epub,
                {
                    CONTAINER: (
                        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                        '<rootfiles><rootfile full-path="book.opf" '
                        'media-type="application/oebps-package+xml"/></rootfiles></container>'
                    ),
                    "book.opf": (
                        f'<package xmlns="{OPF}" version="3.0" unique-identifier="id">'
                        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                        "<dc:title>Broken</dc:title><dc:identifier id='id'>urn:test:3</dc:identifier>"
                        "<dc:language>en</dc:language>"
                        "</metadata>"
                        "<manifest>"
                        '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
                        '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
                        '<item id="cov" href="cover.png" properties="cover-image" media-type="image/png"/>'
                        '<item id="bad" href="corrupt.png" media-type="image/png"/>'
                        '<item id="big" href="big.png" media-type="image/png"/>'
                        '<item id="css" href="style.css" media-type="text/css"/>'
                        "</manifest>"
                        '<spine><itemref idref="c1"/></spine></package>'
                    ),
                    "nav.xhtml": (
                        f'<html xmlns="{XHTML}" xmlns:epub="http://www.idpf.org/2007/ops">'
                        "<head><title>TOC</title></head>"
                        '<body><nav epub:type="toc"><ol></ol></nav></body></html>'
                    ),
                    "c1.xhtml": (
                        f'<html xmlns="{XHTML}"><head><title>C1</title><link rel="stylesheet" href="style.css"/></head>'
                        '<body><p id="dup">A</p><p id="dup">B</p>'
                        '<div style="background: url(missing-inline.png)"></div></body></html>'
                    ),
                    "style.css": '@import "missing-import.css";',
                    "cover.png": _make_jpeg(800, 1000),  # JPEG bytes declared as image/png -> MIME mismatch!
                    "corrupt.png": _make_png(100, 100, truncated=True),
                    "big.png": _make_png(3000, 2000),  # 6M pixels inline image > 5.6M Apple Books limit
                },
            )
            report = audit_epub(epub)
            si = report["structural_integrity"]
            rc = report["reader_compatibility"]
            self.assertFalse(si["passed"])
            self.assertTrue(any(i["type"] == "empty_epub3_toc" for i in si["navigation_issues"]))
            self.assertTrue(any(i["type"] == "duplicate_element_id" for i in si["link_issues"]))
            self.assertTrue(any(i["type"] == "missing_css_import" for i in si["asset_issues"]))
            self.assertTrue(any(i["type"] == "missing_css_url" for i in si["asset_issues"]))
            self.assertTrue(any(i["type"] == "image_mime_mismatch" for i in si["image_issues"]))
            self.assertTrue(any(i["type"] == "corrupted_or_unrecognized_image" for i in si["image_issues"]))
            self.assertTrue(any(img["member"] == "big.png" and not img["is_cover"] for img in rc["oversized_images"]))

    def test_epub2_missing_ncx_is_reported(self):
        with TemporaryDirectory() as tmp:
            epub = Path(tmp) / "epub2-no-ncx.epub"
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
                        "<dc:title>E2</dc:title><dc:identifier id='id'>urn:test:e2</dc:identifier>"
                        "<dc:language>en</dc:language></metadata>"
                        '<manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest>'
                        '<spine><itemref idref="c1"/></spine></package>'
                    ),
                    "c1.xhtml": f'<html xmlns="{XHTML}"><head><title>C1</title></head><body><p>Hi</p></body></html>',
                },
            )
            report = audit_epub(epub)
            self.assertTrue(
                any(
                    i["type"] == "missing_epub2_ncx_or_toc" for i in report["structural_integrity"]["navigation_issues"]
                )
            )

    def test_xml_external_entity_is_not_resolved(self):
        xxe = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><root>&xxe;</root>'
        tree = parse_xml(xxe)
        self.assertNotIn("root:", tree.getroot().text or "")
