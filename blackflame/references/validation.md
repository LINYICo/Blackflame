# Validation & Safety

Use this guide to choose appropriate checks and report results accurately across five distinct dimensions.

## Five Quality Dimensions

Passing one check never proves the others:

1. **File & container safety**: Valid ZIP structure (`mimetype` first and uncompressed, no `../` path traversal, no duplicate entries, no zip bombs), safe XML parsing (no external entities or network DTDs), and intact source file.
2. **EPUBCheck conformance**: Official W3C EPUBCheck fatal, error, and warning diagnostics.
3. **Content fidelity**: Unintended text, paragraph boundaries, preformatted whitespace, footnotes, images, CSS, or spine reading order were not altered.
4. **Reader compatibility**: Practical rendering, cover pixel limits (Apple Books 5.6M pixels), reflow, and footnote pop-ups in target readers.
5. **Unverified aspects**: Anything not directly checked (e.g., visual typography in Apple Books or Kindle) must be reported explicitly.

## `scripts/epub_safe.py` Guarantees & Limitations

- **`parse_xml(data)`**: Strictly parses XML/XHTML within `LIMIT_XML` (16 MiB) with `no_network=True, load_dtd=False, resolve_entities=False`. Guarantees XML well-formedness, not EPUB schema validity.
- **`check_zip(archive, stream)` & `protection_entries(names)`**: Validates EPUB `mimetype` header, path safety, uniqueness, compression, and size bounds; flags `encryption.xml`, `rights.xml`, and `signatures.xml`.
- **`replace_members(source, output, replacements)`**: Refuses to overwrite `source` or any existing file; verifies SHA-256 of every unchanged member and verifies each replaced member matches the exact requested bytes.
- **`compare_epubs(source, candidate, expected_changed=..., expected_added=..., expected_removed=..., preserve_spine=..., preserve_text=...)`**:
  - Verifies exact ZIP member diffs by SHA-256.
  - Validates that every spine `idref` resolves to an existing archive member and checks reading order and `page-progression-direction`.
  - When `preserve_text=True`, fails if zero spine XHTML documents were inspected; hashes structured text preserving block boundaries (`<p>`, `<div>`, headings, `<li>`, `<br>`, etc.) and exact whitespace inside `<pre>`/`<code>`/`xml:space="preserve"`. **Limitation**: Does not verify CSS styling, image pixels, or visual layout.
- **`image_dimensions(data)`**: Lightweight dimension probe for PNG, JPEG, and GIF headers (`(width, height)` or `None`). **Limitation**: Not a full image decoder or pixel-level integrity validator.
- **`run_epubcheck(book, report)` & `assert_no_new_diagnostics(before, after)`**: Rejects any `report` or `.log` path that would overwrite `book` (including via symlinks/hardlinks), runs EPUBCheck with `--maxOfEachMessage unlimited --json`, verifies report identity/completeness, and rejects any new errors, warnings, or increased occurrence counts.
