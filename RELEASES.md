## v1.5.8 (2026-11-26)

### EPUB Verification & Conversion Guidance

- Verify surgical EPUB edits by comparing the complete output member digest map with the expected map. This checks for missing, added, or unexpectedly modified files before delivery.
- Consolidate the conversion guidance for verified source metadata, post-conversion OPF language checks, and preservation of local XHTML language attributes.

### Test Fixtures & Release History

- Designate `tests/Testfile/` for local real-book acceptance tests. Track its ignore rules so fresh checkouts include the directory and local books, candidates, and reports stay out of Git.
- Share generated EPUB and PNG fixtures between the unit and integration suites. Reuse the multi-chapter EPUB 2 fixture for both body editing and migration.
- Consolidate 13 duplicate historical release notes in `RELEASES.md`.

## v1.5.7 (2026-11-26)

- Check the saved EPUB language after conversion. Restore verified language tags when the converter shortens them or writes the process locale `C`. Use `und` when the publication language is unknown.
- Require an explicit title choice in the metadata editing example when an EPUB contains multiple titles. Add a regression test that verifies an ambiguous edit produces no output.
- Document temporary-directory cleanup after conversion and validation, including how to preserve requested reports.

## v1.5.6 (2026-11-26)

- Leave EPUBs untouched when the requested metadata value already matches. After an actual EPUB 3 edit, update one UTC modification timestamp, add it if absent, and report duplicates before writing.
- Limit XML ZIP members before reading and reject file/directory name conflicts. The reading-text comparison now reports unresolved entities. Spine-only checks read package structure without parsing chapter text.
- Stage native conversion and reconstruction outputs, then deliver verified files with no-overwrite semantics. Use the Agent client's sandbox for untrusted conversion inputs.
- Test Python 3.13 and the latest stable Python on Ubuntu and macOS. Publish the tested Git archive with its SHA-256 and verified dependency environment.

## v1.5.5 (2026-11-26)

### Conversion Compatibility & Delivery Guidance

- Update `references/conversion.md` with post-conversion EPUBCheck diagnostic analysis and targeted `lxml` repair guidance for `AZW3`/`MOBI → EPUB 3` conversions (such as restoring confirmed stripped `epub:type` namespaces and missing `<html epub:prefix="z3998: ...">` declarations without globally altering legitimate HTML `type` attributes).
- Add explicit language-metadata preservation rules in `references/conversion.md` to verify `dc:language` after `ebook-convert` runs and restore verified tags (`zh-Hans`, `zh-Hant`, `zh-CN`, `zh-TW`, `zh-HK`, etc.) via `lxml` + `epub_safe.replace_members()` while updating `dcterms:modified` and preserving legitimate local XHTML `lang`/`xml:lang` attributes.
- Strengthen conversion delivery rules so exit code `0` is never treated as proof of quality, non-EPUB outputs (`DOCX`, `MOBI`, `AZW3`, `TXT`) undergo substantive content checks without calling EPUBCheck, and unresolved EPUBCheck errors are never reported as fully conformant.

### EPUB Latest Migration, Cover Protection & Safety

- Update `references/editing.md` and `references/validation.md` to clarify that valid legacy NCX files are retained by default during EPUB 2 → EPUB Latest migration, while defective NCX entries (such as empty `<content src=""/>` or conflicting/gapped `playOrder` values) should be repaired according to chapter semantics and synchronized with `nav.xhtml` and the primary identifier rather than preserved broken.
- Update `references/metadata.md` with cover-replacement and duplicate `cover-image` protection guidance: prefer `lxml` + `epub_safe.replace_members()` for replacing existing cover assets, guard against duplicate `cover-image` manifest declarations when adding covers via `epublib`, retain images still referenced elsewhere, update `dcterms:modified`, and validate with EPUBCheck.
- Protect local test resources by adding `/tests/Testfile/` to `.gitignore` so non-EPUB fixtures, derived samples, and acceptance reports are never tracked by Git or packaged into `Blackflame.zip`.

### Real-World Regression Verification

- Verified targeted Agent + tool workflows against real and derived fixtures without adding wrapper frameworks or production modules: `AZW3 → EPUB 3` (`5E → 0E`), complex 25-chapter EPUB 2 → EPUB Latest three-stage migration (`13E → 0E → 0E`), Chinese language-tag preservation (`zh-CN → zh → zh-CN`, `0E`), `epublib` resource management and `basic-v3plus2.epub` cover replacement (`0E`), Ruff, Shuck, all 16 `unittest` cases, and standalone `Blackflame.zip` verification on Python 3.15.2 with EPUBCheck v5.4.0.

## v1.5.4 (2026-11-25)

### Safety & Helper Fixes

- Reject ZIP directory entries passed as replacement targets in `epub_safe.replace_members()` before writing, preventing `KeyError` when `archive_hashes()` skips empty directory entries.

