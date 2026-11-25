## v1.4.2 (2026-11-25)

### Fixes

- Replace GNU-specific `sha256sum --check` in GitHub Actions with cross-platform Python `hashlib` SHA-256 verification so macOS 15 Apple Silicon CI runs pass reliably while keeping EPUBCheck digest checks intact.
- Fix a Python syntax error in external interpreter probing (`runtime.py`), distinguish distinct virtual environments symlinking to the same base Python via `os.path.abspath`, validate CPU architecture alongside ABI, and perform real `from lxml import etree` import checks.
- Persist explicit `--python` interpreter selection across `status`, `setup`, `configure`, `update`, `run`, and `python`, discover `uv`-managed Pythons, and strictly honor `python_manager = "manual"`.
- Merge existing managed packages with newly requested packages when rebuilding private virtual environments (`bootstrap.py`) so adding optional dependencies never drops previously installed packages.
- Make monthly runtime maintenance transactional (`maintenance.py`, `settings.py`): stage and verify both private venv and official EPUBCheck updates before atomically committing `settings.json`, roll back staged directories on any failure, and hold per-env shared locks so in-use virtual environments are never deleted during concurrent runs.

### EPUB Audit & Testing

- Harden `audit.py`: safely skip XML comments and processing instructions, detect duplicate XHTML element IDs, check EPUB 2 missing NCX / `spine/@toc` and EPUB 3 empty TOC, validate real image integrity (PNG/JPEG/GIF/WebP/SVG) and manifest MIME matches, enforce Apple Books 5.6M pixel limits on both covers and inline images, parse CSS comments/`@import`/inline `style`, separate normal external hyperlinks from runtime remote resources, parse multi-token `epub:type`, and separate structural integrity, EPUBCheck conformance, content fidelity, reader compatibility, and unverified checks.
- Add real subprocess and virtual-environment integration tests (`tests/test_integration.py`) covering dual venvs sharing one base Python, broken `lxml` imports, cross-process `--python` persistence, and full `status`/`inspect`/`audit`/`apply`/`verify` workflows extracted from the official `Blackflame.zip`.

## v1.4.1 (2026-11-25)

### Features

- Add standalone `audit` subcommand to produce structured EPUB quality reports covering manifest integrity, spine references, EPUB 2 NCX / EPUB 3 navigation, internal links and fragment IDs, bidirectional footnotes, cover image format and pixel dimensions, missing CSS/font/image assets, and remote resource detection.
- Split `skill.py` into focused modules (`settings.py`, `runtime.py`, `bootstrap.py`, `maintenance.py`, and `skill.py`) with explicit `status` (read-only), `setup`, and `update` commands.
- Add atomic `settings.json` writes (`0600` permissions), corrupt config recovery, and automatic preference migration from legacy `~/.config/epublib/settings.json`.

### Fixes

- Replace unresolvable `astral-sh/setup-uv@v9` in GitHub Actions with `astral-sh/setup-uv@v10.3.3` and `astral-sh/ruff-action@v4.1.0`, add macOS Apple Silicon (`macos-15`) and Python 3.11/3.13 test matrix, always pull latest upstream dependencies (`uv sync --upgrade`), and enforce EPUBCheck integration tests in CI.
- Make `status` strictly read-only, prevent unnecessary Homebrew installation when local tools already satisfy requirements, require explicit `--allow-system-install` for system-level installs, and validate Python version/ABI before reusing virtual environments or host `site-packages`.
- Restrict automatic monthly updates strictly to Blackflame-managed private environments with verify-before-switch rollback on failure or offline runs.

### Dependencies & Testing

- Keep dependencies unconstrained (`Latest`) in `pyproject.toml`, lower core `requires-python` to `>=3.11`, and separate core (`lxml`) from optional EPUB processing dependencies (`beautifulsoup4`, `epublib` on Python 3.13+, `ebook-convert` on Python 3.12+).
- Expand `unittest` coverage across multi-Python/ABI isolation, read-only `status`, unauthorized system installs, offline rollback, concurrent config recovery, EPUB 2/3 quality audits, XXE/duplicate ZIP safety, and standalone Release ZIP execution.

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
