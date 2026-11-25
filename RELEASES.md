## v1.4.0 (2026-11-25)

### Features

- Rename the project, skill directory, environment variables, and documentation from `EpubLib` to `Blackflame`.
- Detect Homebrew, Python 3.13+, `uv`, EPUBCheck, and Python libraries on first use, reusing existing local tools to avoid duplicate installation.
- Silently install only missing runtime components (Homebrew, Python, `uv`, EPUBCheck, and missing Python packages) on first use when no local environment is present.

### Dependencies & Tooling

- Migrate project dependency management to `uv` (`pyproject.toml` and `uv.lock`) with `epublib`, `beautifulsoup4`, `lxml`, and `ebook-convert` (requires Python 3.13+).
- Remove all `EbookLib` references and standardize on `epublib`.
- Add `ruff.toml` and `shuck.toml` configurations and integrate Ruff and Shuck checks into GitHub Actions CI.

## v1.3.0 (2026-11-22)

### Features

- Detect installed EPUB tools and follow their package manager during monthly maintenance across Homebrew, `uv`, `pip`, and official EPUBCheck releases.

### Fixes

- Require explicit approval and an installation method for each set of missing dependencies so saved preferences do not authorize new installs unexpectedly.

### Documentation

- Match cover artwork to the ISBN, publisher, and edition, comparing original-resolution candidates and recording the selected cover's source and dimensions.
- Distinguish the print edition's ISBN from the EPUB's own identifier when updating bibliographic metadata.

## v1.2.0 (2026-11-22)

### Features

- Add first-use setup for dependency installation and reading platform preferences, with monthly on-demand runtime refreshes.
- Verify exact occurrence counts of reviewed text replacements via `text_edits`.
- Verify approved ZIP member changes with `--expected-changes` and check XHTML body text preservation with `--preserve-text`.

### Fixes

- Preserve unresolved EPUB 2 named entities during XML comparison.
- Require a fresh EPUBCheck report and verify that it identifies the publication being checked.

### CI

- Add GitHub Actions coverage for the editing workflow, validator diagnostics, and monthly maintenance.

## v1.1.0 (2026-11-21)

### Features

- Expand `inspect` to report publication metadata, the primary identifier, cover and navigation resources, and resolved spine entries.
- Add `verify` for independently edited EPUBs, with `--preserve-spine` to check chapter order, linear flags, and page progression.

### Performance

- Calculate source member digests during repack to avoid a separate read pass.

### Documentation

- Add guidance for EPUB 3 migration, Apple Books landmarks, semantic footnotes, and cover replacement.

## v1.0.0 (2026-11-20)

### Features

- Publish the initial stable Agent Skill for inspecting and editing EPUB 2 and EPUB 3 publications.
- Apply reviewed metadata and XHTML replacements to a separate EPUB and verify unchanged ZIP members.
- Compare EPUBCheck diagnostics before and after editing, rejecting new warnings, errors, or additional occurrences of existing diagnostics.

### Documentation

- Provide English installation and editing guides under the MIT License.
