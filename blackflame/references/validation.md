# Validation & Safety

Use this guide for `epub_safe.py` checks, EPUBCheck delivery rules, three-stage migration verification, and accurate reporting across five quality dimensions.

## Five Quality Dimensions

Passing one check never proves the others—report them separately:

1. **Container & file safety**: Valid ZIP structure (`mimetype` first and uncompressed, safe paths, no duplicates or zip bombs), safe XML parsing (no external entities/DTDs), and preserved inputs/existing files.
2. **EPUBCheck conformance**: Official W3C EPUBCheck fatal, error, and warning diagnostics.
3. **Content fidelity**: Unintended text, resources, or reading order were not altered.
4. **Reader compatibility**: Practical rendering, cover/image pixel limits (Apple Books 5.6M pixels), reflow, and footnote pop-ups.
5. **Unverified aspects**: Explicitly state anything not directly checked (e.g., visual rendering in Apple Books or Kindle).

## EPUBCheck Delivery Rules

- **Record the source baseline first** via `epub_safe.run_epubcheck(source, before_report)`.
- **Reject new diagnostics** with `epub_safe.assert_no_new_diagnostics(before, after)`. Never deliver an output as validated if new errors, warnings, or extra occurrences were introduced.
- **Handle inherited errors transparently.** Never describe an output with unresolved source errors as fully conformant; obtain user acceptance when an existing source error must remain.
- **Match validator capability & report incomplete checks.** Confirm the EPUBCheck version supports the claimed EPUB standard. If `epubcheck` is unavailable, fails, or produces an incomplete report, report validation as **incomplete**.

## Three-Stage Verification (Migrated EPUBs)

Use a temporary directory to separate migration from user edits when upgrading legacy EPUBs (e.g., EPUB 2 → EPUB Latest):

1. **Original source → Migrated baseline**: Verify body text preservation, spine order, images, identifiers, and navigation (do not require an OPF-only diff, since migration legitimately updates structural files).
2. **Migrated baseline → Final output**: Verify the user's exact authorized edit scope (e.g., `expected_changed={opf_member}`).
3. **Already-Latest EPUBs**: Compare Original source → Final output directly.

## Guarantees & Limitations of `scripts/epub_safe.py`

- **`parse_xml(data)`**: Strictly parses XML/XHTML within `LIMIT_XML` (16 MiB) with `no_network=True, load_dtd=False, resolve_entities=False`. Checks XML well-formedness, not EPUB schema validity.
- **`check_zip(archive, stream)` & `protection_entries(names)`**: Validates EPUB `mimetype`, paths, uniqueness, compression, and size bounds; flags `encryption.xml`, `rights.xml`, and `signatures.xml`.
- **`replace_members(source, output, replacements)`**: Refuses to overwrite `source` or any existing file, rejects directory entries as replacement targets, verifies SHA-256 of every unchanged file member, and confirms each replaced member matches the requested bytes.
- **`compare_epubs(source, candidate, ...)`**:
  - Compares exact file-member SHA-256 digests (ignoring empty ZIP directory entries). Use exact member hashes whenever untouched files must remain byte-identical.
  - `preserve_spine=True` validates spine `idref` targets, reading order, and `page-progression-direction`.
  - `preserve_text=True` hashes normalized reading text across spine XHTML documents (preserving block boundaries and `<pre>`/`<code>`/`xml:space="preserve"` whitespace), fails if zero spine XHTML documents are inspectable, and returns `inspected_reading_docs` and `skipped_reading_docs`.
  - **Limitations of `preserve_text`**: Not a full XHTML or visual fidelity proof. Does not detect empty-paragraph or repeated `<br/>` changes, heading-level changes (`<h1>` vs `<h2>`), SVG spine docs or non-spine content (listed in `skipped_reading_docs` when in spine), inherited `xml:space` overrides, inline-markup boundaries, CSS styling, or image pixel changes. Verify in-chapter text/structural diffs directly.
- **`image_dimensions(data)`**: Lightweight header probe for PNG/JPEG/GIF dimensions (`(w, h)` or `None`), not a full decoder.
- **`run_epubcheck(book, report)`**: Rejects any `report` or `.log` path colliding with `book`, with each other, or with any existing file; runs in a temporary directory and publishes `report` via `os.link()` only after identity, completeness, and exit-status checks pass.
