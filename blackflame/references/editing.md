# Content & Structural Editing

Use this guide for proofreading, XHTML/CSS edits, promotional content removal, chapters, TOC, images, footnotes, EPUB 2 → EPUB 3 migration, and Apple Books optimization.

## Minimal Replacement vs. Broader Reconstruction

- **Minimal surgical replacement (`lxml` + `epub_safe.replace_members`)**: Use for targeted copyediting, CSS adjustments, or single-chapter fixes. Untouched chapters, images, fonts, and binary resources remain byte-identical.
- **Broader EPUB 3 reconstruction (`epublib`)**: Use when adding, removing, or renaming resources, regenerating TOC/landmarks, or restructuring the manifest and spine. Always write to a new output file and verify exact added/removed/changed members with `epub_safe.compare_epubs()`.

## Targeted Copyediting Checklist

Before writing any text edit:

1. Inspect the original passage and surrounding XML context (`BeautifulSoup(raw, "xml")` for querying; `epub_safe.parse_xml()` for strict verification).
2. Confirm the exact expected match count so a replacement cannot hit unintended occurrences.
3. For paragraphs containing inline markup (`<em>`, `<span>`, `<a>`, footnote links), modify only the target leaf text node rather than overwriting the parent element's `.string`.
4. **Verify the exact in-chapter text and structural diff.** Member-level SHA-256 verification (`compare_epubs(..., expected_changed={chapter})`) proves untouched files did not change, **not** that only the authorized text changed inside the modified chapter. Always inspect the actual diff of the edited XHTML to confirm XML declarations, namespaces, DOCTYPE, comments, processing instructions, footnotes, attribution, and copyright notices were preserved.
5. Confirm all unrelated chapters and spine order remain unchanged (`epub_safe.compare_epubs(..., expected_changed={...}, preserve_spine=True)`).

When removing promotional inserts, check whether promotional copy shares a paragraph with book content (edit only the promotional span) and confirm no remaining links or manifest entries reference removed assets.

## Images, CSS & Footnotes

- Verify `img/@src`, SVG `image/@href`, CSS `url(...)`, and `@import` targets exist in the archive and match manifest `media-type`.
- Probe embedded cover and illustration dimensions with `epub_safe.image_dimensions()` against Apple Books' 5.6 million pixel limit.
- Keep footnotes readable as standard internal links; for Apple Books pop-ups in EPUB 3, pair `epub:type="noteref"` on the link with `epub:type="footnote"` on the target `aside` and preserve a working return link.

## EPUB 2 to EPUB 3 Migration

Migrating EPUB 2 to EPUB 3 is more than bumping `version="3.0"` and adding a TOC file. Check all required specification changes:

- **Package document (OPF)**: Set `version="3.0"`, add UTC `<meta property="dcterms:modified">`, convert obsolete EPUB 2 OPF attributes (`opf:role`, `opf:file-as`, `opf:scheme`) to EPUB 3 `<meta refines="#...">` refinements, declare `properties="nav"` and `properties="cover-image"` on the respective manifest items, and keep the primary identifier intact.
- **Navigation Document**: Create an XHTML5 Navigation Document with `<nav epub:type="toc">` preserving the full NCX hierarchy and fragment targets, plus `<nav epub:type="landmarks">` (`cover`, `bodymatter`) for Apple Books. Retain the NCX only if backward compatibility with EPUB 2 readers is requested (and keep its UID and targets synchronized).
- **Content Documents**: Update XHTML 1.1 documents to valid XHTML5 (`<!DOCTYPE html>`, UTF-8, `xmlns="http://www.w3.org/1999/xhtml"`, `xmlns:epub="http://www.idpf.org/2007/ops"`), replace deprecated presentational attributes (`align`, `border`, `<center>`, `<font>`) with CSS, convert named HTML4 entities (`&nbsp;`, `&mdash;`) to numeric character references or UTF-8 characters (XHTML5 does not load external DTDs), and validate the result with EPUBCheck.
