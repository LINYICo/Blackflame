#!/usr/bin/env python3
"""Inspect an EPUB or apply a reviewed OPF/XHTML replacement plan."""

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
        packages.append({
            "member": package, "version": root.get("version"),
            "titles": root.xpath("opf:metadata/dc:title/text()", namespaces={"opf": OPF, "dc": DC}),
            "manifest": items,
            "spine": root.xpath("opf:spine/opf:itemref/@idref", namespaces={"opf": OPF}),
            "ncx_id": root.xpath("opf:spine/@toc", namespaces={"opf": OPF}),
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
    with ZipFile(candidate, "x") as output:
        output.comment = archive.comment
        for info in archive.infolist():
            with output.open(copy(info), "w") as target:
                if info.filename in replacements:
                    target.write(replacements[info.filename])
                else:
                    with archive.open(info) as source:
                        shutil.copyfileobj(source, target, length=CHUNK_SIZE)
    with candidate.open("rb") as stream, ZipFile(stream) as output:
        check_zip(output, stream)
        require(
            [(i.filename, i.compress_type) for i in output.infolist()]
            == [(i.filename, i.compress_type) for i in archive.infolist()],
            "ZIP entry order, names or compression methods changed",
        )
        after = archive_hashes(output)
    before = archive_hashes(archive)
    require({name for name in before if before[name] != after[name]} == replacements.keys(),
            "Archive changes differ from approved plan")
    require(all(after[name] == sha256(data).hexdigest() for name, data in replacements.items()),
            "Output differs from approved replacement")
    return before, after


def run_epubcheck(command, book, report):
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
            counts.update(
                (severity, entry["ID"], entry["message"], loc.get("path"), loc.get("context"))
                for loc in locations or [{}]
            )
    require(
        all(groups[severity] == checker[key] for severity, key in diagnostic_keys.items()),
        f"Incomplete EPUBCheck report: {report}",
    )
    failed = bool(groups["FATAL"] or groups["ERROR"])
    require(run.returncode == int(failed), "Unexpected EPUBCheck exit status, see diagnostic log")
    return checker["checkerVersion"], failed, counts


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
            version, failed, baseline = run_epubcheck(args.epubcheck, source, reports / "epubcheck-before.json")
            require(not failed or args.allow_existing_errors, f"Existing EPUBCheck errors, see {reports}")
            before, after = repack(archive, candidate, replacements)
        new_version, candidate_failed, diagnostics = run_epubcheck(
            args.epubcheck, candidate, reports / "epubcheck-after.json",
        )
        require(version == new_version, "EPUBCheck version changed between runs")
        require(not (diagnostics - baseline), f"New EPUBCheck errors or warnings, see {reports}")
        require(sha_file(args.source) == digest, "Source changed during editing")
        write_json(reports / "changes.json", {
            "source_sha256": digest,
            "output_sha256": sha_file(candidate),
            "changes": {name: {"before": before[name], "after": after[name]} for name in sorted(replacements)},
            "unchanged_entries": len(before) - len(replacements),
            "epubcheck_version": version,
            "baseline_has_errors": failed,
            "output_has_errors": candidate_failed,
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
    patch.add_argument("--report-dir", required=True, type=Path)
    patch.add_argument("--epubcheck", default="epubcheck", help="Path to the EPUBCheck executable")
    patch.add_argument("--allow-existing-errors", action="store_true", help="Allow an explicitly accepted baseline")
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
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                    "Source changed during inspection",
                )
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            apply(args)
    except (ValueError, KeyError, OSError, BadZipFile, etree.LxmlError, subprocess.SubprocessError) as error:
        parser.exit(1, f"epublib: {error}\n")


if __name__ == "__main__":
    main()
