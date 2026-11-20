#!/usr/bin/env python3
"""Inspect, verify, or apply a reviewed replacement plan to an EPUB."""

import argparse
from collections import Counter
from copy import copy
from hashlib import file_digest, sha256
from io import BytesIO
import json
import os
from pathlib import Path
import posixpath
import shutil
import stat
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import NamedTuple
from urllib.parse import unquote, urlsplit
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

from lxml import etree

CONTAINER = "META-INF/container.xml"
MEDIA_TYPE = b"application/epub+zip"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
XHTML = "http://www.w3.org/1999/xhtml"
PROTECTION = {"META-INF/encryption.xml", "META-INF/rights.xml", "META-INF/signatures.xml"}
EDITABLE_METADATA = {
    f"{{{DC}}}{field}"
    for field in ("title", "creator", "language", "publisher", "description", "subject", "contributor")
}
LIMIT_MEMBER = 256 * 1024**2
LIMIT_TOTAL = 2 * 1024**3
LIMIT_XML = 16 * 1024**2
CHUNK_SIZE = 1024**2


class Diagnostics(NamedTuple):
    version: str
    has_errors: bool
    occurrences: Counter


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha_file(path):
    with path.open("rb") as source:
        return file_digest(source, "sha256").hexdigest()


def parse_xml(data):
    parser = etree.XMLParser(
        no_network=True, load_dtd=False, resolve_entities=False,
        strip_cdata=False, recover=False, huge_tree=False,
    )
    return etree.parse(BytesIO(data), parser)


def safe_member(name):
    parts = name.removesuffix("/").split("/")
    return (
        all(part and part not in {".", ".."} for part in parts)
        and not any(char in name for char in ("\\", "\0", ":"))
    )


def xml_member(archive, name):
    require(archive.getinfo(name).file_size <= LIMIT_XML, f"XML exceeds size limit: {name}")
    return archive.read(name)


def check_zip(archive, stream):
    infos = archive.infolist()
    require(0 < len(infos) <= 50_000, "ZIP entry count outside supported limits")
    require(infos[0].filename == "mimetype", "mimetype must be the first ZIP entry")
    mime = infos[0]
    require(mime.header_offset == 0 and mime.compress_type == ZIP_STORED
            and not mime.extra and mime.file_size == len(MEDIA_TYPE), "Invalid mimetype ZIP entry")
    stream.seek(0)
    header = stream.read(30)
    require(len(header) == 30 and header[:4] == b"PK\x03\x04", "Invalid mimetype local ZIP header")
    flags, method = struct.unpack_from("<HH", header, 6)
    extra_size = struct.unpack_from("<H", header, 28)[0]
    require(not (flags & 1) and method == ZIP_STORED and extra_size == 0,
            "Invalid mimetype local ZIP flags, compression or extra field")
    names = set()
    total_size = 0
    for info in infos:
        name = info.filename
        require(info.orig_filename == name and safe_member(name), f"Unsafe ZIP path: {name!r}")
        require(name not in names, f"Duplicate ZIP entry: {name}")
        require(not (info.flag_bits & 1), f"Encrypted ZIP entry: {name}")
        require(not stat.S_ISLNK(info.external_attr >> 16), f"ZIP symlink: {name}")
        require(info.compress_type in {ZIP_STORED, ZIP_DEFLATED}, f"Unsupported ZIP compression: {name}")
        require(info.file_size <= LIMIT_MEMBER, f"ZIP entry exceeds size limit: {name}")
        total_size += info.file_size
        require(total_size <= LIMIT_TOTAL, "ZIP expanded size exceeds limit")
        names.add(name)
    require(archive.read(mime) == MEDIA_TYPE, "Unexpected mimetype content")
    return names


def local_href(package, href):
    url = urlsplit(href)
    if url.scheme or url.netloc:
        return None
    path = unquote(url.path, errors="strict")
    require(path and not path.startswith("/"), f"Invalid manifest href: {href!r}")
    member = posixpath.normpath(posixpath.join(posixpath.dirname(package), path))
    require(safe_member(member), f"Manifest href escapes package: {href!r}")
    return member


