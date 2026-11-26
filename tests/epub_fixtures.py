"""Generated EPUB and image fixtures shared by the regression suite."""

import struct
import zlib
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import epub_safe

DC_NS = "http://purl.org/dc/elements/1.1/"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"


def make_valid_png(width: int = 16, height: int = 24) -> bytes:
    """Generate a genuinely valid, decodable RGB PNG using Python stdlib zlib + struct."""

    def _chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw_rows = b"".join(b"\x00" + (b"\x40\x80\xc0" * width) for _ in range(height))
    idat = zlib.compress(raw_rows)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def make_bilingual_epub3(
    path: Path,
    *,
    title: str = "Sample 双语测试书",
    body_en: str = "Original English paragraph.",
    body_zh: str = "这是原始中文正文段落。",
    code_block: str = "def demo():\n    return 42",
) -> None:
    """Build a valid, reusable bilingual EPUB 3 fixture with genuine PNG cover/image, footnotes, and <pre>."""
    chapter = (
        f'<html xmlns="{epub_safe.XHTML}" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">'
        "<head><title>Chapter 1 第一章</title></head>"
        "<body>"
        "<h1>Chapter 1 第一章</h1>"
        f"<p>{body_en}</p>"
        f'<p>{body_zh}<a id="ref1" epub:type="noteref" href="#fn1">[1]</a></p>'
        f"<pre>{code_block}</pre>"
        '<p><img src="figure.png" alt="Figure 1"/></p>'
        '<aside id="fn1" epub:type="footnote"><p>Footnote text 脚注内容 <a href="#ref1">↩</a></p></aside>'
        "</body></html>"
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
            f'<package xmlns="{epub_safe.OPF}" version="3.0" unique-identifier="pub-id" xml:lang="zh-CN">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<dc:title>{title}</dc:title>"
            "<dc:creator>Test Author 测试作者</dc:creator>"
            '<dc:identifier id="pub-id">urn:uuid:12345678-1234-5678-1234-567812345678</dc:identifier>'
            "<dc:language>zh-CN</dc:language>"
            "<dc:rights>Copyright 2026 Test Fixture</dc:rights>"
            '<meta property="dcterms:modified">2026-11-25T00:00:00Z</meta>'
            "</metadata>"
            "<manifest>"
            '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
            '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="cov" href="cover.png" properties="cover-image" media-type="image/png"/>'
            '<item id="fig" href="figure.png" media-type="image/png"/>'
            "</manifest>"
            '<spine><itemref idref="ch1"/></spine></package>',
        )
        archive.writestr(
            "OPS/nav.xhtml",
            f'<html xmlns="{epub_safe.XHTML}" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">'
            "<head><title>Contents 目录</title></head>"
            '<body><nav epub:type="toc"><ol><li><a href="ch1.xhtml">Chapter 1 第一章</a></li></ol></nav>'
            "</body></html>",
        )
        archive.writestr("OPS/ch1.xhtml", chapter)
        archive.writestr("OPS/cover.png", make_valid_png(24, 36))
        archive.writestr("OPS/figure.png", make_valid_png(16, 16))


def make_multichapter_epub2(path: Path) -> None:
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
