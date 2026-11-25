#!/usr/bin/env python3
"""Inspect, verify, or apply a reviewed replacement plan to an EPUB."""

import argparse
import json
import os
import shutil
import subprocess
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from lxml import etree

from audit import audit_epub
from edit_plan import read_replacements, unique_fields
from publication import (
    LIMIT_TOTAL,
    archive_hashes,
    check_zip,
    inventory,
    reading_text_hashes,
    repack,
    require,
    sha_file,
    spine_signature,
)
from validation import run_epubcheck, validate_candidate


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_state(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def verify(args):
    require(args.source.is_file() and args.candidate.is_file(), "Source and candidate must be regular files")
    require(not args.source.samefile(args.candidate), "Source and candidate must be different files")
    reports = args.report_dir.absolute()
    reports.mkdir(parents=True)
    inspections = []
    spines = []
    reading_text = []
    for path in (args.source, args.candidate):
        with path.open("rb") as stream:
            state = file_state(os.fstat(stream.fileno()))
            with ZipFile(stream) as archive:
                if args.preserve_spine or args.preserve_text:
                    book = inventory(archive, stream)
                    if args.preserve_spine:
                        spines.append(spine_signature(book, archive))
                    if args.preserve_text:
                        reading_text.append(reading_text_hashes(book, archive))
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
    require(
        file_state(args.source.stat()) == source_state and file_state(args.candidate.stat()) == candidate_state,
        "Source or candidate changed during verification",
    )
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
    if args.preserve_text:
        old, new = reading_text
        comparison["reading_text_changes"] = sorted(
            member for member in old.keys() | new.keys() if old.get(member) != new.get(member)
        )
    write_json(reports / "comparison.json", comparison)
    require(not comparison.get("reading_text_changes"), f"Reading text changed, see {reports}")
    require(comparison.get("spine_unchanged", True), f"Reading order or page progression changed, see {reports}")
    if args.expected_changes:
        expected = json.loads(args.expected_changes.read_text(encoding="utf-8"), object_pairs_hook=unique_fields)
        require(
            isinstance(expected, dict)
            and expected.keys() == {"source_sha256", "added", "removed", "changed"}
            and expected["source_sha256"] == source_hash,
            "Expected changes must identify the source and all three lists",
        )
        for key in ("added", "removed", "changed"):
            names = expected[key]
            require(
                isinstance(names, list)
                and all(isinstance(name, str) for name in names)
                and sorted(names) == comparison[key],
                f"Unexpected {key} members, see {reports}",
            )
    validate_candidate(before, after, reports)
    require(not after.has_errors or args.allow_existing_errors, f"Existing EPUBCheck errors remain, see {reports}")
    print(reports / "comparison.json")


def apply(args):
    require(args.output.suffix.lower() == ".epub", "Output must have an .epub extension")
    require(not os.path.lexists(args.output), "Output already exists")
    require(args.source.is_file(), "Source must be a regular file")
    require(args.source.stat().st_size <= LIMIT_TOTAL, "Source archive exceeds size limit")
    reports = args.report_dir.absolute()
    with TemporaryDirectory(prefix=".blackflame-", dir=args.output.parent) as directory:
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
        write_json(
            reports / "changes.json",
            {
                "source_sha256": digest,
                "output_sha256": sha_file(candidate),
                "review_modified_timestamp": book["packages"][0]["version"] == "3.0",
                "changes": {name: {"before": before[name], "after": after[name]} for name in sorted(replacements)},
                "unchanged_entries": len(before) - len(replacements),
                "epubcheck_version": verified.version,
                "baseline_has_errors": baseline.has_errors,
                "output_has_errors": verified.has_errors,
            },
        )
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
    audit_cmd = commands.add_parser(
        "audit", help="Audit manifest, spine, navigation, links, footnotes, covers, and assets"
    )
    audit_cmd.add_argument("source", type=Path)
    patch = commands.add_parser("apply", help="Validate and apply a reviewed replacement plan")
    patch.add_argument("source", type=Path)
    patch.add_argument("output", type=Path)
    patch.add_argument("--plan", required=True, type=Path)
    compare = commands.add_parser("verify", help="Compare and validate an independently edited EPUB")
    compare.add_argument("source", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--expected-changes", type=Path, help="Require exact added, removed and changed member lists")
    compare.add_argument("--preserve-text", action="store_true", help="Require unchanged XHTML reading text")
    compare.add_argument(
        "--preserve-spine", action="store_true", help="Require unchanged reading order and page progression"
    )
    for command in (patch, compare):
        command.add_argument("--report-dir", required=True, type=Path)
        command.add_argument("--epubcheck", default="epubcheck", help="Path to the EPUBCheck executable")
        command.add_argument(
            "--allow-existing-errors", action="store_true", help="Allow an explicitly accepted baseline"
        )
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
        elif args.command == "audit":
            print(json.dumps(audit_epub(args.source), ensure_ascii=False, indent=2))
        elif args.command == "apply":
            apply(args)
        else:
            verify(args)
    except (ValueError, KeyError, OSError, BadZipFile, etree.LxmlError, subprocess.SubprocessError) as error:
        parser.exit(1, f"blackflame: {error}\n")


if __name__ == "__main__":
    main()
