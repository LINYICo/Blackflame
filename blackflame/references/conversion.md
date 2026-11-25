# Format Conversion

Use this guide when converting e-books between formats via the installed `ebook-convert` CLI (PyPI `ebook-convert`, a standalone Qt-free packaging of the Calibre conversion pipeline).

## Scope & Invocation

- **Distinguish PyPI `ebook-convert` from full Calibre.** Do not assume Calibre GUI tools, `calibredb`, or Qt-dependent PDF plugins are installed.
- **Invoke the `ebook-convert` executable from the skill's verified environment** using the absolute skill directory path (avoid custom wrapper scripts):

```sh
uv run --project /abs/path/to/blackflame --no-sync ebook-convert input.ext output.ext -h
```

- **Verify supported flags for the specific format pair first** with `-h`, then run directly to a separate, non-existent output path (never overwrite the input file):

```sh
# Convert HTML/DOCX/TXT to EPUB 3 (pass --epub-version 3 for modern readers; default is EPUB 2)
uv run --project /abs/path/to/blackflame --no-sync ebook-convert source.html output.epub \
  --title "Book Title" --authors "Author Name" --language en --epub-version 3

# Convert EPUB to plain text or DOCX
uv run --project /abs/path/to/blackflame --no-sync ebook-convert source.epub output.txt
```

- When converting from plain text or Markdown to EPUB, pass `--title`, `--authors`, and `--language` explicitly so `ebook-convert` does not guess metadata from the first heading or line.

## Format-Appropriate Post-Conversion Verification

A `0` exit code alone never proves content was preserved cleanly. Verify according to what the **source and target formats actually support**:

1. **Output integrity**: Non-empty file and valid target format structure.
2. **Body content**: Inspect extracted chapters or text to confirm actual body paragraphs (including non-ASCII/CJK text, headings, and punctuation) survived without truncation or garbled encoding.
3. **Metadata, images & navigation (when supported by target format)**:
   - **EPUB / DOCX outputs**: Verify title, author, language, cover artwork, key illustrations, and table of contents links survived conversion.
   - **Plain-text (`TXT`) or lossy target formats**: Expect that images, styling, TOC navigation, and embedded bibliographic metadata cannot be retained—report these as expected format limitations rather than treating their absence as a conversion failure.
4. **EPUBCheck (when outputting EPUB)**: Run `epub_safe.run_epubcheck(output_epub, report_path)` using a fresh temporary report path and report any diagnostics.

State clearly what was verified programmatically, what format limitations apply, and what still requires visual spot-checking in a target reader.
