"""Deterministic safety, surgical ZIP replacement, fidelity checks, and EPUBCheck diff helpers."""

import json
import os
import posixpath
import re
import stat
import struct
import subprocess
from bisect import bisect_left
from collections import Counter
from collections.abc import Iterator
from copy import copy
from hashlib import file_digest, sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from lxml import etree

CONTAINER = "META-INF/container.xml"
MEDIA_TYPE = b"application/epub+zip"
OPF = "http://www.idpf.org/2007/opf"
XHTML = "http://www.w3.org/1999/xhtml"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
PROTECTION = frozenset({"META-INF/encryption.xml", "META-INF/rights.xml", "META-INF/signatures.xml"})
APPLE_MAX_IMAGE_PIXELS = 5_600_000
LIMIT_MEMBER = 256 * 1024**2
LIMIT_TOTAL = 2 * 1024**3
LIMIT_XML = 16 * 1024**2
CHUNK_SIZE = 1024**2

_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
)
_PREFORMATTED_TAGS = frozenset({"pre", "code", "textarea"})


class Diagnostics(NamedTuple):
    version: str
    has_errors: bool
    occurrences: Counter


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _ensure_distinct_destination(source: Path, destination: Path, label: str) -> None:
    """Reject any output, report, or log path that resolves or links to the source file."""
    src_resolved = source.resolve()
    dst_resolved = destination.resolve()
    _require(dst_resolved != src_resolved, f"{label} path must not overwrite the source EPUB: {destination}")
    if os.path.lexists(destination) and destination.exists():
        _require(
            not os.path.samefile(source, destination),
            f"{label} path refers to the same file as the source EPUB: {destination}",
        )


def parse_xml(data: bytes) -> etree._ElementTree:
    """Strictly parse XML/XHTML within LIMIT_XML with external entities and network DTD loading disabled."""
    _require(len(data) <= LIMIT_XML, f"XML payload exceeds size limit ({LIMIT_XML} bytes)")
    parser = etree.XMLParser(
        no_network=True,
        load_dtd=False,
        resolve_entities=False,
        strip_cdata=False,
        recover=False,
        huge_tree=False,
    )
    return etree.parse(BytesIO(data), parser)


def read_xml_member(archive: ZipFile, name: str) -> bytes:
    """Read an XML ZIP member after checking its expanded size."""
    info = archive.getinfo(name)
    _require(not info.is_dir(), f"XML member is a directory: {name}")
    _require(info.file_size <= LIMIT_XML, f"XML member exceeds size limit: {name}")
    return archive.read(info)


def safe_member(name: str) -> bool:
    """Reject empty, traversal (..), Windows separator, NUL, or drive-letter ZIP paths."""
    parts = name.removesuffix("/").split("/")
    return all(part and part not in {".", ".."} for part in parts) and not any(ch in name for ch in ("\\", "\0", ":"))


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return file_digest(handle, "sha256").hexdigest()


def check_zip(archive: ZipFile, stream) -> set[str]:
    """Validate EPUB ZIP container safety, mimetype header, uniqueness, and size bounds."""
    infos = archive.infolist()
    _require(0 < len(infos) <= 50_000, "ZIP entry count outside supported limits")
    mime = infos[0]
    _require(mime.filename == "mimetype", "mimetype must be the first ZIP entry")
    _require(
        mime.header_offset == 0
        and mime.compress_type == ZIP_STORED
        and not mime.extra
        and mime.file_size == len(MEDIA_TYPE),
        "Invalid mimetype ZIP entry",
    )
    stream.seek(0)
    header = stream.read(30)
    _require(len(header) == 30 and header[:4] == b"PK\x03\x04", "Invalid mimetype local ZIP header")
    flags, method = struct.unpack_from("<HH", header, 6)
    extra_size = struct.unpack_from("<H", header, 28)[0]
    _require(
        not (flags & 1) and method == ZIP_STORED and extra_size == 0,
        "Invalid mimetype local ZIP flags, compression, or extra field",
    )
    names: set[str] = set()
    total_size = 0
    for info in infos:
        name = info.filename
        _require(info.orig_filename == name and safe_member(name), f"Unsafe ZIP path: {name!r}")
        _require(name not in names, f"Duplicate ZIP entry: {name}")
        _require(not (info.flag_bits & 1), f"Encrypted ZIP entry: {name}")
        _require(not stat.S_ISLNK(info.external_attr >> 16), f"ZIP symlink: {name}")
        _require(info.compress_type in {ZIP_STORED, ZIP_DEFLATED}, f"Unsupported ZIP compression: {name}")
        _require(info.file_size <= LIMIT_MEMBER, f"ZIP entry exceeds size limit: {name}")
        total_size += info.file_size
        _require(total_size <= LIMIT_TOTAL, "ZIP expanded size exceeds limit")
        names.add(name)
    ordered_names = sorted(names)
    for name in ordered_names:
        if name.endswith("/"):
            continue
        prefix = name + "/"
        index = bisect_left(ordered_names, prefix)
        _require(
            index == len(ordered_names) or not ordered_names[index].startswith(prefix),
            f"ZIP file and directory conflict: {name}",
        )
    _require(archive.read(mime) == MEDIA_TYPE, "Unexpected mimetype content")
    return names


