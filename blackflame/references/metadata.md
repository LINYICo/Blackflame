# Metadata Management

Use this guide when inspecting, verifying, or updating bibliographic metadata and cover declarations.

## Verification Rules

- **Verify before writing.** Cross-check title, subtitle, author, translator/editor, publisher, publication date, language, series, and ISBN against the book's own title page, copyright page, or verified publisher/catalog records.
- **Never fabricate metadata.** Do not guess or infer unverified ISBNs, publishers, publication dates, or copyright statements.
- **Distinguish print vs. EPUB ISBNs.** Keep the EPUB's own primary package identifier (`unique-identifier`) and EPUB 2 NCX UID stable unless there is verified evidence they are wrong. Record a print edition's ISBN in `dc:source` when the digital edition has no ISBN of its own.
- **Preserve edition matter.** Retain copyright notices (`dc:rights`), credits, existing IDs, attributes, and custom refinements unless the user explicitly authorizes changing them.

## Tool Usage

### EPUB 3 with `epublib`

Use `epublib` directly for reading and editing EPUB 3 metadata:

```python
from epublib import EPUB

with EPUB("book.epub", generator_tag=False) as book:
    print(book.metadata.title, book.metadata.language, book.metadata.identifier)
```

- Pass `generator_tag=False` to avoid adding generator metadata during inspection or minimal edits.
- When `book.write("edited.epub")` would reserialize untouched chapters or manifest entries beyond the authorized scope, edit only the OPF XML with `lxml` and apply it via `epub_safe.replace_members(source, output, {opf_member: new_opf_bytes})`.

### EPUB 2 or Surgical OPF Edits with `lxml`

- Parse OPF with `epub_safe.parse_xml()` (`no_network=True, load_dtd=False, resolve_entities=False`).
- Use OPF (`http://www.idpf.org/2007/opf`) and Dublin Core (`http://purl.org/dc/elements/1.1/`) namespaces.
- For EPUB 3 revisions, update the unrefined `meta[@property='dcterms:modified']` timestamp in UTC (`YYYY-MM-DDTHH:MM:SSZ`).

## Cover Selection

- Match cover artwork to the exact ISBN, publisher, and edition; do not substitute a redesigned or mismatched edition cover.
- Prefer genuine high-resolution RGB JPEG or PNG over upscaled images, preserving aspect ratio.
- Check pixel dimensions with `epub_safe.image_dimensions(img_bytes)` (Apple Books limits embedded images to 5.6 million pixels).
- In EPUB 3, mark the cover image manifest item with `properties="cover-image"`; in EPUB 2, keep `<meta name="cover" content="<id>"/>` synchronized.

## Verification

- For metadata-only edits, confirm with `epub_safe.compare_epubs(source, output, expected_changed={opf_member}, preserve_spine=True, preserve_text=True)` that only the OPF changed.
- Run EPUBCheck before and after when modifying OPF structure or cover declarations.
