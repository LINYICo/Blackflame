# EpubLib

EpubLib is an Agent Skill for inspecting and applying targeted edits to existing EPUB 2 and EPUB 3 publications. It supports package and navigation inspection, metadata corrections, and XHTML copyediting. The editing workflow preserves the source publication and verifies the contents of every unchanged ZIP member.

## Installation

Download the [release ZIP](https://github.com/LINYICo/EpubLib/releases) and extract its `epublib/` directory into your client's skills directory. For Codex, use `~/.agents/skills/`.

```bash
mkdir -p ~/.agents/skills
unzip epublib-1.1.0.zip -d ~/.agents/skills
```

The bundled script requires Python 3.11 or later and `lxml`. Applying edits also requires EPUBCheck with support for unlimited JSON diagnostics. The workflow has been tested with EPUBCheck 5.4.0. See the [tool reference](epublib/references/tools.md) for optional libraries and official documentation.

## Usage

> Use $epublib to update the title to *Revised Edition* and produce a validated copy.

The `inspect` command inventories the source publication. The `apply` command uses an explicit replacement plan, compares EPUBCheck diagnostics, and writes a new EPUB with a change report. Use `verify` to audit structural repairs and optionally enforce the original reading order. See the [editing guide](epublib/references/editing.md) for plans and validation, and the [EPUB 3 guide](epublib/references/epub3.md) for migrations, cover replacement, and Apple Books.

## License

[MIT](LICENSE)
