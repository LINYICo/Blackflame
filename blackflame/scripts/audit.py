"""Structured EPUB quality audit covering manifest, spine, nav, links, footnotes, covers, CSS, and assets."""

import posixpath
import re
import struct
from collections import Counter
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from lxml import etree

from publication import DC, OPF, XHTML, inventory, parse_xml, safe_member, xml_member

EPUB_NS = "http://www.idpf.org/2007/ops"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_ID_ATTR = "{http://www.w3.org/XML/1998/namespace}id"
APPLE_MAX_PIXELS = 5_600_000
FOOTNOTE_TOKENS = {"footnote", "endnote", "rearnote"}
IMAGE_MIME_TO_FORMAT = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}


def detect_image_info(data):
    """Inspect real image format, structural integrity, and pixel dimensions from raw bytes."""
    if not data:
        return {"format": "unknown", "valid": False, "width": "unknown", "height": "unknown", "pixels": "unknown"}

    # PNG: signature + IHDR chunk + IEND chunk
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 33 or data[12:16] != b"IHDR" or b"IEND" not in data[-16:]:
            return {"format": "png", "valid": False, "width": "unknown", "height": "unknown", "pixels": "unknown"}
        width, height = struct.unpack(">II", data[16:24])
        valid = width > 0 and height > 0
        return {
            "format": "png",
            "valid": valid,
            "width": width if valid else "unknown",
            "height": height if valid else "unknown",
            "pixels": width * height if valid else "unknown",
        }

    # GIF: header + logical screen descriptor + trailer 0x3B
    if data.startswith((b"GIF87a", b"GIF89a")):
        if len(data) < 14 or not data.endswith(b"\x3b"):
            return {"format": "gif", "valid": False, "width": "unknown", "height": "unknown", "pixels": "unknown"}
        width, height = struct.unpack("<HH", data[6:10])
        valid = width > 0 and height > 0
        return {
            "format": "gif",
            "valid": valid,
            "width": width if valid else "unknown",
            "height": height if valid else "unknown",
            "pixels": width * height if valid else "unknown",
        }

    # JPEG: SOI (FFD8) + SOF frame + EOI (FFD9)
    if data.startswith(b"\xff\xd8"):
        has_eoi = b"\xff\xd9" in data[-16:] or b"\xff\xd9" in data
        idx = 2
        width = height = None
        while idx + 4 <= len(data):
            if data[idx] != 0xFF:
                break
            while idx < len(data) and data[idx] == 0xFF:
                idx += 1
            if idx >= len(data):
                break
            marker = data[idx]
            idx += 1
            if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7):
                continue
            if idx + 2 > len(data):
                break
            seg_len = struct.unpack(">H", data[idx : idx + 2])[0]
            if seg_len < 2 or idx + seg_len > len(data):
                return {"format": "jpeg", "valid": False, "width": "unknown", "height": "unknown", "pixels": "unknown"}
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if idx + 7 <= len(data):
                    height, width = struct.unpack(">HH", data[idx + 3 : idx + 7])
                break
            idx += seg_len
        if width and height and has_eoi:
            return {"format": "jpeg", "valid": True, "width": width, "height": height, "pixels": width * height}
        return {"format": "jpeg", "valid": False, "width": "unknown", "height": "unknown", "pixels": "unknown"}

    # WebP: RIFF header + size check + VP8 / VP8L / VP8X dimensions
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        riff_size = struct.unpack("<I", data[4:8])[0]
        if len(data) < riff_size + 8 or len(data) < 20:
            return {"format": "webp", "valid": False, "width": "unknown", "height": "unknown", "pixels": "unknown"}
        chunk = data[12:16]
        width = height = None
        if chunk == b"VP8X" and len(data) >= 30:
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
        elif chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        elif chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
            bits = struct.unpack("<I", data[21:25])[0]
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
        if width and height:
            return {"format": "webp", "valid": True, "width": width, "height": height, "pixels": width * height}
        return {"format": "webp", "valid": True, "width": "unknown", "height": "unknown", "pixels": "unknown"}

    # SVG: strict XML parse verifying root element is <svg>
    head = data[:512].lstrip()
    if head.startswith((b"<svg", b"<?xml")) and b"<svg" in head:
        try:
            root = parse_xml(data).getroot()
            is_svg = isinstance(root.tag, str) and (root.tag == "svg" or root.tag.endswith("}svg"))
            return {"format": "svg", "valid": is_svg, "width": "unknown", "height": "unknown", "pixels": "unknown"}
        except etree.LxmlError:
            return {"format": "svg", "valid": False, "width": "unknown", "height": "unknown", "pixels": "unknown"}

    return {"format": "unknown", "valid": False, "width": "unknown", "height": "unknown", "pixels": "unknown"}