def protection_entries(names: set[str]) -> list[str]:
    return sorted(PROTECTION & names)


def archive_hashes(archive: ZipFile) -> dict[str, str]:
    """Return SHA-256 digests for all file members in the archive, ignoring empty directory entries."""
    result: dict[str, str] = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        with archive.open(info) as handle:
            result[info.filename] = file_digest(handle, "sha256").hexdigest()
    return result


def _resolve_href(package_member: str, href: str) -> str | None:
    url = urlsplit(href)
    if url.scheme or url.netloc:
        return None
    path = unquote(url.path, errors="strict")
    _require(bool(path) and not path.startswith("/"), f"Invalid manifest href: {href!r}")
    member = posixpath.normpath(posixpath.join(posixpath.dirname(package_member), path))
    _require(safe_member(member), f"Manifest href escapes package: {href!r}")
    return member


def _iter_reading_text(element: etree._Element, preserve_ws: bool = False) -> Iterator[tuple[str, bool]]:
    """Yield text and its whitespace mode while preserving block boundaries."""
    _require(not isinstance(element, etree._Entity), "Unresolved entity prevents reading-text comparison")
    if not isinstance(element.tag, str):
        return
    local = etree.QName(element).localname.lower()
    is_block = local in _BLOCK_TAGS
    is_pre = preserve_ws or local in _PREFORMATTED_TAGS or element.get(XML_SPACE) == "preserve"

    if is_block:
        yield "\n", False
    if element.text:
        text = element.text if is_pre else re.sub(r"[ \t\r\n]+", " ", element.text)
        yield text, is_pre
    for child in element:
        yield from _iter_reading_text(child, preserve_ws=is_pre)
        if child.tail:
            tail = child.tail if is_pre else re.sub(r"[ \t\r\n]+", " ", child.tail)
            yield tail, is_pre
    if is_block:
        yield "\n", False


