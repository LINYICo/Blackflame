# Format Conversion

Use this guide when converting e-books between formats via the installed `ebook-convert` CLI (PyPI `ebook-convert`, a standalone Qt-free packaging of the Calibre conversion pipeline).

## Scope & Invocation

- **Distinguish PyPI `ebook-convert` from full Calibre.** Do not assume Calibre GUI tools, `calibredb`, or Qt-dependent PDF plugins are installed.
- **Check supported flags for the specific format pair first:**

```sh
uv run --project <skill_dir> --no-sync ebook-convert input.ext output.ext -h
```

- **Run conversion directly to a separate output path** (never overwrite the input file):

```sh
uv run --project <skill_dir> --no-sync ebook-convert source.html output.epub --title "Book Title" --language en
uv run --project <skill_dir> --no-sync ebook-convert source.epub output.txt
```

(If the skill environment is already active on `PATH`, `ebook-convert` can be invoked directly.)

## Required Post-Conversion Verification

A `0` exit code or valid EPUB ZIP container alone does **not** prove content was preserved cleanly. Always verify:

1. **Output integrity**: Non-empty file and valid target format structure.
2. **Body content**: Inspect extracted chapters/text to confirm actual body paragraphs (including non-ASCII/CJK text, headings, and punctuation) survived without truncation or garbled encoding.
3. **Metadata**: Verify title, author, and language survived conversion.
4. **Images & navigation**: Confirm cover artwork, key illustrations, and table of contents links are present and resolve cleanly.
5. **EPUBCheck (when outputting EPUB)**: Run `epub_safe.run_epubcheck(output_epub, report_path)` (using a distinct temporary report path) and report any diagnostics.

State clearly what was verified programmatically and what still requires visual spot-checking in a target reader.
