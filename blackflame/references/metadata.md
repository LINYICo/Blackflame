# Metadata Management

Use this guide when inspecting, verifying, or editing bibliographic metadata and cover artwork.

## Verification Rules

- **Verify before writing.** Cross-check title, subtitle, author, translator/editor, publisher, publication date, language, series, and ISBN against the book's title/copyright page or verified catalog records. Never fabricate unverified ISBNs, publishers, dates, or copyright notices.
- **Distinguish print vs. EPUB ISBNs.** Keep the EPUB's primary package identifier (`unique-identifier`) and EPUB 2 NCX UID stable unless verified wrong. Store a print source ISBN in `dc:source` when the digital edition has no ISBN of its own.
- **Preserve edition matter.** Retain `dc:rights`, attribution, existing IDs, attributes, and custom refinements unless explicitly authorized to change them.

## Metadata Workflow by EPUB State

- **Already EPUB Latest**: Use `lxml` + `epub_safe.replace_members()` for metadata-only edits so no unrelated file members change and no extra repacking occurs.
- **EPUB 2 (default policy)**: First migrate the book to EPUB Latest (see [editing.md](editing.md)) into a temporary migrated baseline and verify migration fidelity, then apply the authorized OPF metadata edit on top of that baseline and verify the metadata diff separately. If the user explicitly asks to keep EPUB 2, edit only the OPF surgically and state that EPUB 2 was preserved.
- **`epublib` role**: Use `epublib` for high-level EPUB 3 inspection, cover/resource management, or structural reconstruction—not as a minimal metadata-only editor, because `book.write()` also reserializes `META-INF/container.xml` and omits explicit ZIP directory entries.

## Minimal Metadata-Only Edit (Recommended: `lxml` + `epub_safe.replace_members`)

Use surgical OPF replacement when only package metadata should change. Never assume the OPF is at `OPS/package.opf`—always resolve it from `META-INF/container.xml`:

```python
import sys
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
from lxml import etree

sys.path.insert(0, "/abs/path/to/blackflame/scripts")
import epub_safe

src = Path("source.epub")
out = Path("edited-metadata.epub")

with src.open("rb") as stream, ZipFile(stream) as zf:
    epub_safe.check_zip(zf, stream)
    container = epub_safe.parse_xml(zf.read(epub_safe.CONTAINER))
    opf_member = container.xpath(
        "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
        namespaces={"c": "urn:oasis:names:tc:opendocument:xmlns:container"},
    )[0]
    opf_tree = epub_safe.parse_xml(zf.read(opf_member))

dc_ns = "http://purl.org/dc/elements/1.1/"
opf_root = opf_tree.getroot()
title_el = opf_root.find(f".//{{{dc_ns}}}title")
if title_el is not None:
    title_el.text = "Verified Title"

# For EPUB 3 packages, refresh the unrefined dcterms:modified UTC timestamp.
if opf_root.get("version", "").startswith("3"):
    for meta in opf_root.findall(f".//{{{epub_safe.OPF}}}meta[@property='dcterms:modified']"):
        if not meta.get("refines"):
            meta.text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            break

new_opf = etree.tostring(opf_tree, xml_declaration=True, encoding="utf-8")
epub_safe.replace_members(src, out, {opf_member: new_opf})
epub_safe.compare_epubs(
    src,
    out,
    expected_changed={opf_member},
    expected_added=set(),
    expected_removed=set(),
    preserve_spine=True,
    preserve_text=True,
)
```

## High-Level EPUB 3 Inspection & Structural Metadata (`epublib`)

Use `epublib` for quick EPUB 3 metadata inspection or when also updating covers, manifest entries, or navigation:

```python
from epublib import EPUB

with EPUB("source.epub", generator_tag=False) as book:
    print(book.metadata.title, book.metadata.language, book.metadata.identifier)
    book.metadata.title = "Verified Title"
    book.write("edited.epub")
```

- Always write to a distinct output path (never overwrite `source.epub`).
- Note that `epublib.EPUB.write()` also reserializes `META-INF/container.xml` and omits empty ZIP directory entries. When strict OPF-only minimal diff is required, use the `lxml` + `epub_safe.replace_members()` workflow above.

## Metadata-Only vs. Cover Replacement

- **Metadata-only edit**: Only the resolved OPF package document should change. Verify with `epub_safe.compare_epubs(src, out, expected_changed={opf_member}, expected_added=set(), expected_removed=set(), preserve_spine=True, preserve_text=True)` and confirm unrelated metadata (`dc:creator`, `dc:identifier`, `dc:rights`, refinements) remained intact.
- **Cover replacement**: Legitimately modifies multiple resources (the cover image file, OPF manifest/metadata `properties="cover-image"` in EPUB 3 or `<meta name="cover" content="..."/>` in EPUB 2, and possibly a cover XHTML wrapper). Match the cover to the exact ISBN/edition, prefer genuine high-resolution RGB JPEG or PNG over upscaled images, probe dimensions with `epub_safe.image_dimensions()` (Apple Books 5.6M pixel limit), and verify reading text and spine order remain unchanged via `compare_epubs(..., expected_added=..., expected_removed=..., expected_changed=..., preserve_spine=True, preserve_text=True)`.
