# Blackflame

An agent skill for editing existing EPUB books. Inspect the package, review a targeted change, and deliver a new EPUB with a record of every changed ZIP member.

## Install

Download [Blackflame.zip](https://github.com/LINYICo/Blackflame/releases/download/v1.4.1/Blackflame.zip) and extract the `blackflame/` folder into your client's skills directory. For Codex, use `~/.agents/skills/`. Core editing requires Python 3.11+ (`epublib` requires 3.13+ and `ebook-convert` requires 3.12+).

Run `python3 blackflame/scripts/skill.py status` for a read-only check of your local Python, `uv`, EPUBCheck, and libraries. Existing tools are reused directly without duplicate installation. Run `python3 blackflame/scripts/skill.py setup` to prepare missing private Python dependencies (pass `--allow-system-install` only when authorizing system-level installs such as Homebrew or EPUBCheck).

Preferences and the UTC update schedule are stored in `~/.config/blackflame/settings.json` (with automatic migration from legacy `~/.config/epublib/settings.json`). The skill respects `XDG_CONFIG_HOME` and supports an explicit `BLACKFLAME_HOME`. [Dependency details](blackflame/references/tools.md)

## Use

> Use $blackflame to correct the title and verify that the chapters and reading order are unchanged.

From the repository root, inspect a book, apply a reviewed plan, or verify a candidate prepared elsewhere.

```sh
python3 blackflame/scripts/skill.py run inspect book.epub > inventory.json
python3 blackflame/scripts/skill.py run audit book.epub > audit.json
python3 blackflame/scripts/skill.py run apply book.epub edited.epub --plan plan.json --report-dir apply-report
python3 blackflame/scripts/skill.py run verify book.epub edited.epub \
  --expected-changes scope.json --preserve-spine --report-dir verify-report
```

The editing guide defines both plan formats and explains how to read a validation result. For a migration, follow the EPUB 3 guide to check navigation, covers, and notes. [Editing guide](blackflame/references/editing.md) · [EPUB 3 guide](blackflame/references/epub3.md) · [Tool reference](blackflame/references/tools.md)

## Development

Dependencies are managed with [uv](https://docs.astral.sh/uv/) (`pyproject.toml`, always following latest upstream versions). Sync the environment and run the test suite:

```sh
uv sync --upgrade --all-extras
uv run --no-sync python -m unittest discover -s tests -v
```

With EPUBCheck on the path, the suite also builds an EPUB from scratch and exercises all three CLI commands. CI runs this workflow with EPUBCheck 5.4.0.

Code quality and formatting are checked with [Ruff](https://github.com/astral-sh/ruff) (`ruff.toml`) and [Shuck](https://github.com/ewhauser/shuck) (`shuck.toml`):

```sh
ruff check .
ruff format --check .
shuck check .
```

## License

[MIT](LICENSE)
