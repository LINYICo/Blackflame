# Blackflame

An agent-first skill for e-book processing in Codex, Gemini, Claude Code, and other agent clients. Blackflame provides domain expertise, tool-usage rules, and deterministic safety helpers so agents can reliably handle EPUB metadata, content and structural editing, format conversion, and validation.

## Install

Download `Blackflame.zip` from [Blackflame Releases](https://github.com/LINYICo/Blackflame) (`v1.5.3`, see [v1.5.3 notes](releases/v1.5.3.md)) and extract the `blackflame/` folder into your client's skills directory (for Codex, `~/.agents/skills/`).

The skill includes its own `blackflame/pyproject.toml` (Python 3.13+, managed with [uv](https://docs.astral.sh/uv/)). Prepare dependencies inside the skill directory when needed:

```sh
uv sync --project /abs/path/to/blackflame
```

## Capabilities & Tech Stack

- **Metadata**: Inspect, verify, and edit EPUB title, author, translator, ISBN, publisher, language, series, and cover artwork.
- **Editing**: Proofread XHTML, fix typography, remove promotional inserts, repair TOC/navigation/footnotes, automatically migrate EPUB 2 to EPUB Latest, and optimize Apple Books compatibility.
- **Conversion**: Convert e-book formats directly via the `ebook-convert` CLI, defaulting EPUB outputs to EPUB Latest.

Standards & runtime tools (all `Latest`): **EPUB Standard** (`Latest`, [W3C EPUB](https://www.w3.org/TR/epub/latest/)), [Python 3.13+](https://www.python.org), [epublib](https://epublib.readthedocs.io/en/stable/), [Beautiful Soup 4](https://pypi.org/project/beautifulsoup4/), [lxml](https://github.com/lxml/lxml), [ebook-convert](https://pypi.org/project/ebook-convert/), and [EPUBCheck](https://github.com/w3c/epubcheck/releases).

## Use

Invoke the skill naturally in your agent client:

> Use $blackflame to fix the title, author, and ISBN of `book.epub` and verify that the chapters and reading order are unchanged.

> Use $blackflame to remove the promotional page at the end of `book.epub`, check the cover dimensions for Apple Books, and validate with EPUBCheck.

> Use $blackflame to convert `draft.html` into an EPUB and verify it with EPUBCheck.

## Development

Sync latest dependencies and run the test suite from the repository root:

```sh
uv sync --project blackflame --upgrade
uv run --project blackflame --no-sync python -m unittest discover -s tests -v
```

Code quality is checked with [Ruff](https://github.com/astral-sh/ruff) (`ruff.toml`) and [Shuck](https://github.com/ewhauser/shuck) (`shuck.toml`):

```sh
ruff check .
ruff format --check .
shuck check .
```

## License

[MIT](LICENSE)
