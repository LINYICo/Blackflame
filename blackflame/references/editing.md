# Content & Structural Editing

Use this guide for proofreading, XHTML/CSS edits, promotional content removal, chapters, TOC, images, footnotes, EPUB 2 → EPUB Latest migration, and Apple Books optimization.

## Surgical Replacement vs. Structural Reconstruction

- **Targeted edits (`lxml` + `epub_safe.replace_members`)**: Use for copyediting, CSS tweaks, or single-chapter fixes so untouched chapters and binary assets remain byte-identical.
- **Structural reconstruction (`epublib`)**: Use when adding/removing/renaming resources or rebuilding navigation/spine. Write to a new file and verify exact diffs with `epub_safe.compare_epubs()`.

## Targeted Copyediting Checklist

1. Inspect the passage and surrounding XML (`BeautifulSoup(raw, "xml")` for querying; `epub_safe.parse_xml()` for strict verification).
2. Confirm exact match counts before replacing.
3. On paragraphs with inline markup (`<em>`, `<span>`, `<strong>`, `<a>`, footnote links), edit only the target leaf text node (`NavigableString` or `lxml` `.text`/`.tail`)—never overwrite `.string` on a mixed-content element.
4. **Verify the actual in-chapter text and structural diff.** Member-level SHA-256 checks prove untouched files did not change, **not** that only authorized text changed inside the edited chapter. Confirm XML declarations, namespaces, DOCTYPE, comments, footnotes, attribution, and copyright notices remain intact.
5. Verify unrelated chapters and spine order with `compare_epubs(..., expected_changed={...}, preserve_spine=True)`.

When removing promotional inserts, edit only the promotional span if it shares a paragraph with book text, and remove dangling links or manifest entries.

## Images, CSS & Footnotes

- Verify `img/@src`, SVG `image/@href`, CSS `url(...)`, and `@import` targets exist and match manifest `media-type`.
- Check image dimensions with `epub_safe.image_dimensions()` against Apple Books' 5.6M pixel limit.
- Keep footnotes as standard internal links; for Apple Books pop-ups in EPUB 3, pair `epub:type="noteref"` on the link with `epub:type="footnote"` on the target `aside` and keep a return link.

## EPUB 2 to EPUB Latest Migration

Prefer fidelity-preserving migration with `lxml`, `epublib`, and surgical ZIP updates rather than blindly rebuilding via `ebook-convert` (use full conversion only when structural reconstruction truly requires it or the user requests it, and verify any resulting text, TOC, style, or asset changes). Preserve original identifiers, ISBNs, authors, publisher, dates, and copyright notices:

- **OPF**: Set `version="3.0"` (never `3.3` or `Latest`), add UTC `<meta property="dcterms:modified">`, convert obsolete EPUB 2 attributes (`opf:role`, `opf:file-as`, `opf:scheme`) to `<meta refines="#...">` refinements, preserve `unique-identifier`, `page-progression-direction`, accessibility/fixed-layout metadata, and declare `properties="nav"` and `properties="cover-image"` on manifest items.
- **Navigation & NCX**: Build an XHTML5 Navigation Document (`<nav epub:type="toc">`) preserving the full NCX hierarchy and fragment targets, plus `<nav epub:type="landmarks">` (`cover`, `bodymatter`) for Apple Books. Retain the valid NCX unless removal is requested (keeping UID and links synchronized).
- **Content & assets**: Upgrade XHTML 1.1 chapters to valid XHTML5 (`<!DOCTYPE html>`, UTF-8, `xmlns="http://www.w3.org/1999/xhtml"`, `xmlns:epub="http://www.idpf.org/2007/ops"`), replace deprecated presentational markup (`align`, `border`, `<center>`, `<font>`) with CSS, convert HTML4 named entities (`&nbsp;`, `&mdash;`) to UTF-8 or numeric references, and verify CSS, images, cover XHTML, embedded fonts, SVG, MathML, footnotes, internal links, and media overlays before validating with EPUBCheck.