def inventory(archive, stream):
    names = check_zip(archive, stream)
    container = parse_xml(xml_member(archive, CONTAINER))
    namespace = "urn:oasis:names:tc:opendocument:xmlns:container"
    rootfiles = container.xpath(
        "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
        namespaces={"c": namespace},
    )
    require(rootfiles, "No OPF package listed in container.xml")
    packages = []
    for package in rootfiles:
        require(package in names and not package.endswith("/"), f"Missing OPF package: {package}")
        root = parse_xml(xml_member(archive, package)).getroot()
        require(root.tag == f"{{{OPF}}}package", f"Invalid OPF root: {package}")
        manifest = root.findall(f"{{{OPF}}}manifest/{{{OPF}}}item")
        items = [
            {
                "id": item.get("id"), "href": item.get("href"),
                "member": local_href(package, item.get("href", "")),
                "media_type": item.get("media-type"),
                "properties": item.get("properties", "").split(),
            }
            for item in manifest
        ]
        members = {item["id"]: item["member"] for item in items if item["id"] is not None}
        namespaces = {"opf": OPF, "dc": DC}
        metadata = {
            field: root.xpath(f"opf:metadata/dc:{field}/text()", namespaces=namespaces)
            for field in ("title", "creator", "contributor", "language", "publisher", "date", "identifier")
        }
        primary_id = root.get("unique-identifier")
        primary_identifier = root.xpath(
            "opf:metadata/dc:identifier[@id=$primary_id]/text()",
            namespaces=namespaces, primary_id=primary_id or "",
        )
        legacy_covers = set(root.xpath("opf:metadata/opf:meta[@name='cover']/@content", namespaces=namespaces))
        spine = root.find(f"{{{OPF}}}spine")
        itemrefs = [] if spine is None else spine.findall(f"{{{OPF}}}itemref")
        spine_items = [
            {
                "idref": ref.get("idref"), "member": members.get(ref.get("idref")),
                "linear": ref.get("linear", "yes"),
            }
            for ref in itemrefs
        ]
        ncx_ids = root.xpath("opf:spine/@toc", namespaces=namespaces)
        packages.append({
            "member": package, "version": root.get("version"),
            "titles": metadata["title"], "metadata": metadata,
            "primary_identifier": primary_identifier[0] if len(primary_identifier) == 1 else None,
            "manifest": items,
            "spine": [item["idref"] for item in spine_items if item["idref"] is not None],
            "spine_items": spine_items,
            "page_progression_direction": spine.get("page-progression-direction", "default") if spine is not None else None,
            "ncx_id": ncx_ids, "ncx_member": members.get(ncx_ids[0]) if ncx_ids else None,
            "nav_members": [item["member"] for item in items if item["member"] and "nav" in item["properties"]],
            "cover_members": [
                item["member"] for item in items
                if item["member"] and ("cover-image" in item["properties"] or item["id"] in legacy_covers)
            ],
        })
    return {"entry_count": len(names), "protection": sorted(PROTECTION & names), "packages": packages}


def compare_xml(old, new, member, scope_error):
    require(
        etree.tostring(old, method="c14n", with_comments=True)
        == etree.tostring(new, method="c14n", with_comments=True),
        f"{scope_error}: {member}",
    )
    # Canonical XML omits the document type declaration and its internal subset.
    if old.docinfo.doctype:
        for tree in (old, new):
            tree.getroot().clear()
        require(etree.tostring(old) == etree.tostring(new), f"Document type declaration changed: {member}")


