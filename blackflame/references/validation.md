# Validation & Safety

Use this guide to interpret `epub_safe.py` checks, apply EPUBCheck delivery rules, and report results accurately across five distinct quality dimensions.

## Five Quality Dimensions

Passing one check never proves the others—report them separately:

1. **Container & file safety**: Valid ZIP structure (`mimetype` first and uncompressed, no path traversal, no duplicate entries, no zip bombs), safe XML parsing (no external entities or network DTDs), and preserved inputs/existing files.
2. **EPUBCheck conformance**: Official W3C EPUBCheck fatal, error, and warning diagnostics.
3. **Content fidelity**: Unintended text, resources, or reading order were not altered.
4. **Reader compatibility**: Practical rendering, cover pixel limits (Apple Books 5.6M pixels), reflow, and footnote pop-ups in target readers.
5. **Unverified aspects**: Anything not directly checked (such as visual typography or CSS rendering in Apple Books or Kindle) must be stated explicitly.

## EPUBCheck Delivery Rules

- **Establish the source baseline first.** Before editing an EPUB, run `epub_safe.run_epubcheck(source, before_report)` to record any pre-existing errors or warnings.
- **Never introduce new diagnostics.** Compare before/after runs with `epub_safe.assert_no_new_diagnostics(before, after)`. Do not deliver an output as successfully validated if any new error, warning, or additional occurrence of an existing diagnostic was introduced.
- **Never claim inherited errors are conformant.** If the source book already contained EPUBCheck errors that were not resolved, do not describe the output as fully conformant; report the inherited baseline clearly and obtain user acceptance when an existing source error must remain unresolved.
- **Report incomplete validation transparently.** If `epubcheck` is unavailable, crashes, or produces an incomplete/truncated report, report validation as **incomplete** (never imply validation passed).

## Actual Guarantees & Limitations of `scripts/epub_safe.py`

- **`parse_xml(data)`**: Strictly parses XML/XHTML within `LIMIT_XML` (16 MiB) with `no_network=True, load_dtd=False, resolve_entities=False`. Guarantees XML well-formedness, not EPUB schema validity.
- **`check_zip(archive, stream)` & `protection_entries(names)`**: Validates EPUB `mimetype` header, path safety, uniqueness, compression, and size bounds; flags `encryption.xml`, `rights.xml`, and `signatures.xml`.
- **`replace_members(source, output, replacements)`**: Refuses to overwrite `source` or any existing file; verifies SHA-256 of every unchanged file member and verifies each replaced member matches the exact requested bytes.
- **`compare_epubs(source, candidate, ...)`**:
  - Compares exact file-member SHA-256 hashes (ignoring empty ZIP directory entries). Use exact member hashes whenever untouched chapters, images, CSS, or fonts must remain byte-identical.
  - With `preserve_spine=True`, verifies all spine `idref` targets exist and checks reading order and `page-progression-direction`.
  - With `preserve_text=True`, hashes normalized reading text across spine XHTML documents (preserving block-tag boundaries and `<pre>`/`<code>`/`xml:space="preserve"` whitespace), fails if zero spine XHTML documents are inspectable, and returns `inspected_reading_docs` and `skipped_reading_docs`.
  - **Known limitations of `preserve_text`**: Normalized text hashing is **not** a full XHTML or visual fidelity proof. It does not detect empty-paragraph or repeated `<br/>` differences, heading-level changes (`<h1>` vs `<h2>`), changes inside SVG spine documents or non-spine reading content (reported in `skipped_reading_docs` when in spine), complex inherited `xml:space` overrides, inline-markup token boundaries, CSS styling, or image pixel changes. For authorized edits inside a chapter, verify the actual text and structural diff directly; use EPUBCheck for spec conformance and task-specific inspection for layout/navigation.
- **`image_dimensions(data)`**: Lightweight header probe for PNG, JPEG, and GIF dimensions (`(width, height)` or `None`). Not a full image decoder or pixel-level integrity validator.
- **`run_epubcheck(book, report)` & `assert_no_new_diagnostics(before, after)`**: Rejects any `report` or `.log` path that collides with `book`, with each other, or with any already-existing file; runs EPUBCheck in a dedicated temporary directory; publishes `report` only after verifying identity, completeness, and exit status so failed/incomplete runs never leave a misleading report JSON behind.
