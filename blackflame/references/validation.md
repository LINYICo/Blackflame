# Validation & Safety

Use this guide to verify EPUB integrity, edit scope, content fidelity, EPUBCheck conformance, and reader compatibility.

## Four Distinct Quality Dimensions

Never treat one passing check as proof of all four:

1. **Container & structural integrity**: Valid ZIP container (`mimetype` first and uncompressed, no path traversal, no duplicate entries, no zip bombs), valid XML, valid manifest/spine/navigation links.
2. **EPUBCheck specification conformance**: Official W3C EPUBCheck diagnostics (fatal, error, warning).
3. **Content fidelity**: Unintended text, punctuation, footnotes, images, CSS, or chapter order were not altered.
4. **Reader compatibility**: Actual rendering, cover display, reflow, and footnote pop-ups in target readers (e.g., Apple Books, Kindle).

Always report unverified dimensions explicitly (for example, when visual rendering in Apple Books was not tested).

## Deterministic Helpers (`scripts/epub_safe.py`)

Import directly from `scripts/epub_safe.py` when deterministic guarantees are needed:

- **`parse_xml(data)`**: Strict `lxml` parser with `no_network=True, load_dtd=False, resolve_entities=False`.
- **`check_zip(archive, stream)` & `protection_entries(names)`**: Rejects malformed `mimetype`, `../` paths, duplicate ZIP entries, encrypted entries, symlinks, and detects `encryption.xml` / `rights.xml` / `signatures.xml`.
- **`replace_members(source, output, replacements)`**: Atomically writes a new EPUB replacing only named ZIP members, verifying SHA-256 of every unchanged and changed member.
- **`compare_epubs(source, candidate, expected_changed=..., preserve_spine=..., preserve_text=...)`**: Verifies added/removed/changed members by SHA-256, checks spine reading order & page progression, and verifies spine XHTML body text hashes.
- **`image_dimensions(data)`**: Checks PNG, JPEG, and GIF integrity and `(width, height)` against `APPLE_MAX_IMAGE_PIXELS` (`5_600_000`).
- **`run_epubcheck(book, report)` & `assert_no_new_diagnostics(before, after)`**: Runs EPUBCheck with `--maxOfEachMessage unlimited --json`, verifies report identity/completeness, and rejects any new errors, warnings, or increased occurrence counts compared to the source.

## Handling Existing Source Errors

- If the source EPUB already contains EPUBCheck errors, document them clearly as the baseline and obtain user confirmation before delivering an edited copy with inherited errors.
- New errors, new warnings, or additional occurrences of existing diagnostics must block delivery until resolved.
- If EPUBCheck is unavailable in the environment, report validation as pending rather than claiming conformance.