def check_edit(member, before, after, is_package):
    old, new = parse_xml(before), parse_xml(after)
    for field in ("doctype", "encoding", "standalone", "xml_version"):
        require(getattr(old.docinfo, field) == getattr(new.docinfo, field),
                f"XML declaration or doctype changed: {member}")
    if is_package:
        modified = "meta[@property='dcterms:modified' and not(@refines)]"
        for tree in (old, new):
            for node in tree.xpath("/*/opf:metadata/*", namespaces={"opf": OPF}):
                if node.tag in EDITABLE_METADATA and len(node) == 0:
                    node.text = None
            for node in tree.xpath(f"/*/opf:metadata/opf:{modified}", namespaces={"opf": OPF}):
                node.text = None
        compare_xml(old, new, member, "OPF changes exceed metadata text edits")
        return

    old_root, new_root = old.getroot(), new.getroot()
    require(old_root.tag == new_root.tag == f"{{{XHTML}}}html", f"Invalid XHTML root: {member}")
    bodies = [tree.getroot().findall(f"{{{XHTML}}}body") for tree in (old, new)]
    require(all(len(matches) == 1 for matches in bodies), f"Expected one XHTML body: {member}")
    anchor_xpath = "//@id | //@xml:id | //x:a/@name"
    old_anchors, new_anchors = (
        Counter(tree.xpath(anchor_xpath, namespaces={"x": XHTML})) for tree in (old, new)
    )
    require(not (old_anchors - new_anchors), f"Existing anchor removed: {member}")
    for (body,) in bodies:
        body.text = None
        for child in list(body):
            body.remove(child)
    compare_xml(old, new, member, "XHTML changes outside body content")


def unique_fields(pairs):
    fields = dict(pairs)
    require(len(fields) == len(pairs), "Duplicate key in replacement plan")
    return fields


def read_replacements(archive, book, plan_path, digest):
    plan = json.loads(plan_path.read_text(encoding="utf-8"), object_pairs_hook=unique_fields)
    require(isinstance(plan, dict) and plan.get("source_sha256") == digest, "Plan source SHA-256 differs")
    proposed = plan.get("replacements")
    require(isinstance(proposed, dict) and proposed, "Plan must contain replacements")
    require(len(book["packages"]) == 1, "Editing requires a single OPF package")
    require(not book["protection"], f"Protected publication: {', '.join(book['protection'])}")
    package = book["packages"][0]
    require(package["version"] in {"2.0", "3.0"}, "Editing supports EPUB 2.0 and 3.0 packages")
    documents = {
        item["member"] for item in package["manifest"]
        if item["member"] is not None and item["media_type"] == "application/xhtml+xml"
    }
    documents -= {item["member"] for item in package["manifest"] if "nav" in item["properties"]}
    allowed = documents | {package["member"]}
    replacements = {}
    for member, file in proposed.items():
        require(member in allowed and isinstance(file, str), f"Unsupported replacement: {member}")
        old = xml_member(archive, member)
        with (plan_path.parent / file).open("rb") as handle:
            new = handle.read(LIMIT_XML + 1)
        require(len(new) <= LIMIT_XML, f"Replacement exceeds XML size limit: {member}")
        require(new != old, f"Replacement has no byte changes: {member}")
        check_edit(member, old, new, member == package["member"])
        replacements[member] = new
    return replacements


def archive_hashes(archive):
    result = {}
    for info in archive.infolist():
        with archive.open(info) as stream:
            result[info.filename] = file_digest(stream, "sha256").hexdigest()
    return result


def repack(archive, candidate, replacements):
    before = {}
    with ZipFile(candidate, "x") as output:
        output.comment = archive.comment
        for info in archive.infolist():
            name = info.filename
            with archive.open(info) as source, output.open(copy(info), "w") as target:
                if name in replacements:
                    before[name] = file_digest(source, "sha256").hexdigest()
                    target.write(replacements[name])
                else:
                    digest = sha256()
                    while chunk := source.read(CHUNK_SIZE):
                        digest.update(chunk)
                        target.write(chunk)
                    before[name] = digest.hexdigest()
    with candidate.open("rb") as stream, ZipFile(stream) as output:
        check_zip(output, stream)
        require(
            [(i.filename, i.compress_type) for i in output.infolist()]
            == [(i.filename, i.compress_type) for i in archive.infolist()],
            "ZIP entry order, names or compression methods changed",
        )
        after = archive_hashes(output)
    require({name for name in before if before[name] != after[name]} == replacements.keys(),
            "Archive changes differ from approved plan")
    require(all(after[name] == sha256(data).hexdigest() for name, data in replacements.items()),
            "Output differs from approved replacement")
    return before, after


