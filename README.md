# EpubLib

EpubLib is an Agent Skill for inspecting and applying targeted edits to existing EPUB 2 and EPUB 3 publications. It supports package and navigation inspection, metadata corrections, and XHTML copyediting. The editing workflow preserves the source publication and verifies the contents of every unchanged ZIP member.

## Installation

Install the [`epublib/`](epublib/) directory in your client's skills directory. For Codex, use `~/.agents/skills/`.

```bash
git clone https://github.com/LINYICo/EpubLib.git
mkdir -p ~/.agents/skills
cp -R EpubLib/epublib ~/.agents/skills/
cp EpubLib/LICENSE ~/.agents/skills/epublib/
```

The bundled script requires Python 3.11 or later and `lxml`. Applying edits also requires EPUBCheck with support for unlimited JSON diagnostics. The workflow has been tested with EPUBCheck 5.4.0. See the [tool reference](epublib/references/tools.md) for optional libraries and official documentation.

## Usage

> Use $epublib to update the title to *Revised Edition* and produce a validated copy.

The `inspect` command inventories the source publication. The `apply` command uses an explicit replacement plan, compares EPUBCheck diagnostics, and writes a new EPUB with a change report. Use `verify` to audit structural repairs prepared separately. See the [editing guide](epublib/references/editing.md) for the plan format and validation rules.

## License

[MIT](LICENSE)
