# Tool reference

Run `inspect` first to identify the package, navigation documents, and spine. Read just the members needed for the task. The following tools serve different parts of that workflow.

## EPUBLib

For EPUB 3 package inspection, open the book with `with EPUB(path, generator_tag=False) as book:`. Read `book.metadata`, `book.manifest`, and `book.spine`. The constructor normally adds generator metadata to its model. Passing the flag keeps inspection free of that addition. Use the manifest's navigation property to distinguish the table of contents from chapters. [EPUBLib API](https://epublib.readthedocs.io/en/stable/epublib.html)

## Beautiful Soup

Use `BeautifulSoup(chapter_bytes, "xml")` to find candidate passages or links. For example, `soup.select("a[href]")` returns links to inspect in context. Beautiful Soup delegates parsing to the selected backend, and HTML parsers can repair the same input differently. Confirm each match against the original XHTML with strict XML parsing. [Beautiful Soup parser differences](https://www.crummy.com/software/BeautifulSoup/bs4/doc/#differences-between-parsers)

## EPUBCheck

Run the same executable on the source and candidate. The CLI passes `--maxOfEachMessage unlimited --json FILE` to retain repeated diagnostics. It checks the reported publication path, validator version, severity totals, exit status, and diagnostic occurrences. A successful comparison can include accepted errors inherited from the source. See the JSON reports for their locations. [EPUBCheck CLI](https://www.w3.org/publishing/epubcheck/docs/cli/)

## Editing dependencies

The bundled writer reads original ZIP members, uses strict XML parsing with external DTD loading and entity expansion disabled, and compares SHA-256 digests of uncompressed member bytes. EPUBLib and Beautiful Soup are optional inspection tools. [lxml parser options](https://lxml.de/parsing.html) · [Python zipfile](https://docs.python.org/3/library/zipfile.html)

## Managed updates

Run `python3 scripts/skill.py status` with the interpreter intended for this book. The inventory covers lxml, EPUBLib, Beautiful Soup, and EPUBCheck. An installed Python distribution supplies its version and installer record. EPUBLib requires Python 3.13 or later. [EPUBLib package](https://pypi.org/project/epublib/)

- **Homebrew.** The launcher matches the resolved installation to a keg in the active Cellar and checks its receipt. Monthly maintenance upgrades identified formulas individually and respects pins. A brewed Python interpreter can contain packages installed separately with pip. For a missing library distributed by the user’s tap, specify `--python-manager homebrew --package PACKAGE --brew-formula PACKAGE=FORMULA`. The launcher verifies that the selected interpreter can see that keg. Choose `--install-epubcheck --checker-manager homebrew` to install missing EPUBCheck with the user's brew. [Homebrew commands](https://docs.brew.sh/Manpage)
- **uv and Python/pip.** Choose `--python-manager uv` or `pip` for missing Python libraries. The selected installer builds a skill-local virtual environment from the selected interpreter and exposes its existing site packages for reuse. Monthly updates rebuild the local environment. A failed build leaves the previous environment available. For existing packages in a user-designated standalone venv, `--dedicated-venv yes` enables updates via each distribution's recorded pip or uv installer. Project, system, and shared environments stay under their owner's update policy. Run the launcher from the interpreter that owns a locked project. [uv environments](https://docs.astral.sh/uv/concepts/projects/sync/) · [Externally managed Python environments](https://packaging.python.org/en/latest/specifications/externally-managed-environments/)
- **Official EPUBCheck.** Select `--install-epubcheck --checker-manager official` to install the official archive using an existing Java runtime. The launcher verifies its published SHA-256 and checks the JAR before recording it. Existing external executables and user-specified JARs are reused. Set `BLACKFLAME_CHECKER_JAR` and optionally `BLACKFLAME_JAVA` for an external JAR. [EPUBCheck releases](https://github.com/w3c/epubcheck/releases)
- **Other managers.** Use the interpreter or validator supplied by Conda, a system package manager, or a manual installation. Unknown ownership remains externally managed. Compatible private runtimes from 1.2.0 remain available as a fallback. First use asks for an installation method only if a needed tool is missing.

Installation consent applies to the named tools in the current configure command. Monthly maintenance updates tools already managed by the skill or their identified owner.

A successful refresh records `last_updated_at`, `next_update_at`, and a one-month interval. The next check uses the same UTC day and time in the following month, or its final day when the day does not exist. If a refresh fails, the launcher records the error and retains the working environment. It retries on the next invocation. The standalone `epub_patch.py` remains available for callers that manage their own dependencies.
