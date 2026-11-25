# Metadata Management

Use this guide for inspecting, verifying, or editing bibliographic metadata and cover artwork. See [SKILL.md](../SKILL.md) for EPUB Latest policy and [validation.md](validation.md) for three-stage verification.

## Verification Rules

- **Verify before writing.** Cross-check title, subtitle, author, translator/editor, publisher, publication date, language, series, and ISBN against the title/copyright page or verified catalog records. Never fabricate unverified fields.
- **Distinguish print vs. EPUB ISBNs.** Keep the primary `unique-identifier` and EPUB 2 NCX UID stable unless verified wrong; store a print ISBN in `dc:source` when the digital edition has none.
- **Preserve edition matter.** Retain original publication date (`dc:date`), `dc:rights`, attribution, IDs, attributes, and refinements unless authorized to change them. For any actual EPUB 3 modification, update only the single unrefined `<meta property="dcterms:modified">` in UTC (`YYYY-MM-DDThh:mm:ssZ`).

## Read-Only Inspection (`epublib`)

```python
from epublib import EPUB

with EPUB("source.epub", generator_tag=False) as book:
    print(book.metadata.title, book.metadata.language, book.metadata.identifier)
```

For structural EPUB 3 work (covers, manifest, navigation), `epublib` may also write to a distinct output path; note that `book.write()` reserializes `META-INF/container.xml`.

## Minimal Metadata-Only Edit (`lxml` + `epub_safe.replace_members`)

- **Already EPUB Latest**: Edit only the OPF with `lxml` + `epub_safe.replace_members()`.
- **EPUB 2**: Migrate to EPUB Latest first ([editing.md](editing.md)), verify the migrated baseline, then apply this OPF edit ([validation.md](validation.md)).

```python
import sys
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
from lxml import etree

sys.path.insert(0, "/abs/path/to/blackflame/scripts")
import epub_safe

src, out = Path("source.epub"), Path("edited-metadata.epub")
dc_ns = "http://purl.org/dc/elements/1.1/"

with src.open("rb") as stream, ZipFile(stream) as zf:
    names = epub_safe.check_zip(zf, stream)
    if prot := epub_safe.protection_entries(names):
        raise ValueError(f"Inspect protection before editing: {prot}")
    container = epub_safe.parse_xml(zf.read(epub_safe.CONTAINER))
    rootfiles = container.xpath(
        "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
        namespaces={"c": "urn:oasis:names:tc:opendocument:xmlns:container"},
    )
    if len(rootfiles) != 1:
        raise ValueError(f"Expected 1 OPF package; handle multi-package scope explicitly: {rootfiles}")
    opf_member = rootfiles[0]
    opf_tree = epub_safe.parse_xml(zf.read(opf_member))

opf_root = opf_tree.getroot()
meta_el = opf_root.find(f"{{{epub_safe.OPF}}}metadata")
if meta_el is None:
    raise ValueError("Missing <metadata> element in OPF")

# Update existing dc:title or explicitly create one if absent (never silently claim success).
title_el = meta_el.find(f"{{{dc_ns}}}title")
if title_el is None:
    title_el = etree.SubElement(meta_el, f"{{{dc_ns}}}title")
title_el.text = "Verified Title"

# For EPUB 3 packages, update existing unrefined dcterms:modified or add it if missing.
if opf_root.get("version", "").startswith("3"):
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    modified = [
        m for m in meta_el.findall(f"{{{epub_safe.OPF}}}meta[@property='dcterms:modified']") if not m.get("refines")
    ]
    if modified:
        modified[0].text = now_utc
    else:
        etree.SubElement(meta_el, f"{{{epub_safe.OPF}}}meta", property="dcterms:modified").text = now_utc

epub_safe.replace_members(src, out, {opf_member: etree.tostring(opf_tree, xml_declaration=True, encoding="utf-8")})
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

## Cover Replacement

Cover replacement legitimately updates multiple files (image asset, OPF `properties="cover-image"` in EPUB 3 or `<meta name="cover" content="..."/>` in EPUB 2, and any cover XHTML). Match the cover to the exact edition/ISBN, prefer genuine high-resolution RGB JPEG/PNG, check `epub_safe.image_dimensions()` against Apple Books' 5.6M pixel limit, and verify spine and reading text via `compare_epubs()`.
