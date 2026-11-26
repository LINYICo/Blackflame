"""Real integration tests for epublib, BeautifulSoup4, lxml, ebook-convert, EPUBCheck, and Blackflame.zip."""

import hashlib
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile

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
DC_NS = "http://purl.org/dc/elements/1.1/"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
MODIFIED = f".//{{{epub_safe.OPF}}}meta[@property='dcterms:modified']"
EDITED_AT = "2026-11-25T00:00:01Z"


def _metadata_example():
    guide = (REPO_ROOT / "blackflame/references/metadata.md").read_text(encoding="utf-8")
    example = guide.split("## Minimal Metadata-Only Edit", 1)[1].split("```python\n", 1)[1].split("```", 1)[0]
    namespace = {"__name__": "metadata_example"}
    exec(compile(example.replace("/abs/path/to/blackflame/scripts", str(SCRIPTS)), "metadata.md", "exec"), namespace)
    return namespace["edit_title"]


def _epubcheck_available() -> bool:
    return REQUIRE_EPUBCHECK or bool(shutil.which("epubcheck"))


def _read_opf_summary(epub_path: Path) -> dict[str, str]:
    with ZipFile(epub_path) as zf:
        container = epub_safe.parse_xml(epub_safe.read_xml_member(zf, epub_safe.CONTAINER))
        opf_member = container.xpath(
            "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
            namespaces={"c": "urn:oasis:names:tc:opendocument:xmlns:container"},
        )[0]
        opf_root = epub_safe.parse_xml(epub_safe.read_xml_member(zf, opf_member)).getroot()
    unique_id_ref = opf_root.get("unique-identifier", "")
    primary_id = ""
    for ident in opf_root.findall(f".//{{{DC_NS}}}identifier"):
        if unique_id_ref and ident.get("id") == unique_id_ref:
            primary_id = (ident.text or "").strip()
            break
    return {
        "opf_member": opf_member,
        "version": opf_root.get("version", ""),
        "unique_identifier": unique_id_ref,
        "title": (opf_root.findtext(f".//{{{DC_NS}}}title") or "").strip(),
        "creator": (opf_root.findtext(f".//{{{DC_NS}}}creator") or "").strip(),
        "language": (opf_root.findtext(f".//{{{DC_NS}}}language") or "").strip(),
        "identifier": primary_id or (opf_root.findtext(f".//{{{DC_NS}}}identifier") or "").strip(),
        "date": (opf_root.findtext(f".//{{{DC_NS}}}date") or "").strip(),
        "rights": (opf_root.findtext(f".//{{{DC_NS}}}rights") or "").strip(),
    }


