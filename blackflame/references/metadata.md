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

For structural EPUB 3 work (covers, manifest, navigation), `epublib` can write a temporary candidate via `book.write()` before [verification and delivery](validation.md#candidate-files-and-delivery). This call reserializes `META-INF/container.xml`.

## Minimal Metadata-Only Edit (`lxml` + `epub_safe.replace_members`)

- Inspect the intended field first. If its verified value is already present, stop without creating an output or migrating the source.
- For an actual EPUB 2 edit, migrate to EPUB Latest per [editing.md](editing.md) and verify the migrated baseline before editing the OPF. The example below starts from an EPUB 3 package with a single title. When a package has several titles, identify the intended one using its refinements before editing.
- Pass a staged path as `out`. Before delivering that file, complete the EPUBCheck and publication steps in [validation.md](validation.md).

```python
import sys
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
from lxml import etree

sys.path.insert(0, "/abs/path/to/blackflame/scripts")
import epub_safe


def edit_title(src: Path, out: Path, verified_title: str) -> bool:
    with src.open("rb") as stream, ZipFile(stream) as zf:
        names = epub_safe.check_zip(zf, stream)
        if protected := epub_safe.protection_entries(names):
            raise ValueError(f"Inspect protection before editing: {protected}")
        container = epub_safe.parse_xml(epub_safe.read_xml_member(zf, epub_safe.CONTAINER))
        rootfiles = container.xpath(
            "/c:container/c:rootfiles/c:rootfile[@media-type='application/oebps-package+xml']/@full-path",
            namespaces={"c": "urn:oasis:names:tc:opendocument:xmlns:container"},
        )
        if len(rootfiles) != 1:
            raise ValueError(f"Expected one OPF package; verify the intended package: {rootfiles}")
        opf_member = rootfiles[0]
        opf_tree = epub_safe.parse_xml(epub_safe.read_xml_member(zf, opf_member))

    opf_root = opf_tree.getroot()
    if opf_root.get("version") != "3.0":
        raise ValueError("Confirm EPUB 3 before applying this edit")
    meta = opf_root.find(f"{{{epub_safe.OPF}}}metadata")
    if meta is None:
        raise ValueError("Missing <metadata> element in OPF")

    title_tag = "{http://purl.org/dc/elements/1.1/}title"
    titles = meta.findall(title_tag)
    if len(titles) > 1:
        raise ValueError("Multiple dc:title entries; use OPF refinements to identify the intended title")
    title = titles[0] if titles else None
    if title is not None and title.text == verified_title:
        return False

    modified_tag = f"{{{epub_safe.OPF}}}meta"
    modified = [m for m in meta.findall(f"{modified_tag}[@property='dcterms:modified']") if "refines" not in m.attrib]
    if len(modified) > 1:
        raise ValueError("Multiple unrefined dcterms:modified entries; resolve with user authorization")
    if title is None:
        title = etree.SubElement(meta, title_tag)
    title.text = verified_title
    timestamp = modified[0] if modified else etree.SubElement(meta, modified_tag, property="dcterms:modified")
    timestamp.text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    epub_safe.replace_members(src, out, {opf_member: etree.tostring(opf_tree, xml_declaration=True, encoding="utf-8")})
    epub_safe.compare_epubs(src, out, expected_changed={opf_member}, preserve_spine=True)
    return True


if __name__ == "__main__":
    changed = edit_title(Path("source.epub"), Path("edited-metadata.epub"), "Verified Title")
    print("Metadata updated" if changed else "The verified title is already present")
```

## Cover Replacement

Cover replacement legitimately updates multiple files (image asset, OPF `properties="cover-image"` in EPUB 3 or `<meta name="cover" content="..."/>` in EPUB 2, and any cover XHTML). Match the cover to the exact edition/ISBN, prefer genuine high-resolution RGB JPEG/PNG, and check `epub_safe.image_dimensions()` against Apple Books' 5.6M pixel limit:

- **Prefer `lxml` + `epub_safe.replace_members()`** when replacing an existing cover asset so untouched chapters and resources remain byte-identical.
- **Guard against duplicate `cover-image` declarations.** When adding a new cover with `epublib` (`book.resources.add(img, is_cover=True)`), `epublib` may leave the `cover-image` property on the previous cover item—inspect the OPF manifest, clear any stale `cover-image` property so each OPF package has **at most one** valid `cover-image` declaration, and keep the old image file if chapters or other resources still reference it.
- Verify cover XHTML references, manifest `media-type`, updated UTC `dcterms:modified`, spine/text fidelity via `compare_epubs()`, and final conformance via EPUBCheck.