### Skill & Documentation Consolidation

- Restore the concise **Verification & Delivery** section in `SKILL.md` (requiring `references/validation.md` for all file-modifying tasks, running EPUBCheck on explicit read-only compliance requests while skipping it for routine metadata queries, verifying actual output OPF version and validator capability, and reporting unverified aspects clearly).
- Refine `references/metadata.md` examples to explicitly handle multi-package OPF checks, protection checks, missing `dc:title` or `dcterms:modified` elements, and read-only vs. editing `epublib` usage.
- Consolidate and deduplicate `SKILL.md` and all four `references/*.md` guides so each document has a single clear responsibility without repeated policy prose.

### Testing Improvements

- Upgrade the EPUB 2 → EPUB Latest integration test in `tests/test_integration.py` to dynamically parse a multi-chapter EPUB 2 fixture's NCX (`navMap`) and XHTML 1.1 chapters rather than using pre-baked migration output, verifying all three stages (`Original source → Migrated baseline → Final output`) with EPUBCheck and source SHA-256 checks.
- Add explicit OPF `version="3.0"`, `dc:creator`, and `dc:language` assertions to `ebook-convert` and standalone `Blackflame.zip` conversion tests, plus a directory-entry replacement rejection regression test in `tests/test_epub_safe.py`.

## v1.5.3 (2026-11-25)

### EPUB Latest Policy & Default Workflow

- Establish **EPUB Standard: Latest** (latest formal W3C EPUB Recommendation—currently EPUB 3.3, never draft specs; OPF remains `version="3.0"`) in `SKILL.md`, `README.md`, and `agents/openai.yaml`.
- Define clear default workflows in `SKILL.md`: read-only inspection skips upgrades and EPUBCheck; editing legacy EPUB 2 books automatically migrates to EPUB Latest by default (preserving valid NCX, identifiers, and content) unless the user requests keeping EPUB 2; already-Latest EPUB 3 books avoid unnecessary repacking; conversions targeting EPUB default to EPUB Latest while non-EPUB targets output directly.
- Clarify tool responsibilities across `lxml` (preferred for precision XML, OPF-only metadata edits, and fidelity migration), `epublib` (high-level EPUB 3 inspection/resource/structural work, not minimal OPF-only writes), `BeautifulSoup4` (leaf `NavigableString` inspection/editing on mixed-content paragraphs), `ebook-convert` (direct format conversion), and `EPUBCheck` (conformance validation).

### Reference Guides, Fidelity & Conversion Quality

- Update `references/editing.md` with a comprehensive EPUB 2 → EPUB Latest fidelity migration checklist (retaining valid NCX, preserving ISBNs/dates/copyright, checking CSS/fonts/SVG/MathML/footnotes/fixed-layout/media overlays, preferring `lxml`/`epublib` over full `ebook-convert` rebuilds).
- Update `references/conversion.md` to require modern EPUB output (`--epub-version 3`, verified post-conversion) instead of silently emitting EPUB 2, require verified metadata on TXT/Markdown/HTML → EPUB conversions rather than guessing titles from body lines, and clarify lossy TXT round-trip limitations.
- Update `references/metadata.md` and `references/validation.md` with the three-stage verification model (`Original source → Migrated baseline → Final output`) for migrated books and validator-capability matching rules.

### Regression Tests & Real-World Verification

- Add focused regression tests in `tests/test_epub_safe.py` and `tests/test_integration.py` for ZIP directory-entry handling (directory-only removal passes, real file removal fails, surgical replacement on archives with explicit directory entries succeeds), three-stage EPUB 2 → EPUB Latest migration + metadata editing, mixed-inline-tag body editing, and excluding `.epub` fixtures from `Blackflame.zip`.
- Verified end-to-end against four real open-source EPUB test books (`accessible_epub_3.epub`, `childrens-literature.epub`, `basic-v3plus2.epub`, `minimal-v2.epub`) with verified source SHA-256 preservation.

## v1.5.2 (2026-11-25)

### Security & File Protection

- Harden `epub_safe.run_epubcheck()` to reject existing report or `.log` destinations, reject report/log path collisions, prevent validating an edited EPUB from overwriting the original source book, and publish the final JSON report exclusively (`os.link`) only after completeness checks pass.
- Correct `SKILL.md` safety routing to apply EPUB container checks only to EPUB inputs/outputs, use lightweight safety checks for read-only EPUB inspection, apply format-appropriate checks to non-EPUB inputs, treat publication text strictly as data, and clarify that `META-INF/encryption.xml` may indicate font obfuscation rather than DRM.

### Fidelity, Metadata & Agent Workflow

