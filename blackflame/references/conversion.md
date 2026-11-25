# Format Conversion

Use this guide when converting e-books between formats via the installed `ebook-convert` CLI (PyPI `ebook-convert`, a standalone Qt-free packaging of the Calibre conversion pipeline).

## Scope & Default EPUB Output Policy

- **Distinguish PyPI `ebook-convert` from full Calibre.** Do not assume Calibre GUI tools, `calibredb`, or Qt-dependent PDF plugins are installed.
- **Default EPUB outputs to EPUB Latest** (never silently output EPUB 2). Check the CLI's supported modern EPUB flags first with `-h`; currently pass `--epub-version 3`, then verify the actual OPF version (`3.0`), Latest compliance, and EPUBCheck diagnostics (do not treat `--epub-version 3` as a permanent hardcoded definition of Latest).
- **Non-EPUB target formats** (DOCX, TXT, MOBI, AZW3, etc.): Output directly in the requested format without converting back to EPUB.
- **Invoke `ebook-convert` directly from the skill's verified environment** using the absolute skill directory path (avoid custom wrapper scripts):

```sh
uv run --project /abs/path/to/blackflame --no-sync ebook-convert input.ext output.ext -h

# Convert DOCX/HTML/TXT to EPUB Latest (always write to a new output path)
uv run --project /abs/path/to/blackflame --no-sync ebook-convert source.docx output.epub --epub-version 3

# Convert TXT/Markdown to EPUB with verified metadata (never fabricate unknown fields)
uv run --project /abs/path/to/blackflame --no-sync ebook-convert source.txt output.epub \
  --epub-version 3 --title "Verified Book Title" --authors "Verified Author" --language zh

# Convert EPUB to plain text or DOCX
uv run --project /abs/path/to/blackflame --no-sync ebook-convert source.epub output.txt
```

## Metadata Quality During Conversion

- **Inspect source metadata first.** Reuse reliable metadata from the source book whenever available.
- **Never guess titles from body lines or fabricate unknown fields.** Plain text (`TXT`), Markdown, and bare HTML lack full bibliographic metadata, causing `ebook-convert` to guess titles from the first heading or line (such as `THE CONTENTS` or `Section 1`). Supply verified `--title`, `--authors`, and `--language` when known; leave unverified fields unknown rather than inventing authors, ISBNs, publishers, or dates.
- **Round-trip conversions (`EPUB → TXT → EPUB`)**: Plain text cannot retain images, styling, TOC navigation, footnote semantics, or complete metadata. Never describe a TXT round-trip as lossless; if the original EPUB is still available, restore verified metadata from it.

## Format-Appropriate Post-Conversion Verification

A `0` exit code alone never proves content was preserved cleanly. Verify according to what the **source and target formats actually support**:

1. **Output integrity**: Non-empty file and valid target format structure.
2. **Body content**: Inspect extracted chapters or text to confirm actual body paragraphs (including non-ASCII/CJK text, headings, and punctuation) survived without truncation or garbled encoding.
3. **Metadata, images & navigation (when supported by target format)**:
   - **EPUB / DOCX outputs**: Verify OPF version (for EPUB), title, author, language, cover artwork, key illustrations, and table of contents links survived conversion.
   - **Plain-text (`TXT`) or lossy target formats**: Report missing images, styling, TOC navigation, and embedded bibliographic metadata as expected format limitations rather than automatic failure.
4. **EPUBCheck (when outputting EPUB)**: Run `epub_safe.run_epubcheck(output_epub, report_path)` using a fresh temporary report path and confirm the EPUBCheck version supports the target EPUB standard.

State clearly what was verified programmatically, what format limitations apply, and what still requires visual spot-checking in a target reader.
