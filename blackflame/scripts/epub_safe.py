"""Deterministic safety, surgical ZIP replacement, fidelity checks, and EPUBCheck diff helpers."""

import json
import os
import posixpath
import re
import stat
import struct
import subprocess
from collections import Counter
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
PROTECTION = frozenset({"META-INF/encryption.xml", "META-INF/rights.xml", "META-INF/signatures.xml"})
APPLE_MAX_IMAGE_PIXELS = 5_600_000
LIMIT_MEMBER = 256 * 1024**2
LIMIT_TOTAL = 2 * 1024**3
LIMIT_XML = 16 * 1024**2
CHUNK_SIZE = 1024**2


class Diagnostics(NamedTuple):
    version: str
    has_errors: bool
    occurrences: Counter


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def parse_xml(data: bytes) -> etree._ElementTree:
    """Strictly parse XML/XHTML with external entities and network DTD loading disabled."""
    parser = etree.XMLParser(
        no_network=True,
        load_dtd=False,
        resolve_entities=False,
        strip_cdata=False,
        recover=False,
        huge_tree=False,
    )
    return etree.parse(BytesIO(data), parser)


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
    _require(archive.read(mime) == MEDIA_TYPE, "Unexpected mimetype content")
    return names


def protection_entries(names: set[str]) -> list[str]:
    return sorted(PROTECTION & names)


def archive_hashes(archive: ZipFile) -> dict[str, str]:
    result: dict[str, str] = {}
    for info in archive.infolist():
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


def _spine_and_docs(archive: ZipFile, names: set[str]) -> tuple[list, dict[str, str]]:
    container = parse_xml(archive.read(CONTAINER))
    rootfiles = container.xpath(
        "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
        namespaces={"c": "urn:oasis:names:tc:opendocument:xmlns:container"},
    )
    _require(bool(rootfiles), "No OPF package listed in container.xml")
    spines: list = []
    text_hashes: dict[str, str] = {}
    for pkg in rootfiles:
        _require(pkg in names and not pkg.endswith("/"), f"Missing OPF package: {pkg}")
        root = parse_xml(archive.read(pkg)).getroot()
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
        itemrefs = [] if spine is None else spine.findall(f"{{{OPF}}}itemref")
        seq = [(id_to_member.get(ref.get("idref", "")), ref.get("linear", "yes")) for ref in itemrefs]
        direction = spine.get("page-progression-direction", "default") if spine is not None else None
        spines.append((pkg, direction, seq))
        for member, _ in seq:
            if not member or member not in xhtml_docs or member in nav_docs or member in text_hashes:
                continue
            body = parse_xml(archive.read(member)).getroot().find(f"{{{XHTML}}}body")
            _require(body is not None, f"Missing XHTML body: {member}")
            normalized = re.sub(r"[ \t\r\n]+", " ", "".join(body.itertext())).strip(" ")
            text_hashes[member] = sha256(normalized.encode("utf-8")).hexdigest()
    return spines, text_hashes


def replace_members(
    source: Path,
    output: Path,
    replacements: dict[str, bytes],
    *,
    allow_protected: bool = False,
) -> dict:
    """Surgically replace specified ZIP members into a new EPUB while verifying all other members stay identical."""
    _require(source.is_file(), "Source EPUB must be a regular file")
    _require(output.suffix.lower() == ".epub", "Output must have an .epub extension")
    _require(not os.path.lexists(output), "Output file already exists; never overwrite the source")
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
            _require("mimetype" not in replacements, "Replacing mimetype is not permitted")

            before: dict[str, str] = {}
            with ZipFile(staged, "x") as out_zip:
                out_zip.comment = archive.comment
                for info in archive.infolist():
                    name = info.filename
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

        actual_changed = {name for name in before if before[name] != after[name]}
        expected_changed = {name for name, data in replacements.items() if sha256(data).hexdigest() != before[name]}
        _require(actual_changed == expected_changed, "Archive member changes differ from requested replacements")
        _require(sha256_file(source) == source_digest, "Source EPUB changed during editing")

        staged.chmod(0o600)
        os.link(staged, output)

    return {
        "source_sha256": source_digest,
        "output_sha256": sha256_file(output),
        "changed": {name: {"before": before[name], "after": after[name]} for name in sorted(actual_changed)},
        "unchanged_entries": len(before) - len(actual_changed),
    }


def compare_epubs(
    source: Path,
    candidate: Path,
    *,
    expected_changed: set[str] | None = None,
    preserve_spine: bool = False,
    preserve_text: bool = False,
) -> dict:
    """Compare source and edited EPUBs for ZIP member diffs, spine order, and reading text fidelity."""
    _require(source.is_file() and candidate.is_file(), "Source and candidate must be regular files")
    _require(not source.samefile(candidate), "Source and candidate must be different files")

    snapshots = []
    for path in (source, candidate):
        with path.open("rb") as stream, ZipFile(stream) as archive:
            names = check_zip(archive, stream)
            members = archive_hashes(archive)
            spines, texts = _spine_and_docs(archive, names) if (preserve_spine or preserve_text) else ([], {})
        snapshots.append((sha256_file(path), members, spines, texts))

    (src_sha, src_mem, src_spine, src_text), (cand_sha, cand_mem, cand_spine, cand_text) = snapshots
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
        text_changes = sorted(m for m in src_text.keys() | cand_text.keys() if src_text.get(m) != cand_text.get(m))
        report["reading_text_changes"] = text_changes
        _require(not text_changes, f"Reading text changed in: {', '.join(text_changes)}")
    if expected_changed is not None:
        _require(
            not added and not removed and set(changed) == expected_changed,
            f"Modified members {changed} (added={added}, removed={removed}) differ from authorized scope {sorted(expected_changed)}",
        )
    return report


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Return (width, height) for PNG, JPEG, or GIF bytes; None if unknown or invalid."""
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
    """Run official EPUBCheck and return complete diagnostic occurrence counts."""
    book = book.resolve()
    cwd = Path.cwd()
    relative_book = book.relative_to(cwd).as_posix() if book.is_relative_to(cwd) else None
    container_paths = {str(book), unquote(book.as_uri())}
    report.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=report.parent) as tmp:
        fresh = Path(tmp) / "result.json"
        proc = subprocess.run(
            [executable, "--maxOfEachMessage", "unlimited", "--json", str(fresh), str(book)],
            capture_output=True,
            timeout=180,
        )
        report.with_suffix(".log").write_bytes(proc.stdout + proc.stderr)
        _require(proc.returncode in {0, 1} and fresh.is_file(), f"EPUBCheck did not complete for {book}")
        data = json.loads(fresh.read_text(encoding="utf-8"))
        checker = data["checker"]
        _require(
            Path(checker["path"]).resolve() == book and bool(checker["checkerVersion"]),
            f"Unexpected EPUBCheck identity for {book}",
        )
        fresh.replace(report)

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
    _require(all(groups[s] == checker[k] for s, k in severity_keys.items()), f"Incomplete EPUBCheck report: {report}")
    failed = bool(groups["FATAL"] or groups["ERROR"])
    _require(proc.returncode == int(failed), "Unexpected EPUBCheck exit status")
    return Diagnostics(checker["checkerVersion"], failed, counts)


def assert_no_new_diagnostics(before: Diagnostics, after: Diagnostics) -> None:
    """Reject any new EPUBCheck errors, warnings, or additional occurrences of existing diagnostics."""
    _require(before.version == after.version, "EPUBCheck version changed between runs")
    added = after.occurrences - before.occurrences
    _require(not added, f"New EPUBCheck diagnostics introduced: {len(added)} item(s)")
