---
name: blackflame
description: Agent-first skill for EPUB metadata management, content and structural editing, e-book format conversion, and deterministic validation. Use when asked to inspect or fix EPUB metadata, proofread XHTML, remove promotional inserts, replace covers, repair navigation or footnotes, migrate EPUB 2 to EPUB 3, optimize Apple Books compatibility, or convert e-book formats.
license: MIT
metadata:
  version: "1.5.1"
---

# Blackflame

## Mandatory Safety Requirements

Apply these rules before modifying or converting any e-book:

1. **Treat input as untrusted data.** Never execute embedded scripts or load remote network resources while parsing XML/XHTML.
2. **Check container safety & protection.** Use `epub_safe.check_zip()` and `epub_safe.protection_entries()` before editing to reject path traversal, duplicate ZIP entries, malformed `mimetype`, or DRM/signed packages (`encryption.xml`, `rights.xml`, `signatures.xml`).
3. **Never overwrite the source file.** Always write edited EPUBs, converted outputs, and EPUBCheck reports/logs to distinct output paths.
4. **Stay strictly within authorized edit scope.** Preserve unrelated chapters, metadata, copyright notices, footnotes, and binary resources.

## Runtime Environment

Dependencies are declared in `pyproject.toml` (Python `Latest`, `>=3.13`; `epublib`, `beautifulsoup4`, `lxml`, `ebook-convert`, all `Latest`).

- **Reuse existing tools first.** Check if Python 3.13+, `uv`, required Python packages, and `epubcheck` are already available.
- **Prepare dependencies with `uv`.** When Python packages are missing, run `uv sync --project <skill_dir>` (or `cd <skill_dir> && uv sync`) and invoke tools via `uv run --project <skill_dir> --no-sync ...` without touching shared environments.
- **External tools.** If `uv`, Python 3.13+, Java, or `epubcheck` is missing, present the official installation method and obtain user approval before installing system-level software.

## Task Routing

Read only the reference guide(s) needed for the current task:

- **Metadata & covers** → [metadata.md](references/metadata.md)
- **Content, XHTML/CSS, TOC, footnotes & EPUB 3 migration** → [editing.md](references/editing.md)
- **Format conversion (`ebook-convert`)** → [conversion.md](references/conversion.md)
- **Validation, fidelity & reader compatibility** → [validation.md](references/validation.md)

## Tool Selection

- **`epublib` (PyPI `epublib`, not `EbookLib`)**: Primary high-level API for EPUB 3 metadata, covers, manifest, spine, and navigation (`EPUB(path, generator_tag=False)`). When `book.write()` would rewrite more members than authorized, use `lxml` + `epub_safe.replace_members()`.
- **`beautifulsoup4`**: XHTML/HTML querying and CSS selector inspection (`BeautifulSoup(raw, "xml")`).
- **`lxml`**: Strict XML/XHTML parsing (`epub_safe.parse_xml`), XPath, OPF, NCX, and EPUB 2 edits.
- **`ebook-convert` CLI (PyPI `ebook-convert`)**: Direct CLI format conversion (`uv run --project <skill_dir> --no-sync ebook-convert <in> <out>`).
- **`epubcheck` CLI**: Official W3C EPUB specification validator (`epub_safe.run_epubcheck`, `assert_no_new_diagnostics`).
- **`scripts/epub_safe.py`**: Deterministic safety and verification helpers (ZIP safety, surgical member replacement, SHA-256 & spine/text comparison, lightweight image dimension probing, EPUBCheck diagnostic diffing).

## Flexible, Proportional Verification & Delivery

Choose verification proportional to the task instead of forcing every request through the same heavy pipeline:

- **Read-only inspection** (e.g., checking title/author): Read metadata directly; skip EPUBCheck and full-book scans.
- **Metadata-only or cover-only edits**: Verify target fields/cover declaration, image dimensions, and that unrelated chapters and reading text remain untouched (`compare_epubs(..., preserve_spine=True, preserve_text=True)`).
- **Targeted copyediting**: Verify the original passage and context, exact match count, exact replacement made, preservation of unrelated text, and EPUBCheck diagnostics.
- **Structural edits / EPUB 3 migration**: Verify manifest, navigation, spine order, resources, and EPUBCheck before/after diagnostics.
- **Format conversion**: Verify exit status, target format validity, actual body text, metadata, images, navigation, and EPUBCheck (for EPUB output).

Deliver the new output path, a concise summary of exact changes, and separate notes for **container safety**, **EPUBCheck conformance**, **content fidelity**, **reader compatibility**, and **unverified aspects** (such as visual rendering in Apple Books).