def run_epubcheck(command, book, report):
    book = book.resolve()
    cwd = Path.cwd()
    relative_book = book.relative_to(cwd).as_posix() if book.is_relative_to(cwd) else None
    container_paths = {str(book), unquote(book.as_uri())}
    run = subprocess.run(
        [command, "--maxOfEachMessage", "unlimited", "--json", str(report), str(book)],
        capture_output=True, timeout=180,
    )
    report.with_suffix(".log").write_bytes(run.stdout + run.stderr)
    require(run.returncode in {0, 1} and report.is_file(), f"EPUBCheck did not complete, see {report.with_suffix('.log')}")
    data = json.loads(report.read_text(encoding="utf-8"))
    checker = data["checker"]
    diagnostic_keys = {"FATAL": "nFatal", "ERROR": "nError", "WARNING": "nWarning"}
    groups = Counter()
    counts = Counter()
    for entry in data["messages"]:
        severity = entry["severity"].upper()
        if severity in diagnostic_keys:
            groups[severity] += 1
            require(entry.get("additionalLocations", 0) == 0, f"Truncated EPUBCheck report: {report}")
            locations = entry.get("locations") or []
            for loc in locations or [{}]:
                path = loc.get("path")
                if path is not None:
                    decoded = unquote(path)
                    if decoded in container_paths or (
                        decoded.startswith("./") and posixpath.normpath(decoded) == relative_book
                    ):
                        path = "<container>"
                counts[(severity, entry["ID"], entry["message"], path, loc.get("context"))] += 1
    require(
        all(groups[severity] == checker[key] for severity, key in diagnostic_keys.items()),
        f"Incomplete EPUBCheck report: {report}",
    )
    failed = bool(groups["FATAL"] or groups["ERROR"])
    require(run.returncode == int(failed), "Unexpected EPUBCheck exit status, see diagnostic log")
    return Diagnostics(checker["checkerVersion"], failed, counts)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_candidate(before, after, reports):
    require(before.version == after.version, "EPUBCheck version changed between runs")
    require(not (after.occurrences - before.occurrences), f"New EPUBCheck errors or warnings, see {reports}")


