# Format Conversion

Use this guide for direct e-book format conversion via the installed `ebook-convert` CLI (PyPI `ebook-convert`, standalone Qt-free Calibre conversion pipeline—do not assume Calibre GUI tools, `calibredb`, or Qt PDF plugins exist).

## Direct Invocation & Default EPUB Output

Per [SKILL.md](../SKILL.md), conversions targeting EPUB default to **EPUB Latest** (never silently EPUB 2), while non-EPUB targets (DOCX, TXT, MOBI, AZW3, etc.) output directly.

1. Check supported flags for the format pair first (`-h`), then invoke directly from the skill environment to a new output path:

```sh
uv run --project /abs/path/to/blackflame --no-sync ebook-convert input.ext output.ext -h

# Convert to EPUB Latest (currently pass --epub-version 3; verify actual OPF version afterward)
uv run --project /abs/path/to/blackflame --no-sync ebook-convert source.docx output.epub --epub-version 3

# Convert TXT/Markdown/HTML to EPUB with verified metadata (never guess from first line or fabricate fields)
uv run --project /abs/path/to/blackflame --no-sync ebook-convert source.txt output.epub \
  --epub-version 3 --title "Verified Title" --authors "Verified Author" --language zh

# Convert EPUB to TXT or DOCX
uv run --project /abs/path/to/blackflame --no-sync ebook-convert source.epub output.txt
```

2. Inspect source metadata first and reuse reliable values. For `TXT`, Markdown, or bare HTML inputs, pass verified `--title`, `--authors`, and `--language` so `ebook-convert` does not guess titles from body lines (such as `THE CONTENTS` or `Section 1`). Leave unverified fields unknown.
3. Never treat `EPUB → TXT → EPUB` as lossless; if the original EPUB is available, restore verified metadata from it and note TXT's inherent loss of images, styling, TOC, and footnote semantics.

## Format-Appropriate Verification

A `0` exit code alone never proves content survived cleanly. Verify according to what the source and target formats support:

- **Integrity & body text**: Non-empty valid output; confirm paragraphs, headings, punctuation, and non-ASCII/CJK text survived without truncation or garbling.
- **EPUB / DOCX outputs**: Check actual OPF `version` (for EPUB), title, author, language, cover/illustrations, and TOC links.
- **TXT / lossy outputs**: Report absent images, styling, TOC, and embedded metadata as expected format limitations rather than automatic failure.
- **EPUB outputs**: Run `epub_safe.run_epubcheck()` using a fresh temporary report path and confirm the validator supports the target EPUB standard ([validation.md](validation.md)).
