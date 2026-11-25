# Tool reference

Run `inspect` first to identify the package, navigation documents, and spine. Read just the members needed for the task. The following tools serve different parts of that workflow.

## EPUBLib

For EPUB 3 package inspection, open the book with `with EPUB(path, generator_tag=False) as book:`. Read `book.metadata`, `book.manifest`, and `book.spine`. The constructor normally adds generator metadata to its model. Passing the flag keeps inspection free of that addition. Use the manifest's navigation property to distinguish the table of contents from chapters. [EPUBLib API](https://epublib.readthedocs.io/en/stable/epublib.html)

## Beautiful Soup

Use `BeautifulSoup(chapter_bytes, "xml")` to find candidate passages or links. For example, `soup.select("a[href]")` returns links to inspect in context. Beautiful Soup delegates parsing to the selected backend, and HTML parsers can repair the same input differently. Confirm each match against the original XHTML with strict XML parsing. [Beautiful Soup parser differences](https://www.crummy.com/software/BeautifulSoup/bs4/doc/#differences-between-parsers)

## EPUBCheck

Run the same executable on the source and candidate. The CLI passes `--maxOfEachMessage unlimited --json FILE` to retain repeated diagnostics. It checks the reported publication path, validator version, severity totals, exit status, and diagnostic occurrences. A successful comparison can include accepted errors inherited from the source. See the JSON reports for their locations. [EPUBCheck CLI](https://www.w3.org/publishing/epubcheck/docs/cli/)

## Editing dependencies

The bundled writer reads original ZIP members, uses strict XML parsing with external DTD loading and entity expansion disabled, and compares SHA-256 digests of uncompressed member bytes. EPUBLib, Beautiful Soup, and ebook-convert are optional inspection and conversion tools. [lxml parser options](https://lxml.de/parsing.html) · [Python zipfile](https://docs.python.org/3/library/zipfile.html)

## First-use detection and managed updates

Run `python3 scripts/skill.py status` for a strictly read-only inventory of Homebrew, Python (3.11+ core; 3.12+ for `ebook-convert`; 3.13+ for `epublib`), `uv`, EPUBCheck, and installed Python libraries.

- **Reuse local environment.** `skill.py` probes the selected Python interpreter's actual version, ABI, and installed packages. Already-installed compatible tools are reused directly without duplicate installation, and Homebrew is never installed when existing tools satisfy requirements.
- **Explicit setup & authorization boundaries.** Run `python3 scripts/skill.py setup` to install missing Python packages into a skill-private virtual environment (`--packages core|all`). Installing system-level tools (Homebrew, system Python, or Homebrew EPUBCheck) requires explicit `--allow-system-install`. Shared environments and Homebrew formulas are never modified automatically.
- **Managed updates & rollback.** Run `python3 scripts/skill.py update --check` to inspect due refreshes or `update` to refresh only Blackflame-managed private environments. New virtual environments are verified before switching; offline or failed updates preserve the previous working runtime. Legacy `~/.config/epublib/settings.json` preferences migrate automatically on first load. Set `BLACKFLAME_CHECKER_JAR` and optionally `BLACKFLAME_JAVA` to reuse an external EPUBCheck JAR.

A successful refresh records `last_updated_at`, `next_update_at`, and a one-month interval. The next check uses the same UTC day and time in the following month, or its final day when the day does not exist. If a refresh fails, the launcher records the error and retains the working environment. It retries on the next invocation. The standalone `epub_patch.py` remains available for callers that manage their own dependencies.
