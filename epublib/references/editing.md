# Editing EPUB publications

Run commands from the skill directory. Store the inventory, replacement files, plan, and reports in the task workspace.

## Inspect the source

```bash
python3 scripts/epub_patch.py inspect book.epub > inventory.json
```

The inventory reports the source SHA-256 and lists each OPF package, its manifest, reading order, and NCX identifier. Read navigation targets from the manifest's EPUB 3 navigation document or the EPUB 2 NCX. Resolve relative links from the referring member. Check the decoded paths and fragment identifiers against the original archive.

## Prepare replacements

- **Metadata.** Use the OPF and Dublin Core namespaces to identify existing fields. When multiple elements represent the same field, use the current value, ID, role, or refinement to select the intended element. Preserve identifiers, attributes, order, and custom metadata. When updating the EPUB 3 `dcterms:modified` value, use a UTC timestamp and record the change.
- **XHTML.** Follow the spine to locate the requested passage. Review the context and verify that each proposed edit has a unique match. If promotional text shares a paragraph with regular content, edit only the identified text. Before removing an element, check its ID, incoming links, footnote references, reused resources, and trailing `tail` text.
- **Diff review.** Preserve the XML declaration, encoding, doctype, comments, processing instructions, and meaningful whitespace. Review all changes to the edited member. Pay particular attention to headings, anchors, styles, SVG, MathML, ruby, and links from navigation, other chapters, or media overlays. Text and layout changes require review even when EPUBCheck succeeds.

Create `plan.json` using the `source_sha256` from the inventory. Map each changed ZIP member to its replacement file. Use a path relative to the plan or an absolute path.

```json
{
  "source_sha256": "<SHA-256 from inventory.json>",
  "replacements": {
    "OPS/package.opf": "replacements/package.opf",
    "OPS/text/chapter.xhtml": "replacements/chapter.xhtml"
  }
}
```

## Apply and validate

```bash
python3 scripts/epub_patch.py apply book.epub edited.epub \
  --plan plan.json --report-dir reports
```

Use a new output filename and report directory. The command supports a single OPF package and checks the edit scope before rebuilding. For XHTML, it checks the document structure outside the body contents and verifies that existing anchor values remain present. It preserves ZIP member names, order, and compression methods, and compares the SHA-256 of every member's uncompressed contents. It stops on signature, rights, or encryption descriptors. Font obfuscation can also produce an encryption descriptor, so record the descriptor without inferring DRM.

By default, errors in the source EPUB block application. Use `--allow-existing-errors` only after the user accepts the documented baseline. The command requests all EPUBCheck diagnostic locations and uses the same validator version for both runs. It compares fatal errors, errors, and warnings by diagnostic ID, message, member path, and context, allowing line and column shifts. New occurrences block output. Review the full reports when a diagnostic in an edited document could have moved or changed meaning. If EPUBCheck is unavailable, report the pending validation and retain the prepared replacements.

Deliver the resulting EPUB and `changes.json`, along with the EPUBCheck reports where relevant. For layout-sensitive edits, spot-check the changed chapter and its navigation links in a reader and report the result.
