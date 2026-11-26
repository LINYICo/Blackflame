"""Unit and regression tests for Blackflame's deterministic safety helpers (epub_safe.py)."""

import os
import sys
import unittest
from collections import Counter
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / "blackflame/scripts"
sys.path.insert(0, str(SCRIPTS))

from epub_fixtures import make_bilingual_epub3, make_valid_png

import epub_safe


class EpubSafeSecurityTests(unittest.TestCase):
    def test_xml_external_entity_and_limit_enforced(self):
        xxe = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><root>&xxe;</root>'
        tree = epub_safe.parse_xml(xxe)
        self.assertNotIn("root:", tree.getroot().text or "")

        oversized = b"<r>" + (b"x" * (epub_safe.LIMIT_XML + 1)) + b"</r>"
        with self.assertRaisesRegex(ValueError, "exceeds size limit"):
            epub_safe.parse_xml(oversized)

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

    def test_zip_rejects_file_directory_conflicts(self):
        for path in ("OPS/chapter/", "OPS/chapter/page.xhtml"):
            with self.subTest(path=path):
                stream = BytesIO()
                with ZipFile(stream, "w") as zf:
                    zf.writestr("mimetype", epub_safe.MEDIA_TYPE, compress_type=ZIP_STORED)
                    zf.writestr("OPS/chapter", b"file")
                    zf.writestr(path, b"")
                with ZipFile(stream) as zf, self.assertRaisesRegex(ValueError, "ZIP file and directory conflict"):
                    epub_safe.check_zip(zf, stream)

    def test_xml_member_size_is_checked_before_read(self):
        stream = BytesIO()
        with ZipFile(stream, "w", compression=ZIP_DEFLATED) as zf:
            zf.writestr("book.opf", b" " * (epub_safe.LIMIT_XML + 1))
        with ZipFile(stream) as zf:
            with self.assertRaisesRegex(ValueError, "XML member exceeds size limit"):
                epub_safe.read_xml_member(zf, "book.opf")

    def test_replace_members_protects_source_and_refuses_protected_epubs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.epub"
            make_bilingual_epub3(src)
            original_sha = epub_safe.sha256_file(src)

            with self.assertRaisesRegex(ValueError, "must not overwrite"):
                epub_safe.replace_members(src, src, {"OPS/ch1.xhtml": b"x"})

            for entry in ("signatures.xml", "rights.xml", "encryption.xml"):
                with self.subTest(entry=entry):
                    protected = root / f"{entry}.epub"
                    with ZipFile(src) as z_in, ZipFile(protected, "w") as z_out:
                        for info in z_in.infolist():
                            z_out.writestr(info, z_in.read(info))
                        z_out.writestr(f"META-INF/{entry}", b"<protection/>")
                    out = root / "out.epub"
                    with self.assertRaisesRegex(ValueError, "Protected publication"):
                        epub_safe.replace_members(protected, out, {"OPS/ch1.xhtml": b"x"})
                    self.assertFalse(out.exists())

            self.assertEqual(epub_safe.sha256_file(src), original_sha)

    def test_run_epubcheck_protects_source_unrelated_files_and_collisions(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "book.epub"
            make_bilingual_epub3(src)
            original_sha = epub_safe.sha256_file(src)

            # Direct, symlink, and hardlink collisions with source
            with self.assertRaisesRegex(ValueError, "must not overwrite"):
                epub_safe.run_epubcheck(src, src)

            sym = root / "alias.json"
            sym.symlink_to(src)
            with self.assertRaisesRegex(ValueError, "must not overwrite|same file"):
                epub_safe.run_epubcheck(src, sym)

            hard = root / "hard.json"
            os.link(src, hard)
            with self.assertRaisesRegex(ValueError, "same file"):
                epub_safe.run_epubcheck(src, hard)

            # .log sidecar collision when source is named book.log
            log_src = root / "book.log"
            make_bilingual_epub3(log_src)
            with self.assertRaisesRegex(ValueError, "must not overwrite"):
                epub_safe.run_epubcheck(log_src, root / "book.json")

            # Report and log path collision (report ending in .log)
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                epub_safe.run_epubcheck(src, root / "check.log")

            # Existing unrelated report or log file must never be overwritten
            existing_report = root / "existing.json"
            existing_report.write_text("keep-report", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                epub_safe.run_epubcheck(src, existing_report)
            self.assertEqual(existing_report.read_text(encoding="utf-8"), "keep-report")

            existing_log = root / "fresh.log"
            existing_log.write_text("keep-log", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                epub_safe.run_epubcheck(src, root / "fresh.json")
            self.assertEqual(existing_log.read_text(encoding="utf-8"), "keep-log")

            # Validating an edited EPUB must not overwrite the original source EPUB
            edited = root / "edited.epub"
            edited.write_bytes(src.read_bytes())
            with self.assertRaisesRegex(ValueError, "already exists"):
                epub_safe.run_epubcheck(edited, src)

            self.assertEqual(epub_safe.sha256_file(src), original_sha)


class EpubSafeVerificationTests(unittest.TestCase):
    def test_image_dimensions_probe(self):
        self.assertEqual(epub_safe.image_dimensions(make_valid_png(24, 36)), (24, 36))
        self.assertIsNone(epub_safe.image_dimensions(make_valid_png(24, 36)[:-12]))  # truncated
        self.assertGreater(3000 * 2000, epub_safe.APPLE_MAX_IMAGE_PIXELS)

    def test_unresolved_spine_reference_fails_fidelity_check(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "good.epub"
            bad = root / "bad-spine.epub"
            make_bilingual_epub3(src)
            with ZipFile(src) as zf:
                opf = zf.read("OPS/package.opf").replace(b'idref="ch1"', b'idref="nonexistent"')
            epub_safe.replace_members(src, bad, {"OPS/package.opf": opf})

            with self.assertRaisesRegex(ValueError, "Unresolved spine idref"):
                epub_safe.compare_epubs(src, bad, preserve_spine=True, preserve_text=True)

    def test_paragraph_boundary_and_preformatted_whitespace_changes_detected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.epub"
            merged_para = root / "merged.epub"
            ws_changed = root / "ws.epub"
            make_bilingual_epub3(src, body_en="Alpha", body_zh="Beta", code_block="x = 1\n    y = 2")

            with ZipFile(src) as zf:
                ch1 = zf.read("OPS/ch1.xhtml")

            # Merge two <p> blocks into one without altering flat text concatenation.
            merged = ch1.replace(b"<p>Alpha</p><p>Beta", b"<p>Alpha Beta")
            epub_safe.replace_members(src, merged_para, {"OPS/ch1.xhtml": merged})
            with self.assertRaisesRegex(ValueError, "Reading text or block structure changed"):
                epub_safe.compare_epubs(src, merged_para, preserve_text=True)

            # Change indentation inside <pre> block.
            changed_pre = ch1.replace(b"    y = 2", b"  y = 2")
            epub_safe.replace_members(src, ws_changed, {"OPS/ch1.xhtml": changed_pre})
            with self.assertRaisesRegex(ValueError, "Reading text or block structure changed"):
                epub_safe.compare_epubs(src, ws_changed, preserve_text=True)

    def test_compare_epubs_supports_expected_added_removed_changed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.epub"
            cand = root / "cand.epub"
            make_bilingual_epub3(src)
            with ZipFile(src) as z_in, ZipFile(cand, "w") as z_out:
                for info in z_in.infolist():
                    if info.filename == "OPS/figure.png":
                        continue
                    z_out.writestr(info, z_in.read(info))
                z_out.writestr("OPS/figure2.png", make_valid_png(16, 16))

            report = epub_safe.compare_epubs(
                src,
                cand,
                expected_added={"OPS/figure2.png"},
                expected_removed={"OPS/figure.png"},
                expected_changed=set(),
            )
            self.assertEqual(report["added"], ["OPS/figure2.png"])
            self.assertEqual(report["removed"], ["OPS/figure.png"])

    def test_compare_epubs_reports_skipped_svg_and_nav_spine_docs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.epub"
            cand = root / "cand.epub"
            make_bilingual_epub3(src)
            with ZipFile(src) as z_in, ZipFile(cand, "w") as z_out:
                for info in z_in.infolist():
                    data = z_in.read(info)
                    if info.filename == "OPS/package.opf":
                        data = data.replace(
                            b"</manifest>",
                            b'<item id="svg1" href="page.svg" media-type="image/svg+xml"/></manifest>',
                        ).replace(
                            b"</spine>",
                            b'<itemref idref="svg1"/><itemref idref="nav"/></spine>',
                        )
                    z_out.writestr(info, data)
                z_out.writestr("OPS/page.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>')
            cand2 = root / "cand2.epub"
            cand2.write_bytes(cand.read_bytes())
            report = epub_safe.compare_epubs(cand, cand2, preserve_spine=True, preserve_text=True)
            self.assertEqual(report["inspected_reading_docs"], ["OPS/ch1.xhtml"])
            self.assertEqual(report["skipped_reading_docs"], ["OPS/nav.xhtml", "OPS/page.svg"])

    def test_zip_directory_entries_do_not_cause_false_positives_or_mask_missing_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_with_dirs = root / "with-dirs.epub"
            no_dirs = root / "no-dirs.epub"
            missing_file = root / "missing-file.epub"
            base = root / "base.epub"
            make_bilingual_epub3(base)

            with ZipFile(base) as z_in, ZipFile(src_with_dirs, "w") as z_out:
                z_out.writestr("mimetype", epub_safe.MEDIA_TYPE, compress_type=ZIP_STORED)
                z_out.writestr("META-INF/", b"")
                z_out.writestr("OPS/", b"")
                for info in z_in.infolist():
                    if info.filename != "mimetype":
                        z_out.writestr(info, z_in.read(info))

            # 1. Removing only explicit directory entries passes comparison
            no_dirs.write_bytes(base.read_bytes())
            diff = epub_safe.compare_epubs(
                src_with_dirs,
                no_dirs,
                expected_added=set(),
                expected_removed=set(),
                expected_changed=set(),
                preserve_spine=True,
                preserve_text=True,
            )
            self.assertEqual(diff["removed"], [])

            # 2. Removing a real file inside a directory fails comparison
            with ZipFile(base) as z_in, ZipFile(missing_file, "w") as z_out:
                for info in z_in.infolist():
                    if info.filename != "OPS/figure.png":
                        z_out.writestr(info, z_in.read(info))
            with self.assertRaisesRegex(ValueError, "Removed members"):
                epub_safe.compare_epubs(src_with_dirs, missing_file, expected_removed=set())

            # 3. Surgical replacement works cleanly on an EPUB with explicit directory entries
            edited = root / "edited-dirs.epub"
            with ZipFile(src_with_dirs) as zf:
                new_opf = zf.read("OPS/package.opf").replace(b"Sample", b"Updated", 1)
            epub_safe.replace_members(src_with_dirs, edited, {"OPS/package.opf": new_opf})
            epub_safe.compare_epubs(
                src_with_dirs,
                edited,
                expected_changed={"OPS/package.opf"},
                expected_added=set(),
                expected_removed=set(),
                preserve_spine=True,
                preserve_text=True,
            )

            # 4. Passing a directory entry as a replacement target is explicitly rejected (no KeyError)
            with self.assertRaisesRegex(ValueError, "Cannot replace directory entries"):
                epub_safe.replace_members(src_with_dirs, root / "dir-replace.epub", {"OPS/": b"x"})

    def test_assert_no_new_diagnostics_blocks_regressions(self):
        before = epub_safe.Diagnostics("5.4.0", False, Counter({("WARNING", "W1", "msg", "a.xhtml", None): 1}))
        same = epub_safe.Diagnostics("5.4.0", False, Counter({("WARNING", "W1", "msg", "a.xhtml", None): 1}))
        worse = epub_safe.Diagnostics("5.4.0", False, Counter({("WARNING", "W1", "msg", "a.xhtml", None): 2}))
        epub_safe.assert_no_new_diagnostics(before, same)
        with self.assertRaisesRegex(ValueError, "New EPUBCheck diagnostics"):
            epub_safe.assert_no_new_diagnostics(before, worse)
