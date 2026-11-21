# EpubLib

An agent skill for editing existing EPUB 2 and EPUB 3 books. Inspect the package, review a targeted change, and deliver a new EPUB with a record of every changed ZIP member.

## Install

Download [Epublib.zip](https://github.com/LINYICo/EpubLib/releases/download/v1.2.0/Epublib.zip) and extract the `epublib/` folder into your client's skills directory. For Codex, use `~/.agents/skills/`. Start with Python 3.11 or later and pip.

On first use, the skill asks whether it may install missing tools and whether to optimize for a particular reader. It silently refreshes dependencies on first use and on the first invocation after one calendar month. Updates run in a private environment. If installation is declined, only tools already present are selected for updates.

Preferences and the UTC update schedule are stored in `~/.config/epublib/settings.json`. The skill respects `XDG_CONFIG_HOME` and supports an explicit `EPUBLIB_HOME`. To change preferences, run `python3 epublib/scripts/skill.py configure --auto-install no --platform general` with your choices. [Dependency details](epublib/references/tools.md)

## Use

> Use $epublib to correct the title and verify that the chapters and reading order are unchanged.

From the repository root, inspect a book, apply a reviewed plan, or verify a candidate prepared elsewhere.

```sh
python3 epublib/scripts/skill.py run inspect book.epub > inventory.json
python3 epublib/scripts/skill.py run apply book.epub edited.epub --plan plan.json --report-dir apply-report
python3 epublib/scripts/skill.py run verify book.epub edited.epub \
  --expected-changes scope.json --preserve-spine --report-dir verify-report
```

The editing guide defines both plan formats and explains how to read a validation result. For a migration, follow the EPUB 3 guide to check navigation, covers, and notes. [Editing guide](epublib/references/editing.md) · [EPUB 3 guide](epublib/references/epub3.md) · [Tool reference](epublib/references/tools.md)

## Development

Run `python3 -m unittest discover -s tests -v`. With EPUBCheck on the path, the suite also builds an EPUB from scratch and exercises all three CLI commands. CI runs this workflow with EPUBCheck 5.4.0.

## License

[MIT](LICENSE)