def _hash_reading_text(body: etree._Element) -> str:
    parts: list[str] = []
    buf: list[str] = []

    def _flush_normal() -> None:
        if not buf:
            return
        for line in "".join(buf).split("\n"):
            stripped = line.strip(" ")
            if stripped:
                parts.append(stripped)
        buf.clear()

    for text, is_pre in _iter_reading_text(body):
        if is_pre:
            _flush_normal()
            parts.append(f"\x1f{text}\x1f")
        else:
            buf.append(text)
    _flush_normal()
    return sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _spine_and_docs(archive: ZipFile, names: set[str], *, read_text: bool) -> tuple[list, dict[str, str], list[str]]:
    container = parse_xml(read_xml_member(archive, CONTAINER))
    rootfiles = container.xpath(
        "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
        namespaces={"c": "urn:oasis:names:tc:opendocument:xmlns:container"},
    )
    _require(bool(rootfiles), "No OPF package listed in container.xml")
    spines: list = []
    text_hashes: dict[str, str] = {}
    skipped: set[str] = set()
    for pkg in rootfiles:
        _require(pkg in names and not pkg.endswith("/"), f"Missing OPF package: {pkg}")
        root = parse_xml(read_xml_member(archive, pkg)).getroot()
        manifest = root.findall(f"{{{OPF}}}manifest/{{{OPF}}}item")
        id_to_member: dict[str, str | None] = {}
        xhtml_docs: set[str] = set()
        nav_docs: set[str] = set()
        for item in manifest:
            member = _resolve_href(pkg, item.get("href", ""))
            if item_id := item.get("id"):
                id_to_member[item_id] = member
            if member and item.get("media-type") == "application/xhtml+xml":
                xhtml_docs.add(member)
                if "nav" in item.get("properties", "").split():
                    nav_docs.add(member)
        spine = root.find(f"{{{OPF}}}spine")
        _require(spine is not None, f"Missing spine in OPF package: {pkg}")
        itemrefs = spine.findall(f"{{{OPF}}}itemref")
        _require(bool(itemrefs), f"Empty spine in OPF package: {pkg}")
        seq = []
        for ref in itemrefs:
            idref = ref.get("idref", "")
            _require(bool(idref) and idref in id_to_member, f"Unresolved spine idref: {idref!r}")
            member = id_to_member[idref]
            _require(bool(member) and member in names, f"Missing spine resource: {member!r}")
            linear = ref.get("linear", "yes")
            _require(linear in {"yes", "no"}, f"Invalid spine linear flag: {linear!r}")
            seq.append((member, linear))
        direction = spine.get("page-progression-direction", "default")
        spines.append((pkg, direction, seq))
        if not read_text:
            continue
        for member, _ in seq:
            if member in text_hashes:
                continue
            if member not in xhtml_docs or member in nav_docs:
                skipped.add(member)
                continue
            body = parse_xml(read_xml_member(archive, member)).getroot().find(f"{{{XHTML}}}body")
            _require(body is not None, f"Missing XHTML body: {member}")
            text_hashes[member] = _hash_reading_text(body)
    return spines, text_hashes, sorted(skipped)


def replace_members(
    source: Path,
    output: Path,
    replacements: dict[str, bytes],
    *,
    allow_protected: bool = False,
) -> dict:
    """Surgically replace named ZIP members into a new EPUB while verifying all member SHA-256 digests."""
    _require(source.is_file(), "Source EPUB must be a regular file")
    _require(output.suffix.lower() == ".epub", "Output must have an .epub extension")
    _ensure_distinct_destination(source, output, "Output")
    _require(not os.path.lexists(output), "Output file already exists; never overwrite an existing file")
    _require(bool(replacements), "Replacements mapping must not be empty")
    source_digest = sha256_file(source)

    with TemporaryDirectory(prefix=".blackflame-", dir=output.parent) as tmp:
        staged = Path(tmp) / "candidate.epub"
        with source.open("rb") as stream, ZipFile(stream) as archive:
            names = check_zip(archive, stream)
            protected = protection_entries(names)
            _require(allow_protected or not protected, f"Protected publication: {', '.join(protected)}")
            unknown = sorted(set(replacements) - names)
            _require(not unknown, f"Replacement target not in archive: {', '.join(unknown)}")
            dir_targets = sorted(name for name in replacements if name.endswith("/") or archive.getinfo(name).is_dir())
            _require(not dir_targets, f"Cannot replace directory entries: {', '.join(dir_targets)}")
            _require("mimetype" not in replacements, "Replacing mimetype is not permitted")

            before: dict[str, str] = {}
            with ZipFile(staged, "x") as out_zip:
                out_zip.comment = archive.comment
                for info in archive.infolist():
                    name = info.filename
                    if info.is_dir():
                        out_zip.writestr(copy(info), b"")
                        continue
                    with archive.open(info) as src_member, out_zip.open(copy(info), "w") as dst_member:
                        if name in replacements:
                            before[name] = file_digest(src_member, "sha256").hexdigest()
                            dst_member.write(replacements[name])
                        else:
                            h = sha256()
                            while chunk := src_member.read(CHUNK_SIZE):
                                h.update(chunk)
                                dst_member.write(chunk)
                            before[name] = h.hexdigest()

        with staged.open("rb") as stream, ZipFile(stream) as out_zip:
            check_zip(out_zip, stream)
            after = archive_hashes(out_zip)

        replacement_hashes = {name: sha256(data).hexdigest() for name, data in replacements.items()}
        for name, expected_hash in replacement_hashes.items():
            _require(
                after[name] == expected_hash,
                f"Written member digest does not match requested bytes: {name}",
            )
        actual_changed = {name for name in before if before[name] != after[name]}
        expected_changed = {name for name, digest in replacement_hashes.items() if digest != before[name]}
        _require(actual_changed == expected_changed, "Archive member changes differ from requested replacements")

        staged.chmod(0o600)
        output_digest = sha256_file(staged)
        _require(sha256_file(source) == source_digest, "Source EPUB changed during editing")
        os.link(staged, output)

    return {
        "source_sha256": source_digest,
        "output_sha256": output_digest,
        "changed": {name: {"before": before[name], "after": after[name]} for name in sorted(actual_changed)},
        "unchanged_entries": len(before) - len(actual_changed),
    }


