# Tool reference

Run `inspect` first to identify the package, navigation documents, and spine. Read just the members needed for the task. The following tools serve different parts of that workflow.

## EPUBLib

For EPUB 3 package inspection, open the book with `with EPUB(path, generator_tag=False) as book:`. Read `book.metadata`, `book.manifest`, and `book.spine`. The constructor normally adds generator metadata to its model. Passing the flag keeps inspection free of that addition. Use the manifest's navigation property to distinguish the table of contents from chapters. [EPUBLib API](https://epublib.readthedocs.io/en/stable/epublib.html)

## EbookLib

Use `epub.read_epub(path)` for EPUB 2 or EPUB 3. The value of `book.get_metadata("DC", "creator")` is a list of value and attribute pairs. Retain the attributes when distinguishing authors from contributors. EbookLib documents limitations when writing a book it has read. Use the original ZIP member as the source of each replacement. [EbookLib tutorial](https://docs.sourcefabric.org/projects/ebooklib/en/latest/tutorial.html)

## Beautiful Soup

Use `BeautifulSoup(chapter_bytes, "xml")` to find candidate passages or links. For example, `soup.select("a[href]")` returns links to inspect in context. Beautiful Soup delegates parsing to the selected backend, and HTML parsers can repair the same input differently. Confirm each match against the original XHTML with strict XML parsing. [Beautiful Soup parser differences](https://www.crummy.com/software/BeautifulSoup/bs4/doc/#differences-between-parsers)

## EPUBCheck

Run the same executable on the source and candidate. The CLI passes `--maxOfEachMessage unlimited --json FILE` to retain repeated diagnostics. It checks the reported publication path, validator version, severity totals, exit status, and diagnostic occurrences. A successful comparison can include accepted errors inherited from the source. See the JSON reports for their locations. [EPUBCheck CLI](https://www.w3.org/publishing/epubcheck/docs/cli/)

## Editing dependencies

The bundled writer reads original ZIP members, uses strict XML parsing with external DTD loading and entity expansion disabled, and compares SHA-256 digests of uncompressed member bytes. EPUBLib, EbookLib, and Beautiful Soup are optional inspection tools. [lxml parser options](https://lxml.de/parsing.html) · [Python zipfile](https://docs.python.org/3/library/zipfile.html)

## Managed updates

The skill launcher selects the latest compatible Python packages from pip's configured index. The managed set includes lxml, EbookLib and Beautiful Soup. EPUBLib requires Python 3.13 or later. EPUBCheck comes from the latest official GitHub release and its archive is verified against the published SHA-256. When a Java runtime is missing and automatic installation is enabled, the launcher installs a private runtime via jdk4py. Use `python3 scripts/skill.py python` for Python tools in this environment. [EPUBLib package](https://pypi.org/project/epublib/) · [EPUBCheck releases](https://github.com/w3c/epubcheck/releases)

A successful refresh records `last_updated_at`, `next_update_at`, and a one-month interval. The next check uses the same UTC day and time in the following month, or its final day when the day does not exist. If a refresh fails, the launcher records the error and retains the working environment. It retries on the next invocation. The standalone `epub_patch.py` remains available for callers that manage their own dependencies.
