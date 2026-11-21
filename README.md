# EpubLib

An agent skill for editing existing EPUB 2 and EPUB 3 books. Inspect the package, review a targeted change, and deliver a new EPUB with a record of every changed ZIP member.

## Install

Copy the `epublib/` directory from this checkout into your client's skills directory. For Codex, use `~/.agents/skills/`. Keep the scripts together. The CLI requires Python 3.11 or later and `lxml`. Editing and verification also require EPUBCheck with unlimited JSON diagnostics. [EPUBCheck installation](https://www.w3.org/publishing/epubcheck/docs/installation/)

## Use

> Use $epublib to correct the title and verify that the chapters and reading order are unchanged.

From the repository root, inspect a book, apply a reviewed plan, or verify a candidate prepared elsewhere.

```sh
python3 epublib/scripts/epub_patch.py inspect book.epub > inventory.json
python3 epublib/scripts/epub_patch.py apply book.epub edited.epub --plan plan.json --report-dir apply-report
python3 epublib/scripts/epub_patch.py verify book.epub edited.epub \
  --expected-changes scope.json --preserve-spine --report-dir verify-report
```

The editing guide defines both plan formats and explains how to read a validation result. For a migration, follow the EPUB 3 guide to check navigation, covers, and notes. [Editing guide](epublib/references/editing.md) · [EPUB 3 guide](epublib/references/epub3.md) · [Tool reference](epublib/references/tools.md)

## Development

Run `python3 -m unittest discover -s tests -v`. With EPUBCheck on the path, the suite also builds an EPUB from scratch and exercises all three CLI commands. CI runs this workflow with EPUBCheck 5.4.0.

## License

[MIT](LICENSE)
