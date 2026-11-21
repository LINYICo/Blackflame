"""Regression tests for reviewed edits and EPUBCheck validation."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
from subprocess import CompletedProcess, run
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / "epublib/scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_plan import check_edit, check_text_edits, read_replacements
from publication import CONTAINER, MEDIA_TYPE, OPF, XHTML, check_zip
from validation import run_epubcheck, validate_candidate


class EditTests(unittest.TestCase):
    def setUp(self):
        self.chapter = (
            '<!DOCTYPE html SYSTEM "xhtml11.dtd">'
            f'<html xmlns="{XHTML}"><head><title>A&nbsp;B</title></head>'
            '<body><p>One <i>word</i> here.</p><p>Keep me.</p></body></html>'
        ).encode()
        self.edited = self.chapter.replace(b" here.", b" there.")
        self.edits = [{"old": " here.", "new": " there.", "count": 1}]

    def test_named_entity_and_tail(self):
        check_edit("ch", self.chapter, self.edited, False)
        check_text_edits("ch", self.chapter, self.edited, self.edits)
        with self.assertRaises(ValueError):
            check_edit("ch", self.chapter, self.edited.replace(b"&nbsp;", b"&copy;"), False)

    def test_unrelated_deletion_and_wrong_count(self):
        with self.assertRaisesRegex(ValueError, "differs from reviewed"):
            check_text_edits("ch", self.chapter, self.edited.replace(b"<p>Keep me.</p>", b""), self.edits)
        self.edits[0]["count"] = 2
        with self.assertRaisesRegex(ValueError, "match count"):
            check_text_edits("ch", self.chapter, self.edited, self.edits)


class ContainerTests(unittest.TestCase):
    def test_malformed_archive_members(self):
        for member, mime in [("../chapter", MEDIA_TYPE), ("chapter", b"invalid")]:
            with self.subTest(member=member):
                stream = BytesIO()
                with ZipFile(stream, "w") as archive:
                    archive.writestr("mimetype", mime)
                    archive.writestr(member, b"chapter")
                with ZipFile(stream) as archive, self.assertRaises(ValueError):
                    check_zip(archive, stream)

    def test_signed_package_refuses_replacement(self):
        with TemporaryDirectory() as directory:
            plan = Path(directory) / "plan"
            plan.write_text(json.dumps({"source_sha256": "digest", "replacements": {"p.opf": "p"}}))
            book = {"packages": [{}], "protection": ["META-INF/signatures.xml"]}
            with self.assertRaisesRegex(ValueError, "Protected publication"):
                read_replacements(None, book, plan, "digest")


class ReportTests(unittest.TestCase):
    def test_stale_report(self):
        with TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            report.write_text("{}")
            with patch("validation.subprocess.run", return_value=CompletedProcess([], 0, b"", b"")):
                with self.assertRaisesRegex(ValueError, "did not complete"):
                    run_epubcheck("checker", Path("source.epub"), report)

    def test_repeated_warning(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            def checker(args, **kwargs):
                locations = [{"path": "chapter.xhtml"}] * (1 if args[-1].endswith("a.epub") else 2)
                data = {"checker": {"path": args[-1], "checkerVersion": "test", "nWarning": 1,
                                    "nFatal": 0, "nError": 0},
                        "messages": [{"severity": "warning", "ID": "W", "message": "warning",
                                      "locations": locations}]}
                Path(args[-2]).write_text(json.dumps(data))
                return CompletedProcess(args, 0, b"", b"")
            with patch("validation.subprocess.run", side_effect=checker):
                before, after = [run_epubcheck("checker", root/name, root/"report.json")
                                 for name in ("a.epub", "b.epub")]
            with self.assertRaisesRegex(ValueError, "New EPUBCheck"):
                validate_candidate(before, after, root)


@unittest.skipUnless(shutil.which("epubcheck"), "requires EPUBCheck")
class WorkflowTests(unittest.TestCase):
    def test_reviewed_copy_and_exact_scope(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.epub"
            chapter = f'<html xmlns="{XHTML}" xml:lang="en"><head><title>Chapter</title></head><body><p>First.</p></body></html>'
            with ZipFile(source, "w") as archive:
                archive.writestr("mimetype", MEDIA_TYPE)
                archive.writestr(CONTAINER, '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
                archive.writestr("book.opf", f'''<package xmlns="{OPF}" version="3.0" unique-identifier="id" xml:lang="en">
                    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Sample</dc:title><dc:identifier id="id">urn:example:test</dc:identifier><dc:language>en</dc:language><meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata>
                    <manifest><item id="ch" href="c.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="ch"/></spine></package>''')
                archive.writestr("nav.xhtml", f'<html xmlns="{XHTML}" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en"><head><title>Contents</title></head><body><nav epub:type="toc"><ol><li><a href="c.xhtml">Chapter</a></li></ol></nav></body></html>')
                archive.writestr("c.xhtml", chapter)
            cli = [sys.executable, SCRIPTS / "epub_patch.py"]
            digest = json.loads(run([*cli, "inspect", source], check=True, capture_output=True).stdout)["source_sha256"]
            (root/"chapter").write_text(chapter.replace("First.", "Second."))
            (root/"plan").write_text(json.dumps({"source_sha256": digest, "replacements": {"c.xhtml": "chapter"},
                "text_edits": {"c.xhtml": [{"old": "First.", "new": "Second.", "count": 1}]}}))
            run([*cli, "apply", "source.epub", "edited.epub", "--plan", "plan", "--report-dir", "apply"], cwd=root, check=True)
            self.assertEqual(digest, sha256(source.read_bytes()).hexdigest())
            scope = {"source_sha256": digest, "added": [], "removed": [], "changed": ["c.xhtml"]}
            verify = [*cli, "verify", "source.epub", "edited.epub", "--expected-changes", "scope", "--preserve-spine", "--report-dir"]
            (root/"scope").write_text(json.dumps(scope))
            run([*verify, "verify"], cwd=root, check=True)
            scope["changed"] = []
            (root/"scope").write_text(json.dumps(scope))
            result = run([*verify, "unexpected"], cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"Unexpected changed members", result.stderr)