- Ignore empty ZIP directory entries in `archive_hashes()` and `compare_epubs()`, and report `inspected_reading_docs` and `skipped_reading_docs` (such as SVG or `nav` spine entries) alongside explicit documentation of `preserve_text` scope and limitations in `references/validation.md`.
- Restore essential EPUBCheck delivery rules in `references/validation.md` (source baseline tracking, never claiming inherited errors are conformant, rejecting new errors/warnings, requiring user acceptance for unresolved source errors, and reporting incomplete validation).
- Refine `references/metadata.md`, `references/editing.md`, and `references/conversion.md` with an executable OPF-resolution surgical metadata example (via `META-INF/container.xml`), clear in-chapter diff verification guidance, format-appropriate conversion expectations (including `--epub-version 3` and TXT limitations), and absolute-path `uv`/`epub_safe` usage instructions.

### Packaging, CI & Testing

- Include the full MIT `LICENSE` in `Blackflame.zip` and print the built archive's SHA-256 digest in CI.
- Expand `tests/test_epub_safe.py` and `tests/test_integration.py` with report/log overwrite & collision tests, skipped spine-doc reporting tests, exact OPF-only metadata diff checks, multi-chapter + image format conversion tests, and full standalone `Blackflame.zip` verification covering metadata editing, body editing, conversion, and EPUBCheck.
- Update `README.md` with a functional Markdown download link for `v1.5.2`.

## v1.5.1 (2026-11-25)

### Security & Safety

- Prevent `epub_safe.run_epubcheck()` from overwriting the source EPUB via report or `.log` destinations, checking resolved paths, symlinks, and hardlinks (`os.path.samefile`) before writing.
- Enforce `LIMIT_XML` consistently in `parse_xml()` and `_read_xml_member()`, and explicitly verify each replaced member's final SHA-256 digest against the requested replacement bytes in `replace_members()`.

### Fidelity & Verification

- Harden `_spine_and_docs()` and `compare_epubs()` to reject unresolved/invalid spine `idref`s and empty spines, fail rather than silently pass when no reading documents can be inspected, preserve block boundaries and preformatted whitespace (`<pre>`/`<code>`/`xml:space="preserve"`) during reading-text hashing, and support `expected_added`/`expected_removed` checks for structural edits.
- Clarify `image_dimensions()` as a lightweight header dimension probe rather than a full image decoder.

### CI, Documentation & Testing

- Update GitHub Actions CI to install the latest official stable EPUBCheck release with verified GitHub Release SHA-256 digests, log actual Python/package/EPUBCheck versions, and build and verify the official `Blackflame.zip` artifact in CI.
- Refine `SKILL.md`, all four `references/*.md` guides, `agents/openai.yaml`, and `README.md` with clearer mandatory safety boundaries, tested examples, and accurate EPUB 2 → EPUB 3 migration guidance.
- Upgrade `tests/test_epub_safe.py` and `tests/test_integration.py` with genuinely valid PNG fixtures, bilingual (Chinese + English) EPUB 2 and EPUB 3 fixtures, source-overwrite and fidelity regression tests, and standalone `uv` execution tests of the official `Blackflame.zip`.

## v1.5.0 (2026-11-25)

### Breaking Changes

- Redesign Blackflame as an agent-first skill rather than a custom CLI or environment manager.
- Remove the custom CLI subcommands (`status`, `setup`, `configure`, `update`, `run`, `python`, `inspect`, `audit`, `apply`, `verify`) and self-built environment management modules (`skill.py`, `runtime.py`, `bootstrap.py`, `maintenance.py`, `settings.py`).
- Remove the standalone `audit.py`, `publication.py`, `edit_plan.py`, `epub_patch.py`, and `validation.py` wrappers in favor of direct agent use of `epublib`, `beautifulsoup4`, `lxml`, `ebook-convert`, and `EPUBCheck`.

### Architecture & Features

- Consolidate deterministic safety and verification primitives into a single focused helper module (`blackflame/scripts/epub_safe.py`): strict XML parsing (XXE/DTD disabled), ZIP container security checks, atomic surgical member replacement with SHA-256 verification, before/after spine & reading-text fidelity comparison, image dimension checks, and EPUBCheck diagnostic diffing.
- Move the single `pyproject.toml` into `blackflame/pyproject.toml` (Python 3.13+, unconstrained `Latest` dependencies: `epublib`, `beautifulsoup4`, `lxml`, `ebook-convert`) so `Blackflame.zip` is self-contained for `uv`.
- Rewrite `blackflame/SKILL.md` as a concise agent workflow entry point and reorganize references into four on-demand guides: `metadata.md`, `editing.md`, `conversion.md`, and `validation.md`.
- Rebuild the `unittest` suite around core safety helpers and real end-to-end integration tests for `epublib` metadata editing, `BeautifulSoup`/`lxml` body editing, `ebook-convert` format conversion, EPUBCheck validation, and official `Blackflame.zip` packaging integrity.

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