def _make_multichapter_epub2(path: Path) -> None:
    """Build a valid multi-chapter EPUB 2 fixture with nested NCX, fragments, opf:scheme, and cover."""
    ch1 = (
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
        f'<html xmlns="{epub_safe.XHTML}" xml:lang="zh-CN">'
        "<head><title>第一章</title></head>"
        '<body><h1 id="c1">第一章</h1><p>第一章原始中文正文。</p></body></html>'
    )
    ch2 = (
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
        f'<html xmlns="{epub_safe.XHTML}" xml:lang="zh-CN">'
        "<head><title>第二章</title></head>"
        '<body><h1 id="c2">第二章</h1><h2 id="sec-2-1">第二节</h2><p>Second chapter original body.</p></body></html>'
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", epub_safe.MEDIA_TYPE, compress_type=ZIP_STORED)
        archive.writestr(
            epub_safe.CONTAINER,
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            f'<package xmlns="{epub_safe.OPF}" version="2.0" unique-identifier="uid">'
            f'<metadata xmlns:dc="{DC_NS}" xmlns:opf="{epub_safe.OPF}">'
            "<dc:title>旧版多章节测试书</dc:title>"
            "<dc:creator>Test Author</dc:creator>"
            '<dc:identifier id="uid" opf:scheme="UUID">urn:uuid:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee</dc:identifier>'
            "<dc:language>zh-CN</dc:language>"
            "<dc:date>2020-05-01</dc:date>"
            "<dc:rights>Copyright 2020 Original Publisher</dc:rights>"
            '<meta name="cover" content="cov"/>'
            "</metadata>"
            "<manifest>"
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="cov" href="cover.png" media-type="image/png"/>'
            "</manifest>"
            '<spine toc="ncx"><itemref idref="ch1"/><itemref idref="ch2"/></spine></package>',
        )
        archive.writestr(
            "OEBPS/toc.ncx",
            f'<ncx xmlns="{NCX_NS}" version="2005-1">'
            '<head><meta name="dtb:uid" content="urn:uuid:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"/>'
            '<meta name="dtb:depth" content="3"/><meta name="dtb:totalPageCount" content="0"/>'
            '<meta name="dtb:maxPageNumber" content="0"/></head>'
            "<docTitle><text>旧版多章节测试书</text></docTitle>"
            "<navMap>"
            '<navPoint id="np-1" playOrder="1"><navLabel><text>第一章</text></navLabel><content src="ch1.xhtml"/>'
            '<navPoint id="np-2" playOrder="2"><navLabel><text>第二章</text></navLabel><content src="ch2.xhtml#c2"/>'
            '<navPoint id="np-3" playOrder="3"><navLabel><text>第二节</text></navLabel><content src="ch2.xhtml#sec-2-1"/></navPoint>'
            "</navPoint></navPoint></navMap></ncx>",
        )
        archive.writestr("OEBPS/ch1.xhtml", ch1)
        archive.writestr("OEBPS/ch2.xhtml", ch2)
        archive.writestr("OEBPS/cover.png", make_valid_png(20, 30))


class RealToolIntegrationTests(unittest.TestCase):
    def test_surgical_metadata_edit_changes_only_opf_and_preserves_all_other_resources(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "book.epub"
            out = root / "edited-meta.epub"
            make_bilingual_epub3(src, title="旧书名 Old Title")
            src_sha = epub_safe.sha256_file(src)

            opf_member = _read_opf_summary(src)["opf_member"]
            edit_title = _metadata_example()
            self.assertFalse(edit_title(src, out, "旧书名 Old Title"))
            self.assertFalse(out.exists())
            self.assertTrue(edit_title(src, out, "修订书名 Verified Title"))
            with ZipFile(src) as before_zip, ZipFile(out) as after_zip:
                before_opf = epub_safe.parse_xml(epub_safe.read_xml_member(before_zip, opf_member))
                after_opf = epub_safe.parse_xml(epub_safe.read_xml_member(after_zip, opf_member))
            timestamps = after_opf.findall(MODIFIED)
            self.assertEqual(len(timestamps), 1)
            self.assertRegex(timestamps[0].text, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            self.assertNotEqual(timestamps[0].text, before_opf.findtext(MODIFIED))
            before_opf.find(f".//{{{DC_NS}}}title").text = "修订书名 Verified Title"
            before_opf.find(MODIFIED).text = timestamps[0].text
            self.assertEqual(etree.tostring(before_opf), etree.tostring(after_opf))

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

    def test_metadata_example_rejects_duplicate_modified_and_restores_missing_entry(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "book.epub"
            make_bilingual_epub3(src)
            opf_member = _read_opf_summary(src)["opf_member"]
            edit_title = _metadata_example()
            for count in (0, 2):
                with self.subTest(timestamps=count), ZipFile(src) as zf:
                    opf = epub_safe.parse_xml(epub_safe.read_xml_member(zf, opf_member))
                    timestamp = opf.find(MODIFIED)
                    meta = timestamp.getparent()
                    if count == 0:
                        meta.remove(timestamp)
                    else:
                        etree.SubElement(meta, timestamp.tag, property="dcterms:modified").text = EDITED_AT
                    variant = root / f"source-{count}.epub"
                    out = root / f"edited-{count}.epub"
                    epub_safe.replace_members(src, variant, {opf_member: etree.tostring(opf)})
                    source_hash = epub_safe.sha256_file(variant)
                    if count == 2:
                        with self.assertRaisesRegex(ValueError, "Multiple unrefined dcterms:modified"):
                            edit_title(variant, out, "Verified Title")
                        self.assertFalse(out.exists())
                    else:
                        self.assertTrue(edit_title(variant, out, "Verified Title"))
                        with ZipFile(out) as edited:
                            updated = epub_safe.parse_xml(epub_safe.read_xml_member(edited, opf_member))
                        self.assertEqual(len(updated.findall(MODIFIED)), 1)
                    self.assertEqual(epub_safe.sha256_file(variant), source_hash)

    def test_epub2_and_epub3_surgical_body_editing_with_bs4_lxml(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src3 = root / "book3.epub"
            out3 = root / "edited3.epub"
            make_bilingual_epub3(src3, body_zh="这里有一个<em>错别字</em>需要修正。")
            opf_member = _read_opf_summary(src3)["opf_member"]
            with ZipFile(src3) as zf:
                raw3 = epub_safe.read_xml_member(zf, "OPS/ch1.xhtml")
                original_opf = epub_safe.parse_xml(epub_safe.read_xml_member(zf, opf_member))
            original_opf.find(MODIFIED).text = EDITED_AT
            expected_opf = etree.tostring(original_opf)
            soup3 = BeautifulSoup(raw3, "xml")
            em_node = soup3.find("em")
            self.assertIsNotNone(em_node)
            for leaf in em_node.descendants:
                if isinstance(leaf, str) and "错别字" in leaf:
                    leaf.replace_with(str(leaf).replace("错别字", "准确词", 1))
                    break
            new3 = soup3.encode("utf-8")
            self.assertIn(b"<em>", new3)
            self.assertIn(b'href="#fn1"', new3)
            epub_safe.parse_xml(new3)
            epub_safe.replace_members(src3, out3, {"OPS/ch1.xhtml": new3, opf_member: expected_opf})
            diff3 = epub_safe.compare_epubs(
                src3, out3, expected_changed={"OPS/ch1.xhtml", opf_member}, preserve_spine=True
            )
            self.assertEqual(diff3["unchanged_entries"], 5)
            with ZipFile(out3) as zf:
                updated_opf = epub_safe.parse_xml(epub_safe.read_xml_member(zf, opf_member))
            self.assertEqual(updated_opf.findtext(MODIFIED), EDITED_AT)
            self.assertEqual(etree.tostring(updated_opf), expected_opf)

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

    def test_epub2_to_epub_latest_three_stage_migration_and_metadata_edit(self):
        """Migrate a multi-chapter EPUB 2 by dynamically parsing its NCX and XHTML chapters."""

        def _ncx_points_to_ol(points: list[etree._Element]) -> etree._Element:
            ol = etree.Element(f"{{{epub_safe.XHTML}}}ol")
            for pt in points:
                label = (pt.findtext(f"{{{NCX_NS}}}navLabel/{{{NCX_NS}}}text") or "").strip()
                content = pt.find(f"{{{NCX_NS}}}content")
                li = etree.SubElement(ol, f"{{{epub_safe.XHTML}}}li")
                a = etree.SubElement(li, f"{{{epub_safe.XHTML}}}a", href=content.get("src", ""))
                a.text = label
                children = pt.findall(f"{{{NCX_NS}}}navPoint")
                if children:
                    li.append(_ncx_points_to_ol(children))
            return ol

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src2 = root / "legacy-v2.epub"
            migrated = root / "migrated-latest.epub"
            final_out = root / "final-latest.epub"
            _make_multichapter_epub2(src2)
            src_sha = epub_safe.sha256_file(src2)
            src_summary = _read_opf_summary(src2)
            self.assertEqual(src_summary["version"], "2.0")

            # Stage 1 -> Stage 2: Dynamically build XHTML5 nav from original NCX and upgrade original XHTML chapters.
            with ZipFile(src2) as z_in:
                ncx_root = epub_safe.parse_xml(z_in.read("OEBPS/toc.ncx")).getroot()
                nav_map = ncx_root.find(f"{{{NCX_NS}}}navMap")
                epub_ns = "http://www.idpf.org/2007/ops"
                nav_html = etree.Element(f"{{{epub_safe.XHTML}}}html", nsmap={None: epub_safe.XHTML, "epub": epub_ns})
                nav_html.set("{http://www.w3.org/XML/1998/namespace}lang", src_summary["language"])
                head = etree.SubElement(nav_html, f"{{{epub_safe.XHTML}}}head")
                etree.SubElement(head, f"{{{epub_safe.XHTML}}}meta", charset="utf-8")
                etree.SubElement(head, f"{{{epub_safe.XHTML}}}title").text = "Contents"
                body = etree.SubElement(nav_html, f"{{{epub_safe.XHTML}}}body")
                nav_el = etree.SubElement(body, f"{{{epub_safe.XHTML}}}nav", {f"{{{epub_ns}}}type": "toc"})
                nav_el.append(_ncx_points_to_ol(nav_map.findall(f"{{{NCX_NS}}}navPoint")))
                nav_bytes = etree.tostring(nav_html, doctype="<!DOCTYPE html>", xml_declaration=True, encoding="utf-8")

                with ZipFile(migrated, "w") as z_out:
                    for info in z_in.infolist():
                        if info.filename == "mimetype":
                            z_out.writestr(info, epub_safe.MEDIA_TYPE)
                        elif info.filename == "OEBPS/content.opf":
                            opf = epub_safe.parse_xml(z_in.read(info))
                            opf_root = opf.getroot()
                            opf_root.set("version", "3.0")
                            meta_el = opf_root.find(f"{{{epub_safe.OPF}}}metadata")
                            for ident in meta_el.findall(f"{{{DC_NS}}}identifier"):
                                scheme = ident.attrib.pop(f"{{{epub_safe.OPF}}}scheme", None)
                                if scheme and ident.get("id"):
                                    ref = etree.SubElement(
                                        meta_el,
                                        f"{{{epub_safe.OPF}}}meta",
                                        refines=f"#{ident.get('id')}",
                                        property="identifier-type",
                                    )
                                    ref.text = scheme
                            etree.SubElement(
                                meta_el, f"{{{epub_safe.OPF}}}meta", property="dcterms:modified"
                            ).text = "2026-11-25T00:00:00Z"
                            manifest = opf_root.find(f"{{{epub_safe.OPF}}}manifest")
                            etree.SubElement(
                                manifest,
                                f"{{{epub_safe.OPF}}}item",
                                id="nav",
                                href="nav.xhtml",
                                properties="nav",
                                **{"media-type": "application/xhtml+xml"},
                            )
                            for item in manifest:
                                if item.get("id") == "cov":
                                    item.set("properties", "cover-image")
                            z_out.writestr(info, etree.tostring(opf, xml_declaration=True, encoding="utf-8"))
                        elif info.filename.endswith(".xhtml"):
                            ch_tree = epub_safe.parse_xml(z_in.read(info))
                            ch_bytes = etree.tostring(
                                ch_tree.getroot(), doctype="<!DOCTYPE html>", xml_declaration=True, encoding="utf-8"
                            )
                            z_out.writestr(info, ch_bytes)
                        else:
                            z_out.writestr(info, z_in.read(info))
                    z_out.writestr("OEBPS/nav.xhtml", nav_bytes)

            # Verify Original source -> Migrated baseline
            with ZipFile(src2) as z_src:
                src_cover_sha = hashlib.sha256(z_src.read("OEBPS/cover.png")).hexdigest()
                src_ncx_sha = hashlib.sha256(z_src.read("OEBPS/toc.ncx")).hexdigest()

            mig_summary = _read_opf_summary(migrated)
            self.assertEqual(mig_summary["version"], "3.0")
            for field in ("unique_identifier", "identifier", "creator", "language", "date", "rights"):
                self.assertEqual(mig_summary[field], src_summary[field])
            mig_diff = epub_safe.compare_epubs(
                src2,
                migrated,
                expected_changed={"OEBPS/content.opf", "OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml"},
                expected_added={"OEBPS/nav.xhtml"},
                expected_removed=set(),
                preserve_spine=True,
                preserve_text=True,
            )
            self.assertEqual(mig_diff["added"], ["OEBPS/nav.xhtml"])
            self.assertEqual(mig_diff["removed"], [])
            with ZipFile(migrated) as zf:
                self.assertEqual(hashlib.sha256(zf.read("OEBPS/cover.png")).hexdigest(), src_cover_sha)
                self.assertEqual(hashlib.sha256(zf.read("OEBPS/toc.ncx")).hexdigest(), src_ncx_sha)
                self.assertEqual(epub_safe.image_dimensions(zf.read("OEBPS/cover.png")), (20, 30))

                # Verify TOC hierarchy and real fragment targets in target XHTML docs.
                nav_root = epub_safe.parse_xml(zf.read("OEBPS/nav.xhtml")).getroot()
                toc_nav = nav_root.find(f".//{{{epub_safe.XHTML}}}nav[@{{{epub_ns}}}type='toc']")
                self.assertIsNotNone(toc_nav)
                top_lis = toc_nav.findall(f"{{{epub_safe.XHTML}}}ol/{{{epub_safe.XHTML}}}li")
                self.assertEqual(len(top_lis), 1)
                self.assertEqual(top_lis[0].find(f"{{{epub_safe.XHTML}}}a").get("href"), "ch1.xhtml")
                lvl2_lis = top_lis[0].findall(f"{{{epub_safe.XHTML}}}ol/{{{epub_safe.XHTML}}}li")
                self.assertEqual(len(lvl2_lis), 1)
                self.assertEqual(lvl2_lis[0].find(f"{{{epub_safe.XHTML}}}a").get("href"), "ch2.xhtml#c2")
                lvl3_lis = lvl2_lis[0].findall(f"{{{epub_safe.XHTML}}}ol/{{{epub_safe.XHTML}}}li")
                self.assertEqual(len(lvl3_lis), 1)
                self.assertEqual(lvl3_lis[0].find(f"{{{epub_safe.XHTML}}}a").get("href"), "ch2.xhtml#sec-2-1")
                for link in toc_nav.findall(f".//{{{epub_safe.XHTML}}}a"):
                    href = link.get("href", "")
                    doc_href, _, frag = href.partition("#")
                    member = f"OEBPS/{doc_href}"
                    self.assertIn(member, zf.namelist())
                    if frag:
                        target_doc = epub_safe.parse_xml(zf.read(member))
                        self.assertTrue(
                            target_doc.xpath(f"//*[@id='{frag}']"),
                            f"Missing fragment target #{frag} in {member}",
                        )
                mig_opf = epub_safe.parse_xml(zf.read("OEBPS/content.opf")).getroot()
                mig_modified = [
                    m
                    for m in mig_opf.findall(f".//{{{epub_safe.OPF}}}meta[@property='dcterms:modified']")
                    if not m.get("refines")
                ]
                self.assertEqual(len(mig_modified), 1)
                self.assertRegex((mig_modified[0].text or "").strip(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

            # Stage 2 -> Stage 3: Surgical OPF metadata edit on migrated baseline (updating dcterms:modified)
            with ZipFile(migrated) as zf:
                opf = epub_safe.parse_xml(zf.read("OEBPS/content.opf"))
            opf.find(f".//{{{DC_NS}}}title").text = "新版核实书名"
            fin_mod = [
                m
                for m in opf.findall(f".//{{{epub_safe.OPF}}}meta[@property='dcterms:modified']")
                if not m.get("refines")
            ]
            self.assertEqual(len(fin_mod), 1)
            fin_mod[0].text = "2026-11-25T00:00:01Z"
            epub_safe.replace_members(
                migrated,
                final_out,
                {"OEBPS/content.opf": etree.tostring(opf, xml_declaration=True, encoding="utf-8")},
            )
            epub_safe.compare_epubs(
                migrated,
                final_out,
                expected_changed={"OEBPS/content.opf"},
                expected_added=set(),
                expected_removed=set(),
                preserve_spine=True,
                preserve_text=True,
            )
            final_summary = _read_opf_summary(final_out)
            self.assertEqual(final_summary["version"], "3.0")
            self.assertEqual(final_summary["title"], "新版核实书名")
            for field in ("unique_identifier", "identifier", "creator", "language", "date", "rights"):
                self.assertEqual(final_summary[field], src_summary[field])
            with ZipFile(final_out) as zf:
                self.assertEqual(hashlib.sha256(zf.read("OEBPS/cover.png")).hexdigest(), src_cover_sha)
                self.assertEqual(hashlib.sha256(zf.read("OEBPS/toc.ncx")).hexdigest(), src_ncx_sha)
                final_opf = epub_safe.parse_xml(zf.read("OEBPS/content.opf")).getroot()
                final_modified = [
                    m
                    for m in final_opf.findall(f".//{{{epub_safe.OPF}}}meta[@property='dcterms:modified']")
                    if not m.get("refines")
                ]
                self.assertEqual(len(final_modified), 1)
                self.assertEqual((final_modified[0].text or "").strip(), "2026-11-25T00:00:01Z")
            self.assertEqual(epub_safe.sha256_file(src2), src_sha)

            if _epubcheck_available():
                ec_src = epub_safe.run_epubcheck(src2, root / "mig-src.json")
                ec_mig = epub_safe.run_epubcheck(migrated, root / "mig-base.json")
                ec_fin = epub_safe.run_epubcheck(final_out, root / "mig-final.json")
                epub_safe.assert_no_new_diagnostics(ec_src, ec_mig)
                epub_safe.assert_no_new_diagnostics(ec_mig, ec_fin)
                self.assertFalse(ec_src.has_errors)
                self.assertFalse(ec_mig.has_errors)
                self.assertFalse(ec_fin.has_errors)

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

            summary = _read_opf_summary(out_epub)
            self.assertEqual(summary["version"], "3.0")
            self.assertEqual(summary["title"], "转换测试 Converted")
            self.assertEqual(summary["creator"], "Test Author")
            self.assertTrue(summary["language"].startswith("zh"))

            with out_epub.open("rb") as stream, ZipFile(stream) as zf:
                names = epub_safe.check_zip(zf, stream)
                spines, _, _ = epub_safe._spine_and_docs(zf, names, read_text=True)
                spine_members = [m for _, _, seq in spines for m, _ in seq]
                spine_text = "\n".join(BeautifulSoup(zf.read(m), "xml").get_text() for m in spine_members)
                pos1 = spine_text.find("第一段中文正文")
                pos2 = spine_text.find("第二段中文正文")
                self.assertTrue(0 <= pos1 < pos2, "Expected Chapter One content before Chapter Two content in spine")
                self.assertIn("English paragraph one", spine_text)
                self.assertIn("English paragraph two", spine_text)
                png_members = [n for n in names if n.lower().endswith(".png")]
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
                forbidden = ("__pycache__", ".venv", "tests/", "skill.py", "runtime.py", "audit.py", "uv.lock", ".epub")
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

with ZipFile(src) as zf:
    c = epub_safe.parse_xml(epub_safe.read_xml_member(zf, epub_safe.CONTAINER))
    opf_member = c.xpath(
        "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
        namespaces={{"c": "urn:oasis:names:tc:opendocument:xmlns:container"}},
    )[0]
    opf = epub_safe.parse_xml(epub_safe.read_xml_member(zf, opf_member))
opf.find(".//{{http://purl.org/dc/elements/1.1/}}title").text = "Standalone Verified"
modified = opf.find({MODIFIED!r})
modified.text = {EDITED_AT!r}
epub_safe.replace_members(src, meta_out, {{opf_member: etree.tostring(opf, xml_declaration=True, encoding="utf-8")}})
epub_safe.compare_epubs(src, meta_out, expected_changed={{opf_member}}, preserve_spine=True, preserve_text=True)

with ZipFile(meta_out) as zf:
    raw = zf.read("OPS/ch1.xhtml")
soup = BeautifulSoup(raw, "xml")
assert any("独立包测试错别字" in p.get_text() for p in soup.select("p"))
updated_ch = raw.replace("独立包测试错别字".encode(), "独立包已校对".encode(), 1)
epub_safe.parse_xml(updated_ch)
modified.text = "2026-11-25T00:00:02Z"
opf_data = etree.tostring(opf, xml_declaration=True, encoding="utf-8")
epub_safe.replace_members(meta_out, body_out, {{"OPS/ch1.xhtml": updated_ch, opf_member: opf_data}})
epub_safe.compare_epubs(meta_out, body_out, expected_changed={{"OPS/ch1.xhtml", opf_member}}, preserve_spine=True)
with ZipFile(body_out) as zf:
    delivered_opf = epub_safe.parse_xml(epub_safe.read_xml_member(zf, opf_member))
assert delivered_opf.findtext({MODIFIED!r}) == "2026-11-25T00:00:02Z"

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
                    "--authors",
                    "Standalone Author",
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
            conv_summary = _read_opf_summary(epub_out)
            self.assertEqual(conv_summary["version"], "3.0")
            self.assertEqual(conv_summary["title"], "Standalone")
            self.assertEqual(conv_summary["creator"], "Standalone Author")
            self.assertTrue(conv_summary["language"].startswith("en"))
            if run_ec:
                diag = epub_safe.run_epubcheck(epub_out, work / "ec-conv.json")
                self.assertFalse(diag.has_errors)
