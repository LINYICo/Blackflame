# Editing EPUB publications

Run commands from the skill directory. Store the inventory, replacement files, plan, and reports in the task workspace.

## Inspect the source

```bash
python3 scripts/skill.py run inspect book.epub > inventory.json
```

The inventory reports the source SHA-256, package metadata, primary identifier, cover and navigation members, and resolved spine entries. Read navigation targets from the manifest's EPUB 3 navigation document or the EPUB 2 NCX. Resolve relative links from the referring member. Check the decoded paths and fragment identifiers against the original archive.

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
  },
  "text_edits": {
    "OPS/text/chapter.xhtml": [
      {"old": "teh harbour", "new": "the harbour", "count": 1}
    ]
  }
}
```

For copyedits, include every changed XHTML member in `text_edits`. Each substitution applies in order to individual body text nodes, including text following inline elements. The count must match exactly. The CLI compares the resulting document with the proposed replacement, catching unrelated deletions and markup changes. Use a longer phrase when the same word occurs in several places. Existing plans without this field retain the broader body-edit checks described below.

For EPUB 3, include the package's unrefined `dcterms:modified` in the reviewed replacements and set it to the revision time in UTC. The change report flags EPUB 3 publications for timestamp review. [EPUB 3 last modified date](https://www.w3.org/TR/epub-33/#last-modified-date)

## Apply and validate

```bash
python3 scripts/skill.py run apply book.epub edited.epub \
  --plan plan.json --report-dir reports
```

Use a new output filename and report directory. The command supports a single OPF package and checks the edit scope before rebuilding. For XHTML, it checks the document structure outside the body contents and verifies that existing anchor values remain present. It preserves ZIP member names, order, and compression methods, and compares the SHA-256 of every member's uncompressed contents. It stops on signature, rights, or encryption descriptors. Font obfuscation can also produce an encryption descriptor, so record the descriptor without inferring DRM.

By default, errors in the source EPUB block application. Use `--allow-existing-errors` only after the user accepts the documented baseline. The command requests all EPUBCheck diagnostic locations and uses the same validator version for both runs. It compares fatal errors, errors, and warnings by diagnostic ID, message, member path, and context, allowing line and column shifts. New occurrences block output. Review the full reports when a diagnostic in an edited document could have moved or changed meaning. If EPUBCheck is unavailable, report the pending validation and retain the prepared replacements.

Deliver the resulting EPUB and `changes.json`, along with the EPUBCheck reports where relevant. For layout-sensitive edits, spot-check the changed chapter and its navigation links in a reader and report the result.

## Verify a structural repair

For an authorized repair outside the replacement plan's scope, rebuild a separate candidate from the original ZIP members. This covers adding missing package metadata, editing CSS, renaming chapter files, or removing a confirmed promotional page and its unused assets. Keep the EPUB version and original reading order unless the task requires a change. Run one baseline and candidate validation pair with `verify`.

```bash
python3 scripts/skill.py run verify book.epub repaired.epub \
  --expected-changes scope.json --report-dir reports
```

Write `scope.json` before verification. List exact ZIP member names in each category, using empty arrays where appropriate. A missing expected change also fails verification. Omit the flag for an inventory-only comparison with EPUBCheck.

```json
{
  "source_sha256": "<SHA-256 from inventory.json>",
  "added": [],
  "removed": [],
  "changed": ["OPS/package.opf", "OPS/text/chapter.xhtml"]
}
```

- **Metadata and navigation.** Cross-check edition details with the publisher and the book's imprint. Preserve the package's primary identifier unless there is evidence that it is wrong. Keep it synchronized with the NCX UID in EPUB 2. Update package, navigation, and content references together when renaming a member. Preserve fragment targets and verify reading order.
- **Exporter markup.** Inspect proprietary attributes before cleanup. If an empty marker contains footnote text, preserve that text in a linked note with a return link. Compare the original and edited chapter text after excluding generated markers and note blocks. Remove remote font declarations if local reader fonts can serve the same role.
- **Advertising and layout.** Remove promotional assets only after checking all remaining references. Preserve edition matter such as the cover, copyright page, and endorsements about the book itself unless they are in scope. Check typography on narrow and wide viewports, including headings, inline formulas, and note links.

`verify` checks ZIP member integrity, compares EPUBCheck diagnostics, and reports added, removed, and byte-changed members in `comparison.json`. A rename appears as one removal and one addition. Add `--preserve-spine` to require the same ordered member paths, linear flags, and page progression. Review the comparison against the approved scope and confirm link targets independently. The command accepts a clean candidate from a source with existing errors. An unresolved baseline requires `--allow-existing-errors` and explicit acceptance. New errors or warnings always fail verification.