def compare_epubs(
    source: Path,
    candidate: Path,
    *,
    expected_changed: set[str] | None = None,
    expected_added: set[str] | None = None,
    expected_removed: set[str] | None = None,
    preserve_spine: bool = False,
    preserve_text: bool = False,
) -> dict:
    """Compare source and candidate EPUBs for file-member diffs, spine order, and spine XHTML reading-text hashes."""
    _require(source.is_file() and candidate.is_file(), "Source and candidate must be regular files")
    _require(not source.samefile(candidate), "Source and candidate must be different files")

    snapshots = []
    for path in (source, candidate):
        with path.open("rb") as stream, ZipFile(stream) as archive:
            names = check_zip(archive, stream)
            members = archive_hashes(archive)
            spines, texts, skipped = (
                _spine_and_docs(archive, names, read_text=preserve_text)
                if preserve_spine or preserve_text
                else ([], {}, [])
            )
        snapshots.append((sha256_file(path), members, spines, texts, skipped))

    (src_sha, src_mem, src_spine, src_text, src_skipped), (cand_sha, cand_mem, cand_spine, cand_text, cand_skipped) = (
        snapshots
    )
    added = sorted(cand_mem.keys() - src_mem.keys())
    removed = sorted(src_mem.keys() - cand_mem.keys())
    shared = src_mem.keys() & cand_mem.keys()
    changed = sorted(name for name in shared if src_mem[name] != cand_mem[name])

    report: dict = {
        "source_sha256": src_sha,
        "candidate_sha256": cand_sha,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_entries": len(shared) - len(changed),
    }
    if preserve_spine:
        report["spine_unchanged"] = src_spine == cand_spine
        _require(report["spine_unchanged"], "Reading order or page progression changed")
    if preserve_text:
        report["inspected_reading_docs"] = sorted(src_text.keys() | cand_text.keys())
        report["skipped_reading_docs"] = sorted(set(src_skipped) | set(cand_skipped))
        _require(
            bool(src_text) and bool(cand_text),
            "No inspectable spine XHTML reading documents found for text fidelity check",
        )
        text_changes = sorted(m for m in src_text.keys() | cand_text.keys() if src_text.get(m) != cand_text.get(m))
        report["reading_text_changes"] = text_changes
        _require(not text_changes, f"Reading text or block structure changed in: {', '.join(text_changes)}")
    if expected_added is not None:
        _require(set(added) == expected_added, f"Added members {added} differ from expected {sorted(expected_added)}")
    if expected_removed is not None:
        _require(
            set(removed) == expected_removed,
            f"Removed members {removed} differ from expected {sorted(expected_removed)}",
        )
    if expected_changed is not None:
        if expected_added is None:
            _require(not added, f"Unexpected added members: {added}")
        if expected_removed is None:
            _require(not removed, f"Unexpected removed members: {removed}")
        _require(
            set(changed) == expected_changed,
            f"Changed members {changed} differ from authorized scope {sorted(expected_changed)}",
        )
    return report


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Lightweight dimension probe for PNG, JPEG, and GIF headers (not a full image decoder)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 33 and data[12:16] == b"IHDR" and b"IEND" in data[-16:]:
        w, h = struct.unpack(">II", data[16:24])
        return (w, h) if w > 0 and h > 0 else None
    if data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 14 and data.endswith(b"\x3b"):
        w, h = struct.unpack("<HH", data[6:10])
        return (w, h) if w > 0 and h > 0 else None
    if data.startswith(b"\xff\xd8") and b"\xff\xd9" in data:
        idx = 2
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
                return None
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if idx + 7 <= len(data):
                    h, w = struct.unpack(">HH", data[idx + 3 : idx + 7])
                    return (w, h) if w > 0 and h > 0 else None
                return None
            idx += seg_len
    return None


