# Content & Structural Editing

Use this guide for proofreading, XHTML/CSS edits, ad removal, chapters, TOC, images, footnotes, EPUB 2 → EPUB 3 migration, and Apple Books optimization.

## Choosing the Right Edit Path

- **Targeted text, CSS, or single-chapter edits (minimal diff):** Edit only the affected ZIP member(s) using `lxml` (or `BeautifulSoup(..., "xml")` for querying followed by strict XML verification) and write the new EPUB via `epub_safe.replace_members()`. This guarantees all untouched chapters, fonts, images, and ZIP ordering remain byte-identical.
- **Broad EPUB 3 structural edits (renaming/adding/removing resources, regenerating TOC/landmarks, cover replacement):** Use `epublib` (`EPUB`, `book.resources`, `book.manifest`, `book.spine`, `book.nav`) and write to a separate output file, then verify with `epub_safe.compare_epubs()` and EPUBCheck.

## Proofreading & Copyediting

- Inspect context around every match before replacing; avoid blind global string replaces across XML tags or attributes.
- Preserve XML declarations, encoding, DOCTYPE, comments, processing instructions, footnotes, attribution, and copyright notices.
- When removing promotional inserts, verify whether promotional text shares a paragraph with book content (edit only the promotional span) and confirm no remaining links or manifest entries reference removed assets.
- Keep existing anchor IDs (`id`, `xml:id`, `a/@name`) intact unless explicitly updating all incoming links and TOC/NCX targets.

## Images, Covers & CSS

- Verify every `img/@src`, SVG `image/@href`, CSS `url(...)`, and `@import` resolves to an existing member inside the archive.
- Confirm manifest `media-type` matches the actual image format (JPEG, PNG, GIF, SVG) and check pixel dimensions against Apple Books' 5.6 million pixel limit (`epub_safe.image_dimensions()`).
- Remove remote font or tracking image declarations when local reader rendering suffices.

## Footnotes & Navigation

- Keep footnotes readable as ordinary internal links. For Apple Books pop-up footnotes in EPUB 3, mark the reference with `epub:type="noteref"` and the target `aside` with `epub:type="footnote"`, preserving both note text and a working return link.
- When multiple footnotes share duplicate IDs, match each reference to its note by marker text and surrounding context before assigning unique IDs.
- Keep TOC hierarchy, labels, and fragment targets synchronized when renaming or reordering chapters.

## EPUB 2 to EPUB 3 Migration & Apple Books

- Set OPF `version="3.0"` and add UTC `dcterms:modified` while preserving primary identifier, edition metadata, spine order, and page progression.
- Build an EPUB 3 Navigation Document (`properties="nav"`) with `<nav epub:type="toc">` preserving NCX hierarchy and targets.
- For Apple Books, add `<nav epub:type="landmarks">` identifying the actual `cover` document and first chapter (`bodymatter`), preserve reflowable text sizing, and spot-check cover proportions, opening location, and note pop-ups in a target reader when possible.
