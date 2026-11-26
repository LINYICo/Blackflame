# Blackflame

An agent-first skill for e-book processing in Codex, Gemini, Claude Code, and other agent clients. Blackflame provides domain expertise, tool-usage rules, and deterministic safety helpers so agents can reliably handle EPUB metadata, content and structural editing, format conversion, and validation.

## Install

Download [Blackflame.zip](https://github.com/LINYICo/Blackflame/releases/latest/download/Blackflame.zip) (see [release history](RELEASES.md)) and extract the `blackflame/` folder into your client's skills directory (for Codex, `~/.agents/skills/`).

The skill includes its own `blackflame/pyproject.toml` (Python 3.13+, managed with [uv](https://docs.astral.sh/uv/)). Prepare dependencies inside the skill directory when needed:

```sh
uv sync --project /abs/path/to/blackflame
```

Install the [official EPUBCheck CLI](https://github.com/w3c/epubcheck/releases) and its required Java runtime for EPUB conformance checks. Verify the launcher with `epubcheck --version`. Run the skill's Python and `ebook-convert` through `uv run --project /abs/path/to/blackflame --no-sync`.

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
git archive --format=zip --output=Blackflame.zip HEAD LICENSE blackflame
uv run --project blackflame --no-sync python -m unittest discover -s tests -v
```

Code quality is checked with [Ruff](https://github.com/astral-sh/ruff) (`ruff.toml`) and [Shuck](https://github.com/ewhauser/shuck) (`shuck.toml`):

```sh
ruff check .
ruff format --check .
shuck check .
```

CI tests Python 3.13 and the latest stable Python on Ubuntu and macOS. To release, push a matching `vX.Y.Z` tag or land a `Release vX.Y.Z` commit on `main`. Once the test matrix and lint pass, GitHub publishes the tested ZIP, its SHA-256, and the release environment. The version must match `blackflame/SKILL.md`, `blackflame/pyproject.toml`, and the first entry in `RELEASES.md`.

## License

[MIT](LICENSE)
