"""Run EPUBCheck and compare complete diagnostic occurrences."""

import json
import os
import posixpath
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple
from urllib.parse import unquote

from publication import require


class Diagnostics(NamedTuple):
    version: str
    has_errors: bool
    occurrences: Counter


def run_epubcheck(command, book, report):
    book = book.resolve()
    cwd = Path.cwd()
    relative_book = book.relative_to(cwd).as_posix() if book.is_relative_to(cwd) else None
    container_paths = {str(book), unquote(book.as_uri())}
    with TemporaryDirectory(dir=report.parent) as directory:
        fresh = Path(directory) / "result.json"
        executable = [command]
        if command == "epubcheck" and os.environ.get("BLACKFLAME_CHECKER_JAR"):
            executable = [os.environ["BLACKFLAME_JAVA"], "-jar", os.environ["BLACKFLAME_CHECKER_JAR"]]
        run = subprocess.run(
            [*executable, "--maxOfEachMessage", "unlimited", "--json", str(fresh), str(book)],
            capture_output=True,
            timeout=180,
        )
        log = report.with_suffix(".log")
        log.write_bytes(run.stdout + run.stderr)
        require(run.returncode in {0, 1} and fresh.is_file(), f"EPUBCheck did not complete, see {log}")
        data = json.loads(fresh.read_text(encoding="utf-8"))
        checker = data["checker"]
        require(
            Path(checker["path"]).resolve() == book and checker["checkerVersion"],
            f"Unexpected EPUBCheck identity for {book}: {checker['path']!r}, version {checker['checkerVersion']!r}",
        )
        fresh.replace(report)
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


def validate_candidate(before, after, reports):
    require(before.version == after.version, "EPUBCheck version changed between runs")
    require(not (after.occurrences - before.occurrences), f"New EPUBCheck errors or warnings, see {reports}")