def file_state(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def spine_signature(book, archive):
    result = []
    archive_members = set(archive.namelist())
    for package in book["packages"]:
        sequence = [(item["member"], item["linear"]) for item in package["spine_items"]]
        require(
            sequence and all(member in archive_members and linear in {"yes", "no"} for member, linear in sequence),
            f"Cannot resolve reading order for {package['member']}",
        )
        result.append((package["member"], package["page_progression_direction"], sequence))
    return result


def verify(args):
    require(args.source.is_file() and args.candidate.is_file(), "Source and candidate must be regular files")
    require(not args.source.samefile(args.candidate), "Source and candidate must be different files")
    reports = args.report_dir.absolute()
    reports.mkdir(parents=True)
    inspections = []
    spines = []
    for path in (args.source, args.candidate):
        with path.open("rb") as stream:
            state = file_state(os.fstat(stream.fileno()))
            with ZipFile(stream) as archive:
                if args.preserve_spine:
                    spines.append(spine_signature(inventory(archive, stream), archive))
                else:
                    check_zip(archive, stream)
                members = archive_hashes(archive)
            stream.seek(0)
            digest = file_digest(stream, "sha256").hexdigest()
            inspections.append((state, digest, members))
    (source_state, source_hash, source_members), (candidate_state, candidate_hash, candidate_members) = inspections
    added = candidate_members.keys() - source_members.keys()
    removed = source_members.keys() - candidate_members.keys()
    shared = source_members.keys() & candidate_members.keys()
    changed = sorted(name for name in shared if source_members[name] != candidate_members[name])
    before = run_epubcheck(args.epubcheck, args.source, reports / "epubcheck-before.json")
    after = run_epubcheck(args.epubcheck, args.candidate, reports / "epubcheck-after.json")
    require(file_state(args.source.stat()) == source_state and file_state(args.candidate.stat()) == candidate_state,
            "Source or candidate changed during verification")
    comparison = {
        "source_sha256": source_hash,
        "candidate_sha256": candidate_hash,
        "added": sorted(added),
        "removed": sorted(removed),
        "changed": changed,
        "unchanged_entries": len(shared) - len(changed),
        "epubcheck_version": after.version,
        "baseline_has_errors": before.has_errors,
        "candidate_has_errors": after.has_errors,
    }
    if args.preserve_spine:
        comparison["spine_unchanged"] = spines[0] == spines[1]
    write_json(reports / "comparison.json", comparison)
    require(comparison.get("spine_unchanged", True), f"Reading order or page progression changed, see {reports}")
    validate_candidate(before, after, reports)
    require(not after.has_errors or args.allow_existing_errors, f"Existing EPUBCheck errors remain, see {reports}")
    print(reports / "comparison.json")


def apply(args):
    require(args.output.suffix.lower() == ".epub", "Output must have an .epub extension")
    require(not os.path.lexists(args.output), "Output already exists")
    require(args.source.is_file(), "Source must be a regular file")
    require(args.source.stat().st_size <= LIMIT_TOTAL, "Source archive exceeds size limit")
    reports = args.report_dir.absolute()
    with TemporaryDirectory(prefix=".epublib-", dir=args.output.parent) as directory:
        scratch = Path(directory).resolve()
        source = scratch / "source.epub"
        candidate = scratch / "candidate" / source.name
        candidate.parent.mkdir()
        shutil.copyfile(args.source, source)
        digest = sha_file(source)
        with source.open("rb") as stream, ZipFile(stream) as archive:
            book = inventory(archive, stream)
            replacements = read_replacements(archive, book, args.plan, digest)
            reports.mkdir(parents=True)
            baseline = run_epubcheck(args.epubcheck, source, reports / "epubcheck-before.json")
            require(not baseline.has_errors or args.allow_existing_errors, f"Existing EPUBCheck errors, see {reports}")
            before, after = repack(archive, candidate, replacements)
        verified = run_epubcheck(args.epubcheck, candidate, reports / "epubcheck-after.json")
        validate_candidate(baseline, verified, reports)
        require(sha_file(args.source) == digest, "Source changed during editing")
        write_json(reports / "changes.json", {
            "source_sha256": digest,
            "output_sha256": sha_file(candidate),
            "changes": {name: {"before": before[name], "after": after[name]} for name in sorted(replacements)},
            "unchanged_entries": len(before) - len(replacements),
            "epubcheck_version": verified.version,
            "baseline_has_errors": baseline.has_errors,
            "output_has_errors": verified.has_errors,
        })
        candidate.chmod(0o600)
        # The staging file and destination share a filesystem. Linking is atomic
        # and fails if another process has already created the destination.
        os.link(candidate, args.output)
    print(args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Print package inventory and source SHA-256")
    inspect.add_argument("source", type=Path)
    patch = commands.add_parser("apply", help="Validate and apply a reviewed replacement plan")
    patch.add_argument("source", type=Path)
    patch.add_argument("output", type=Path)
    patch.add_argument("--plan", required=True, type=Path)
    compare = commands.add_parser("verify", help="Compare and validate an independently edited EPUB")
    compare.add_argument("source", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--preserve-spine", action="store_true", help="Require unchanged reading order and page progression")
    for command in (patch, compare):
        command.add_argument("--report-dir", required=True, type=Path)
        command.add_argument("--epubcheck", default="epubcheck", help="Path to the EPUBCheck executable")
        command.add_argument("--allow-existing-errors", action="store_true", help="Allow an explicitly accepted baseline")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            with args.source.open("rb") as stream:
                before = os.fstat(stream.fileno())
                with ZipFile(stream) as archive:
                    data = inventory(archive, stream)
                stream.seek(0)
                data["source_sha256"] = file_digest(stream, "sha256").hexdigest()
                after = os.fstat(stream.fileno())
                require(
                    file_state(before) == file_state(after),
                    "Source changed during inspection",
                )
            print(json.dumps(data, ensure_ascii=False, indent=2))
        elif args.command == "apply":
            apply(args)
        else:
            verify(args)
    except (ValueError, KeyError, OSError, BadZipFile, etree.LxmlError, subprocess.SubprocessError) as error:
        parser.exit(1, f"epublib: {error}\n")


if __name__ == "__main__":
    main()