def _resolve_target(origin_member, href):
    """Resolve an internal href to (member_path, fragment) or classify as remote/external/invalid."""
    if not href:
        return None, None
    stripped = href.strip()
    if not stripped:
        return None, None
    parsed = urlsplit(stripped)
    if parsed.scheme in {"http", "https", "ftp"} or stripped.startswith("//"):
        return "remote", stripped
    if parsed.scheme:
        return "external", stripped
    fragment = unquote(parsed.fragment) if parsed.fragment else None
    if not parsed.path:
        return origin_member, fragment
    path = unquote(parsed.path, errors="strict")
    if path.startswith("/"):
        return "invalid", stripped
    target = posixpath.normpath(posixpath.join(posixpath.dirname(origin_member), path))
    if not safe_member(target):
        return "invalid", stripped
    return target, fragment


def _collect_ids(root):
    """Return (unique_ids_set, duplicate_ids_list) while safely skipping XML comments and PIs."""
    seen = Counter()
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        for attr in ("id", XML_ID_ATTR, "name"):
            if val := node.get(attr):
                seen[val] += 1
    return set(seen.keys()), sorted(k for k, v in seen.items() if v > 1)


def _strip_css_comments(css_text):
    return re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)


def _extract_css_references(css_text):
    """Extract @import targets and url(...) references from CSS, handling comments, quotes, and escapes."""
    cleaned = _strip_css_comments(css_text)
    refs = []

    # 1. @import "path.css" or @import 'path.css' (without url())
    for match in re.finditer(r"@import\s+(['\"])((?:\\.|(?!\1).)*)\1", cleaned, flags=re.IGNORECASE):
        raw = re.sub(r"\\(.)", r"\1", match.group(2)).strip()
        if raw:
            refs.append(("import", raw))

    # 2. url(...) with single-quoted, double-quoted, or unquoted (including escaped parens) arguments
    url_re = re.compile(
        r"url\(\s*(?:'((?:\\.|[^'])*)'|\"((?:\\.|[^\"])*)\"|((?:\\.|[^)\s])+))\s*\)",
        flags=re.IGNORECASE,
    )
    for match in url_re.finditer(cleaned):
        raw = match.group(1) or match.group(2) or match.group(3) or ""
        raw = re.sub(r"\\(.)", r"\1", raw).strip()
        if raw and not raw.lower().startswith("data:"):
            refs.append(("url", raw))
    return refs


