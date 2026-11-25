"""Structured EPUB quality audit covering manifest, spine, nav, links, footnotes, covers, and assets."""

import posixpath
import struct
from collections import Counter
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from publication import DC, OPF, XHTML, inventory, parse_xml, safe_member, xml_member

EPUB_NS = "http://www.idpf.org/2007/ops"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
XLINK_NS = "http://www.w3.org/1999/xlink"
APPLE_MAX_PIXELS = 5_600_000


def detect_image_info(data):
    """Inspect real image format and dimensions from raw image bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return {"format": "png", "width": width, "height": height, "pixels": width * height}
    if data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return {"format": "gif", "width": width, "height": height, "pixels": width * height}
    if data.startswith(b"\xff\xd8"):
        idx = 2
        while idx + 4 <= len(data):
            if data[idx] != 0xFF:
                break
            marker = data[idx + 1]
            idx += 2
            if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7):
                continue
            if idx + 2 > len(data):
                break
            seg_len = struct.unpack(">H", data[idx : idx + 2])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if idx + 7 <= len(data):
                    height, width = struct.unpack(">HH", data[idx + 3 : idx + 7])
                    return {"format": "jpeg", "width": width, "height": height, "pixels": width * height}
                break
            idx += seg_len
        return {"format": "jpeg", "width": None, "height": None, "pixels": None}
    if data.startswith(b"RIFF") and len(data) >= 30 and data[8:12] == b"WEBP":
        return {"format": "webp", "width": None, "height": None, "pixels": None}
    head = data[:512].lstrip()
    if head.startswith((b"<svg", b"<?xml")) and b"<svg" in head:
        return {"format": "svg", "width": None, "height": None, "pixels": None}
    return {"format": "unknown", "width": None, "height": None, "pixels": None}


def _resolve_target(origin_member, href):
    """Resolve an internal href to (member_path, fragment) or return ('remote', href)."""
    if not href:
        return None, None
    stripped = href.strip()
    if not stripped:
        return None, None
    parsed = urlsplit(stripped)
    if parsed.scheme in {"http", "https", "ftp"} or stripped.startswith("//"):
        return "remote", stripped
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
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
    ids = set()
    for node in root.iter():
        for attr in ("id", "{http://www.w3.org/XML/1998/namespace}id", "name"):
            if val := node.get(attr):
                ids.add(val)
    return ids


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
        remote_resources = []
        cover_reports = []
        metadata_notes = []

        for pkg in book["packages"]:
            pkg_member = pkg["member"]
            pkg_root = parse_xml(xml_member(archive, pkg_member)).getroot()
            version = pkg.get("version") or ""

            # 1. Manifest: duplicate IDs and missing archive members.
            raw_ids = [item["id"] for item in pkg["manifest"] if item["id"] is not None]
            dup_ids = sorted(item_id for item_id, count in Counter(raw_ids).items() if count > 1)
            for item_id in dup_ids:
                manifest_issues.append({"type": "duplicate_manifest_id", "package": pkg_member, "id": item_id})

            manifest_by_id = {item["id"]: item for item in pkg["manifest"] if item["id"] is not None}
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
            for ref in pkg["spine_items"]:
                idref = ref["idref"]
                if not idref or idref not in manifest_by_id:
                    spine_issues.append({"type": "invalid_spine_idref", "package": pkg_member, "idref": idref})
                elif ref["member"] not in archive_members:
                    spine_issues.append(
                        {"type": "missing_spine_member", "package": pkg_member, "idref": idref, "member": ref["member"]}
                    )

            # 3. Bibliographic metadata & copyright presence.
            meta = pkg["metadata"]
            for required_field in ("title", "identifier", "language"):
                if not meta.get(required_field):
                    metadata_notes.append({"type": "missing_required_metadata", "field": required_field})
            rights = pkg_root.xpath("opf:metadata/dc:rights/text()", namespaces={"opf": OPF, "dc": DC})
            if not rights:
                metadata_notes.append({"type": "missing_rights_metadata", "field": "dc:rights"})

            # 4. Cover declaration, real image format, and pixel dimensions.
            if not pkg["cover_members"]:
                cover_reports.append({"status": "missing_cover_declaration", "package": pkg_member})
            for cover_member in pkg["cover_members"]:
                if cover_member not in archive_members:
                    cover_reports.append({"status": "missing_cover_file", "member": cover_member})
                    continue
                img_info = detect_image_info(archive.read(cover_member))
                exceeds_apple = bool(img_info["pixels"] and img_info["pixels"] > APPLE_MAX_PIXELS)
                cover_reports.append(
                    {
                        "status": "ok" if img_info["format"] != "unknown" else "unrecognized_format",
                        "member": cover_member,
                        **img_info,
                        "exceeds_apple_books_pixel_limit": exceeds_apple,
                    }
                )

            # 5. Parse all XHTML documents once for IDs, links, assets, footnotes, and remote URLs.
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
                doc_ids[member] = _collect_ids(root)

            # 6. Navigation checks: EPUB 3 nav and EPUB 2 NCX.
            if version.startswith("3"):
                if not pkg["nav_members"]:
                    nav_issues.append({"type": "missing_epub3_nav", "package": pkg_member})
                for nav_member in pkg["nav_members"]:
                    if nav_member not in doc_roots:
                        nav_issues.append({"type": "missing_nav_file", "member": nav_member})
                        continue
                    toc_navs = doc_roots[nav_member].xpath(
                        ".//x:nav[@epub:type='toc']", namespaces={"x": XHTML, "epub": EPUB_NS}
                    )
                    if not toc_navs:
                        nav_issues.append({"type": "missing_toc_nav_element", "member": nav_member})
            if pkg["ncx_member"]:
                ncx_member = pkg["ncx_member"]
                if ncx_member not in archive_members:
                    nav_issues.append({"type": "missing_ncx_file", "member": ncx_member})
                else:
                    ncx_root = parse_xml(xml_member(archive, ncx_member)).getroot()
                    for content in ncx_root.xpath(".//n:content/@src", namespaces={"n": NCX_NS}):
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

            # 7. Links, assets (images/CSS/fonts), remote references, and footnotes.
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

                # Images & SVG images
                for img in root.xpath(".//x:img[@src]", namespaces={"x": XHTML}):
                    src = img.get("src", "")
                    target, _ = _resolve_target(member, src)
                    if target == "remote":
                        remote_resources.append({"source": member, "href": src, "context": "img"})
                    elif target == "invalid" or target not in archive_members:
                        asset_issues.append({"type": "missing_image", "source": member, "href": src})

                for svg_img in root.iter():
                    if svg_img.tag.endswith("}image"):
                        href = svg_img.get(f"{{{XLINK_NS}}}href") or svg_img.get("href") or ""
                        if href:
                            target, _ = _resolve_target(member, href)
                            if target == "remote":
                                remote_resources.append({"source": member, "href": href, "context": "svg-image"})
                            elif target == "invalid" or target not in archive_members:
                                asset_issues.append({"type": "missing_image", "source": member, "href": href})

                # Anchor links & noterefs
                for anchor in root.xpath(".//x:a[@href]", namespaces={"x": XHTML}):
                    href = anchor.get("href", "")
                    target, frag = _resolve_target(member, href)
                    if target == "remote":
                        remote_resources.append({"source": member, "href": href, "context": "anchor"})
                        continue
                    if target == "external":
                        continue
                    if target == "invalid" or target not in archive_members:
                        link_issues.append({"type": "broken_link", "source": member, "href": href})
                        continue
                    if frag and target in doc_ids and frag not in doc_ids[target]:
                        link_issues.append(
                            {"type": "missing_fragment", "source": member, "href": href, "fragment": frag}
                        )
                    epub_type = (anchor.get(f"{{{EPUB_NS}}}type") or "").split()
                    if "noteref" in epub_type and frag:
                        noterefs.append((member, anchor.get("id"), target, frag))

                # Footnote / endnote containers and their return links
                for note in root.xpath(
                    ".//*[@epub:type='footnote' or @epub:type='endnote' or @epub:type='rearnote']",
                    namespaces={"epub": EPUB_NS},
                ):
                    note_id = note.get("id")
                    if note_id:
                        back_targets = set()
                        for back in note.xpath(".//x:a[@href]", namespaces={"x": XHTML}):
                            b_target, b_frag = _resolve_target(member, back.get("href", ""))
                            if b_target not in {"remote", "external", "invalid"}:
                                back_targets.add((b_target, b_frag))
                        footnote_targets[(member, note_id)] = back_targets

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

            # 8. CSS @font-face / url(...) checks for missing local fonts or remote fonts.
            for item in pkg["manifest"]:
                if item["media_type"] == "text/css" and item["member"] in archive_members:
                    css_text = archive.read(item["member"]).decode("utf-8", errors="replace")
                    for raw in _extract_css_urls(css_text):
                        if raw.startswith("data:"):
                            continue
                        target, _ = _resolve_target(item["member"], raw)
                        if target == "remote":
                            remote_resources.append({"source": item["member"], "href": raw, "context": "css"})
                        elif target == "invalid" or target not in archive_members:
                            asset_issues.append({"type": "missing_css_asset", "source": item["member"], "href": raw})

        structural_ok = not any((manifest_issues, spine_issues, nav_issues, link_issues, asset_issues))
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
            },
            "reader_compatibility": {
                "covers": cover_reports,
                "footnote_issues": footnote_issues,
                "remote_resources": remote_resources,
                "metadata_notes": metadata_notes,
            },
            "note": (
                "Structural audit checks package integrity, links, covers, and assets. "
                "EPUBCheck conformance and visual rendering in target readers are separate checks."
            ),
        }


def _extract_css_urls(css_text):
    urls = []
    idx = 0
    lower = css_text.lower()
    while True:
        pos = lower.find("url(", idx)
        if pos == -1:
            break
        end = css_text.find(")", pos + 4)
        if end == -1:
            break
        raw = css_text[pos + 4 : end].strip().strip("'\"")
        if raw:
            urls.append(raw)
        idx = end + 1
    return urls