def run_epubcheck(book: Path, report: Path, executable: str = "epubcheck") -> Diagnostics:
    """Run official EPUBCheck without overwriting inputs or existing files; publish report only when complete."""
    _require(book.is_file(), f"EPUB file does not exist: {book}")
    log_path = report.with_suffix(".log")
    _ensure_distinct_destination(book, report, "EPUBCheck report")
    _ensure_distinct_destination(book, log_path, "EPUBCheck log")
    _require(report.resolve() != log_path.resolve(), f"EPUBCheck report and log paths must be distinct: {report}")
    _require(not os.path.lexists(report), f"EPUBCheck report already exists: {report}")
    _require(not os.path.lexists(log_path), f"EPUBCheck log already exists: {log_path}")

    book_resolved = book.resolve()
    cwd = Path.cwd()
    relative_book = book_resolved.relative_to(cwd).as_posix() if book_resolved.is_relative_to(cwd) else None
    container_paths = {str(book_resolved), unquote(book_resolved.as_uri())}
    report.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".blackflame-check-", dir=report.parent) as tmp:
        fresh = Path(tmp) / "result.json"
        proc = subprocess.run(
            [executable, "--maxOfEachMessage", "unlimited", "--json", str(fresh), str(book_resolved)],
            capture_output=True,
            timeout=180,
        )
        with log_path.open("xb") as log_handle:
            log_handle.write(proc.stdout + proc.stderr)
        _require(proc.returncode in {0, 1} and fresh.is_file(), f"EPUBCheck did not complete for {book}")
        data = json.loads(fresh.read_text(encoding="utf-8"))
        checker = data["checker"]
        _require(
            Path(checker["path"]).resolve() == book_resolved and bool(checker["checkerVersion"]),
            f"Unexpected EPUBCheck identity for {book}",
        )
        severity_keys = {"FATAL": "nFatal", "ERROR": "nError", "WARNING": "nWarning"}
        groups: Counter = Counter()
        counts: Counter = Counter()
        for entry in data["messages"]:
            severity = entry["severity"].upper()
            if severity in severity_keys:
                groups[severity] += 1
                _require(entry.get("additionalLocations", 0) == 0, f"Truncated EPUBCheck report: {report}")
                for loc in entry.get("locations") or [{}]:
                    path = loc.get("path")
                    if path is not None:
                        decoded = unquote(path)
                        if decoded in container_paths or (
                            decoded.startswith("./") and posixpath.normpath(decoded) == relative_book
                        ):
                            path = "<container>"
                    counts[(severity, entry["ID"], entry["message"], path, loc.get("context"))] += 1
        _require(
            all(groups[s] == checker[k] for s, k in severity_keys.items()),
            f"Incomplete EPUBCheck report: {report}",
        )
        failed = bool(groups["FATAL"] or groups["ERROR"])
        _require(proc.returncode == int(failed), "Unexpected EPUBCheck exit status")
        os.link(fresh, report)
    return Diagnostics(checker["checkerVersion"], failed, counts)


def assert_no_new_diagnostics(before: Diagnostics, after: Diagnostics) -> None:
    """Reject any new EPUBCheck errors, warnings, or additional occurrences of existing diagnostics."""
    _require(before.version == after.version, "EPUBCheck version changed between runs")
    added = after.occurrences - before.occurrences
    _require(not added, f"New EPUBCheck diagnostics introduced: {len(added)} item(s)")