def audit_epub(path):
    """Produce a structured quality audit report for a single EPUB file."""
    with path.open("rb") as stream, ZipFile(stream) as archive:
        book = inventory(archive, stream)
        archive_members = set(archive.namelist())

        manifest_issues = []
        spine_issues = []
        nav_issues = []
        link_issues = []
        footnote_issues = []
        asset_issues = []
        image_issues = []
        oversized_images = []
        remote_resources = []
        external_links = []
        cover_reports = []
        required_metadata_issues = []
        optional_metadata_notes = []

        for pkg in book["packages"]:
            pkg_member = pkg["member"]
            pkg_root = parse_xml(xml_member(archive, pkg_member)).getroot()
            version = pkg.get("version") or ""

            # 1. Manifest: duplicate IDs and missing archive members.
            raw_ids = [item["id"] for item in pkg["manifest"] if item["id"] is not None]
            for item_id, count in Counter(raw_ids).items():
                if count > 1:
                    manifest_issues.append({"type": "duplicate_manifest_id", "package": pkg_member, "id": item_id})

            manifest_by_id = {item["id"]: item for item in pkg["manifest"] if item["id"] is not None}
            manifest_by_member = {item["member"]: item for item in pkg["manifest"] if item["member"] is not None}
            for item in pkg["manifest"]:
                member = item["member"]
                if member is None:
                    remote_resources.append({"source": pkg_member, "href": item["href"], "context": "manifest"})
                elif member not in archive_members:
                    manifest_issues.append(
                        {"type": "missing_manifest_resource", "package": pkg_member, "id": item["id"], "member": member}
                    )

            # 2. Spine: invalid idrefs and empty spine.
            if not pkg["spine_items"]:
                spine_issues.append({"type": "empty_spine", "package": pkg_member})
            spine_members = set()
            for ref in pkg["spine_items"]:
                idref = ref["idref"]
                if not idref or idref not in manifest_by_id:
                    spine_issues.append({"type": "invalid_spine_idref", "package": pkg_member, "idref": idref})
                elif ref["member"] not in archive_members:
                    spine_issues.append(
                        {"type": "missing_spine_member", "package": pkg_member, "idref": idref, "member": ref["member"]}
                    )
                else:
                    spine_members.add(ref["member"])

            # 3. Required vs optional metadata (missing dc:rights is informational, not non-compliance).
            meta = pkg["metadata"]
            for required_field in ("title", "identifier", "language"):
                if not meta.get(required_field):
                    required_metadata_issues.append({"type": "missing_required_metadata", "field": required_field})
            rights = pkg_root.xpath("opf:metadata/dc:rights/text()", namespaces={"opf": OPF, "dc": DC})
            if not rights:
                optional_metadata_notes.append(
                    {"type": "missing_optional_metadata", "field": "dc:rights", "compliance_impact": "none"}
                )

            # 4. Inspect ALL manifest images (covers + inline illustrations) for format, integrity, MIME, and pixel limits.
            cover_set = set(pkg["cover_members"])
            if not cover_set:
                cover_reports.append({"status": "missing_cover_declaration", "package": pkg_member})

            for item in pkg["manifest"]:
                member = item["member"]
                declared_mime = (item.get("media_type") or "").lower()
                is_cover = member in cover_set
                if not is_cover and not declared_mime.startswith("image/"):
                    continue
                if member not in archive_members:
                    if is_cover:
                        cover_reports.append({"status": "missing_cover_file", "member": member})
                    continue
                img_info = detect_image_info(archive.read(member))
                expected_fmt = IMAGE_MIME_TO_FORMAT.get(declared_mime)
                mime_match = expected_fmt is None or img_info["format"] == expected_fmt
                pixels = img_info["pixels"]
                exceeds_apple = isinstance(pixels, int) and pixels > APPLE_MAX_PIXELS
                if not img_info["valid"]:
                    image_issues.append(
                        {
                            "type": "corrupted_or_unrecognized_image",
                            "member": member,
                            "declared_mime": declared_mime,
                            **img_info,
                        }
                    )
                elif not mime_match:
                    image_issues.append(
                        {
                            "type": "image_mime_mismatch",
                            "member": member,
                            "declared_mime": declared_mime,
                            "actual_format": img_info["format"],
                        }
                    )
                if exceeds_apple:
                    oversized_images.append(
                        {
                            "member": member,
                            "is_cover": is_cover,
                            "width": img_info["width"],
                            "height": img_info["height"],
                            "pixels": pixels,
                        }
                    )
                if is_cover:
                    cover_reports.append(
                        {
                            "status": "ok" if (img_info["valid"] and mime_match) else "invalid",
                            "member": member,
                            "declared_mime": declared_mime,
                            "mime_matches_format": mime_match,
                            **img_info,
                            "exceeds_apple_books_pixel_limit": exceeds_apple,
                        }
                    )

            # 5. Parse all XHTML documents once for IDs, duplicate IDs, links, assets, footnotes, inline styles, and remote URLs.
            xhtml_members = [
                item["member"]
                for item in pkg["manifest"]
                if item["member"] in archive_members and item["media_type"] == "application/xhtml+xml"
            ]
            doc_roots = {}
            doc_ids = {}
            for member in xhtml_members:
                root = parse_xml(xml_member(archive, member)).getroot()
                doc_roots[member] = root
                ids, dup_ids = _collect_ids(root)
                doc_ids[member] = ids
                for dup in dup_ids:
                    link_issues.append({"type": "duplicate_element_id", "source": member, "id": dup})

            # 6. Navigation checks: EPUB 3 nav (non-empty TOC & chapter resolution) and EPUB 2 NCX.
            if version.startswith("3"):
                if not pkg["nav_members"]:
                    nav_issues.append({"type": "missing_epub3_nav", "package": pkg_member})
                for nav_member in pkg["nav_members"]:
                    if nav_member not in doc_roots:
                        nav_issues.append({"type": "missing_nav_file", "member": nav_member})
                        continue
                    toc_navs = doc_roots[nav_member].xpath(
                        ".//x:nav[@epub:type]", namespaces={"x": XHTML, "epub": EPUB_NS}
                    )
                    toc_navs = [n for n in toc_navs if "toc" in (n.get(f"{{{EPUB_NS}}}type") or "").split()]
                    if not toc_navs:
                        nav_issues.append({"type": "missing_toc_nav_element", "member": nav_member})
                    else:
                        toc_links = toc_navs[0].xpath(".//x:a[@href]", namespaces={"x": XHTML})
                        if not toc_links:
                            nav_issues.append({"type": "empty_epub3_toc", "member": nav_member})
            elif version.startswith("2"):
                if not pkg["ncx_id"] or not pkg["ncx_member"]:
                    nav_issues.append({"type": "missing_epub2_ncx_or_toc", "package": pkg_member})

            if pkg["ncx_member"]:
                ncx_member = pkg["ncx_member"]
                if ncx_member not in archive_members:
                    nav_issues.append({"type": "missing_ncx_file", "member": ncx_member})
                else:
                    ncx_root = parse_xml(xml_member(archive, ncx_member)).getroot()
                    ncx_targets = ncx_root.xpath(".//n:content/@src", namespaces={"n": NCX_NS})
                    if not ncx_targets:
                        nav_issues.append({"type": "empty_ncx_navmap", "source": ncx_member})
                    for content in ncx_targets:
                        target, frag = _resolve_target(ncx_member, content)
                        if target == "remote":
                            remote_resources.append({"source": ncx_member, "href": frag, "context": "ncx"})
                        elif target == "invalid" or target not in archive_members:
                            nav_issues.append({"type": "broken_ncx_target", "source": ncx_member, "href": content})
                        elif frag and target in doc_ids and frag not in doc_ids[target]:
                            nav_issues.append(
                                {
                                    "type": "missing_ncx_fragment",
                                    "source": ncx_member,
                                    "href": content,
                                    "fragment": frag,
                                }
                            )

            # 7. Links, assets (images/CSS/fonts/inline styles), external hyperlinks vs remote resources, and footnotes.
            noterefs = []
            footnote_targets = {}
            for member, root in doc_roots.items():
                # Stylesheet links
                for link in root.xpath(".//x:link[@href]", namespaces={"x": XHTML}):
                    href = link.get("href", "")
                    target, _ = _resolve_target(member, href)
                    if target == "remote":
                        remote_resources.append({"source": member, "href": href, "context": "link"})
                    elif target == "invalid" or target not in archive_members:
                        asset_issues.append({"type": "missing_linked_asset", "source": member, "href": href})

                # Inline <style> blocks and style="..." attributes
                for style_el in root.xpath(".//x:style", namespaces={"x": XHTML}):
                    if style_el.text:
                        _audit_css_text(member, style_el.text, archive_members, remote_resources, asset_issues)
                for node in root.iter():
                    if not isinstance(node.tag, str):
                        continue
                    if inline_css := node.get("style"):
                        _audit_css_text(member, inline_css, archive_members, remote_resources, asset_issues)
                    if node.tag.endswith("}image") or node.tag == "image":
                        href = node.get(f"{{{XLINK_NS}}}href") or node.get("href") or ""
                        if href:
                            target, _ = _resolve_target(member, href)
                            if target == "remote":
                                remote_resources.append({"source": member, "href": href, "context": "svg-image"})
                            elif target == "invalid" or target not in archive_members:
                                asset_issues.append({"type": "missing_image", "source": member, "href": href})
                    # Multi-token epub:type footnote/endnote/rearnote containers
                    epub_tokens = set((node.get(f"{{{EPUB_NS}}}type") or "").split())
                    if epub_tokens & FOOTNOTE_TOKENS:
                        note_id = node.get("id") or node.get(XML_ID_ATTR)
                        if note_id:
                            back_targets = set()
                            for back in node.xpath(".//x:a[@href]", namespaces={"x": XHTML}):
                                b_target, b_frag = _resolve_target(member, back.get("href", ""))
                                if b_target not in {"remote", "external", "invalid", None}:
                                    back_targets.add((b_target, b_frag))
                            footnote_targets[(member, note_id)] = back_targets

                # <img> elements
                for img in root.xpath(".//x:img[@src]", namespaces={"x": XHTML}):
                    src = img.get("src", "")
                    target, _ = _resolve_target(member, src)
                    if target == "remote":
                        remote_resources.append({"source": member, "href": src, "context": "img"})
                    elif target == "invalid" or target not in archive_members:
                        asset_issues.append({"type": "missing_image", "source": member, "href": src})

                # Anchor links: external http(s) links are recorded as external_links, NOT runtime remote resources.
                for anchor in root.xpath(".//x:a[@href]", namespaces={"x": XHTML}):
                    href = anchor.get("href", "")
                    target, frag = _resolve_target(member, href)
                    if target in {"remote", "external"}:
                        external_links.append({"source": member, "href": href})
                        continue
                    if target == "invalid" or target not in archive_members:
                        link_issues.append({"type": "broken_link", "source": member, "href": href})
                        continue
                    if frag and target in doc_ids and frag not in doc_ids[target]:
                        link_issues.append(
                            {"type": "missing_fragment", "source": member, "href": href, "fragment": frag}
                        )
                    epub_tokens = set((anchor.get(f"{{{EPUB_NS}}}type") or "").split())
                    if "noteref" in epub_tokens and frag:
                        noterefs.append((member, anchor.get("id") or anchor.get(XML_ID_ATTR), target, frag))

            for src_member, ref_id, target_member, frag in noterefs:
                key = (target_member, frag)
                if key not in footnote_targets:
                    footnote_issues.append(
                        {
                            "type": "noteref_missing_footnote_container",
                            "source": src_member,
                            "target": f"{target_member}#{frag}",
                        }
                    )
                elif ref_id and (src_member, ref_id) not in footnote_targets[key]:
                    footnote_issues.append(
                        {
                            "type": "footnote_missing_return_link",
                            "source": src_member,
                            "ref_id": ref_id,
                            "target": f"{target_member}#{frag}",
                        }
                    )

            # 8. Standalone CSS stylesheets (@import + url(...))
            for item in pkg["manifest"]:
                if item["media_type"] == "text/css" and item["member"] in archive_members:
                    css_text = archive.read(item["member"]).decode("utf-8", errors="replace")
                    _audit_css_text(item["member"], css_text, archive_members, remote_resources, asset_issues)

            # Ensure unused manifest_by_member reference stays clean for future checks
            _ = (manifest_by_member, spine_members)

        structural_ok = not any(
            (
                manifest_issues,
                spine_issues,
                nav_issues,
                link_issues,
                asset_issues,
                image_issues,
                required_metadata_issues,
            )
        )
        return {
            "entry_count": book["entry_count"],
            "protection": book["protection"],
            "packages": [
                {
                    "member": p["member"],
                    "version": p["version"],
                    "title": p["titles"],
                    "primary_identifier": p["primary_identifier"],
                    "spine_count": len(p["spine_items"]),
                }
                for p in book["packages"]
            ],
            "structural_integrity": {
                "passed": structural_ok,
                "manifest_issues": manifest_issues,
                "spine_issues": spine_issues,
                "navigation_issues": nav_issues,
                "link_issues": link_issues,
                "asset_issues": asset_issues,
                "image_issues": image_issues,
                "required_metadata_issues": required_metadata_issues,
            },
            "epubcheck_conformance": {
                "status": "not_run",
                "note": "Run `apply` or `verify` (or EPUBCheck directly) to assess W3C EPUBCheck conformance.",
            },
            "content_fidelity": {
                "status": "not_verified",
                "note": "Structural audit does not compare text or layout against a source edition; use `verify --preserve-text --preserve-spine` and visual diff review.",
            },
            "reader_compatibility": {
                "covers": cover_reports,
                "oversized_images": oversized_images,
                "footnote_issues": footnote_issues,
                "remote_resources": remote_resources,
                "external_links": external_links,
                "optional_metadata_notes": optional_metadata_notes,
            },
            "unverified_checks": [
                "W3C EPUBCheck specification conformance",
                "Textual and typographic fidelity against source edition",
                "Visual layout, typography, and popup rendering in target readers (e.g., Apple Books, Kindle)",
            ],
        }


def _audit_css_text(source_member, css_text, archive_members, remote_resources, asset_issues):
    for ref_kind, raw in _extract_css_references(css_text):
        target, _ = _resolve_target(source_member, raw)
        if target == "remote":
            remote_resources.append({"source": source_member, "href": raw, "context": f"css-{ref_kind}"})
        elif target == "invalid" or target not in archive_members:
            asset_issues.append({"type": f"missing_css_{ref_kind}", "source": source_member, "href": raw})
