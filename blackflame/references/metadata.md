# Metadata Management

Use this guide when inspecting, verifying, or editing bibliographic metadata and cover artwork.

## Verification Rules

- **Verify before writing.** Cross-check title, subtitle, author, translator/editor, publisher, publication date, language, series, and ISBN against the book's title/copyright page or verified catalog records. Never fabricate unverified ISBNs, publishers, dates, or copyright notices.
- **Distinguish print vs. EPUB ISBNs.** Keep the EPUB's primary package identifier (`unique-identifier`) and EPUB 2 NCX UID stable unless verified wrong. Store a print source ISBN in `dc:source` when the digital edition has no ISBN of its own.
- **Preserve edition matter.** Retain `dc:rights`, attribution, existing IDs, attributes, and custom refinements unless explicitly authorized to change them.

## Tested Examples

### Read & Edit EPUB 3 Metadata with `epublib`

```python
from epublib import EPUB

with EPUB("source.epub", generator_tag=False) as book:
    print(book.metadata.title, book.metadata.language, book.metadata.identifier)
    book.metadata.title = "Verified Title"
    book.write("edited.epub")
```

- Always write to a distinct output path (never overwrite `source.epub`).
- If `book.write()` would reserialize untouched chapters or manifest entries beyond the authorized scope, edit only the OPF XML with `lxml` and apply it via `epub_safe.replace_members(source, output, {opf_member: new_opf_bytes})`.

### Surgical OPF Edit (EPUB 2 or Minimal Diff) with `lxml`

```python
from pathlib import Path
from zipfile import ZipFile
import epub_safe

src = Path("source.epub")
with ZipFile(src) as zf:
    opf_tree = epub_safe.parse_xml(zf.read("OPS/package.opf"))
title_el = opf_tree.find(".//{http://purl.org/dc/elements/1.1/}title")
title_el.text = "Verified Title"
epub_safe.replace_members(src, Path("edited.epub"), {"OPS/package.opf": ...})
```

- For EPUB 3 revisions, update the unrefined `meta[@property='dcterms:modified']` timestamp in UTC (`YYYY-MM-DDTHH:MM:SSZ`).

## Metadata-Only vs. Cover Replacement

- **Metadata-only edit**: Only the OPF package document should change. Confirm with `epub_safe.compare_epubs(source, output, expected_changed={opf_member}, preserve_spine=True, preserve_text=True)`.
- **Cover replacement**: Legitimately modifies multiple resources (the cover image file, OPF manifest/metadata, and possibly a cover XHTML wrapper). Match the cover to the exact ISBN/edition, prefer genuine high-resolution RGB JPEG or PNG over upscaled images, probe dimensions with `epub_safe.image_dimensions()` (Apple Books 5.6M pixel limit), and verify reading text and spine order remain unchanged via `compare_epubs(..., expected_added=..., expected_removed=..., expected_changed=..., preserve_spine=True, preserve_text=True)`.
