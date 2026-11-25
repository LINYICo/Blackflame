"""Unit tests for Blackflame's deterministic safety and verification helpers (epub_safe.py)."""

import struct
import sys
import unittest
from collections import Counter
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, BadZipFile, ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / "blackflame/scripts"
sys.path.insert(0, str(SCRIPTS))

import epub_safe


def make_png(width: int, height: int, *, truncated: bool = False) -> bytes:
    header = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00"
    )
    return header if truncated else header + struct.pack(">I", 0) + b"IEND\xaeB`\x82"


def make_epub3(path: Path, *, title: str = "Sample Book", body: str = "Original paragraph.") -> None:
    chapter = (
        f'<html xmlns="{epub_safe.XHTML}" xml:lang="en"><head><title>Chapter 1</title></head>'
        f"<body><h1>Chapter 1</h1><p>{body}</p></body></html>"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", epub_safe.MEDIA_TYPE, compress_type=ZIP_STORED)
        archive.writestr(
            epub_safe.CONTAINER,
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OPS/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "OPS/package.opf",
            f'<package xmlns="{epub_safe.OPF}" version="3.0" unique-identifier="pub-id" xml:lang="en">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<dc:title>{title}</dc:title>"
            "<dc:creator>Author Name</dc:creator>"
            '<dc:identifier id="pub-id">urn:uuid:12345678-1234-5678-1234-567812345678</dc:identifier>'
            "<dc:language>en</dc:language>"
            '<meta property="dcterms:modified">2026-11-25T00:00:00Z</meta>'
            "</metadata>"
            "<manifest>"
            '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
            '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="cov" href="cover.png" properties="cover-image" media-type="image/png"/>'
            "</manifest>"
            '<spine><itemref idref="ch1"/></spine></package>',
        )
        archive.writestr(
            "OPS/nav.xhtml",
            f'<html xmlns="{epub_safe.XHTML}" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en">'
            "<head><title>Contents</title></head>"
            '<body><nav epub:type="toc"><ol><li><a href="ch1.xhtml">Chapter 1</a></li></ol></nav></body></html>',
        )
        archive.writestr("OPS/ch1.xhtml", chapter)
        archive.writestr("OPS/cover.png", make_png(800, 1200))


class EpubSafeSecurityTests(unittest.TestCase):
    def test_xml_external_entity_not_resolved(self):
        xxe = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><root>&xxe;</root>'
        tree = epub_safe.parse_xml(xxe)
        self.assertNotIn("root:", tree.getroot().text or "")

    def test_zip_rejects_traversal_invalid_mimetype_duplicates_and_corruption(self):
        for member, mime in [("../escape.xhtml", epub_safe.MEDIA_TYPE), ("ch.xhtml", b"invalid")]:
            with self.subTest(member=member):
                stream = BytesIO()
                with ZipFile(stream, "w") as zf:
                    zf.writestr("mimetype", mime, compress_type=ZIP_STORED)
                    zf.writestr(member, b"data")
                with ZipFile(stream) as zf, self.assertRaises(ValueError):
                    epub_safe.check_zip(zf, stream)

        dup_stream = BytesIO()
        with ZipFile(dup_stream, "w") as zf:
            zf.writestr("mimetype", epub_safe.MEDIA_TYPE, compress_type=ZIP_STORED)
            zf.writestr("a.xhtml", b"1")
            zf.writestr("a.xhtml", b"2")
        with ZipFile(dup_stream) as zf, self.assertRaisesRegex(ValueError, "Duplicate ZIP entry"):
            epub_safe.check_zip(zf, dup_stream)

        with self.assertRaises(BadZipFile):
            ZipFile(BytesIO(b"not a zip archive"))

    def test_replace_members_protects_source_and_refuses_protected_epubs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.epub"
            make_epub3(src)
            original_sha = epub_safe.sha256_file(src)

            # Never overwrite existing file
            with self.assertRaisesRegex(ValueError, "already exists"):
                epub_safe.replace_members(src, src, {"OPS/ch1.xhtml": b"x"})

            # Refuse protected publication containing signatures.xml
            protected = root / "signed.epub"
            with ZipFile(src) as z_in, ZipFile(protected, "w") as z_out:
                for info in z_in.infolist():
                    z_out.writestr(info, z_in.read(info))
                z_out.writestr("META-INF/signatures.xml", b"<signatures/>")
            with self.assertRaisesRegex(ValueError, "Protected publication"):
                epub_safe.replace_members(protected, root / "out.epub", {"OPS/ch1.xhtml": b"x"})

            self.assertEqual(epub_safe.sha256_file(src), original_sha)


class EpubSafeVerificationTests(unittest.TestCase):
    def test_image_dimensions_and_apple_limit(self):
        self.assertEqual(epub_safe.image_dimensions(make_png(1000, 1500)), (1000, 1500))
        self.assertIsNone(epub_safe.image_dimensions(make_png(1000, 1500, truncated=True)))
        self.assertGreater(3000 * 2000, epub_safe.APPLE_MAX_IMAGE_PIXELS)

    def test_compare_epubs_detects_text_and_scope_changes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.epub"
            out = root / "out.epub"
            make_epub3(src, body="Hello world.")
            with ZipFile(src) as zf:
                ch1 = zf.read("OPS/ch1.xhtml")
            epub_safe.replace_members(src, out, {"OPS/ch1.xhtml": ch1.replace(b"world", b"Blackflame")})

            report = epub_safe.compare_epubs(src, out, expected_changed={"OPS/ch1.xhtml"}, preserve_spine=True)
            self.assertEqual(report["changed"], ["OPS/ch1.xhtml"])
            self.assertTrue(report["spine_unchanged"])

            with self.assertRaisesRegex(ValueError, "Reading text changed"):
                epub_safe.compare_epubs(src, out, preserve_text=True)

            with self.assertRaisesRegex(ValueError, "authorized scope"):
                epub_safe.compare_epubs(src, out, expected_changed=set())

    def test_assert_no_new_diagnostics_blocks_regressions(self):
        before = epub_safe.Diagnostics("5.4.0", False, Counter({("WARNING", "W1", "msg", "a.xhtml", None): 1}))
        same = epub_safe.Diagnostics("5.4.0", False, Counter({("WARNING", "W1", "msg", "a.xhtml", None): 1}))
        worse = epub_safe.Diagnostics("5.4.0", False, Counter({("WARNING", "W1", "msg", "a.xhtml", None): 2}))
        epub_safe.assert_no_new_diagnostics(before, same)
        with self.assertRaisesRegex(ValueError, "New EPUBCheck diagnostics"):
            epub_safe.assert_no_new_diagnostics(before, worse)
