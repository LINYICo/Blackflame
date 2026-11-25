# Release notes

## v1.4.0 · 2026-11-25

### Feature

- Rename the project, skill directory, environment variables, and documentation from `EpubLib` to `Blackflame`.
- Detect Homebrew, Python 3.13+, `uv`, EPUBCheck, and Python dependencies on first use, reusing existing local tools to avoid duplicate installation.
- Silently install only missing runtime components (Homebrew, Python, `uv`, EPUBCheck, and missing Python packages) on first use when no local runtime is present.

### Dependencies & Tooling

- Migrate project dependency management to `uv` (`pyproject.toml` and `uv.lock`) with `epublib`, `beautifulsoup4`, `lxml`, and `ebook-convert` (requires Python 3.13+).
- Remove all `EbookLib` references and standardize on `epublib`.
- Add `ruff.toml` and `shuck.toml` configurations and integrate Ruff and Shuck checks into GitHub Actions CI.

## [v1.3.0](https://github.com/LINYICo/Blackflame/releases/tag/v1.3.0) · 2026-11-22

### Feature

- Detect installed EPUB tools and follow their package manager during monthly maintenance. Support Homebrew, uv, pip, and official EPUBCheck releases.

### Fix

- Require explicit approval and an installation method for each set of missing dependencies. A saved preference no longer authorizes new installs.

### Docs

- Match cover artwork to the ISBN, publisher, and edition. Compare original-resolution candidates and record the selected cover's source and dimensions.
- Distinguish the print edition's ISBN from the EPUB's own identifier when updating bibliographic metadata.

[Full changelog](https://github.com/LINYICo/Blackflame/compare/v1.2.0...v1.3.0)

## [v1.2.0](https://github.com/LINYICo/Blackflame/releases/tag/v1.2.0) · 2026-11-22

### Feature

- Add first-use setup for dependency installation and reading platform preferences. Refresh the private runtime on demand once per calendar month.
- Check the exact occurrence count of reviewed text replacements with `text_edits`.
- Verify the approved ZIP member changes with `--expected-changes` and check that XHTML body text is preserved with `--preserve-text`.

### Fix

- Preserve unresolved EPUB 2 named entities during XML comparison.
- Require a fresh EPUBCheck report and verify that it identifies the publication being checked.

### CI

- Add GitHub Actions coverage for the editing workflow, validator diagnostics, and monthly maintenance.

[Full changelog](https://github.com/LINYICo/Blackflame/compare/v1.1.0...v1.2.0)

## [v1.1.0](https://github.com/LINYICo/Blackflame/releases/tag/v1.1.0) · 2026-11-21

### Feature

- Expand `inspect` to report publication metadata, the primary identifier, cover and navigation resources, and resolved spine entries.
- Add `verify` for independently edited EPUBs. Use `--preserve-spine` to check chapter order, linear flags, and page progression.

### Performance

- Calculate source member digests during repack to avoid a separate read pass.

### Docs

- Add guidance for EPUB 3 migration, Apple Books landmarks, semantic footnotes, and cover replacement.

[Full changelog](https://github.com/LINYICo/Blackflame/compare/v1.0.0...v1.1.0)

## [v1.0.0](https://github.com/LINYICo/Blackflame/releases/tag/v1.0.0) · 2026-11-20

### Feature

- Publish the first stable Agent Skill for inspecting and editing EPUB 2 and EPUB 3 books.
- Apply reviewed metadata and XHTML replacements to a separate EPUB and verify the contents of unchanged ZIP members.
- Compare EPUBCheck diagnostics before and after editing. Reject new warnings and errors, including additional occurrences of existing diagnostics.

### Docs

- Provide English installation and editing guides and distribute the skill under the MIT License.
