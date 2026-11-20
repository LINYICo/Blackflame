# EPUB 3 migration and Apple Books

Use this workflow when an edition needs EPUB 3 navigation, semantic notes, or reader compatibility fixes. Keep the source and build a separate candidate. For flowing books, preserve reflow and allow the reader to control type size.

## Migrate the package

- Set the OPF package version to `3.0` and add `dcterms:modified` in UTC. Preserve the primary identifier, edition metadata, reading order, and page progression. Convert EPUB 2 metadata attributes to EPUB 3 refinements where needed.
- Build a navigation document with a nested `epub:type="toc"` list. Preserve labels, hierarchy, and targets from the NCX. Declare the navigation document with `properties="nav"` in the manifest.
- Check that every manifest and navigation target resolves from its referring document. When changing filenames, update the package, navigation, and all incoming links together.
- For Apple Books, use landmarks to identify the cover and the first chapter with the `cover` and `bodymatter` types. Keep notes readable through ordinary internal links. For pop-ups, mark each linked reference with `epub:type="noteref"` and the corresponding `aside` with `epub:type="footnote"`. Preserve note text and return links. [EPUB 3.3](https://www.w3.org/TR/epub-33/) · [Apple Books navigation](https://help.apple.com/itc/booksassetguide/en.lproj/itc0f175a5b9.html) · [Apple Books Asset Guide](https://help.apple.com/itc/booksassetguide/en.lproj/static.html)

## Replace an embedded cover

Confirm the title, edition, and source of the image. Use a genuine high-resolution RGB JPEG or PNG and preserve its aspect ratio. Mark the image manifest item `properties="cover-image"` and update the cover page's image reference when its path changes. Apple's documented limit for images embedded in the publication is 5.6 million pixels. [Apple Books cover requirements](https://help.apple.com/itc/booksassetguide/en.lproj/itc1bda991ba.html)

## Verify the candidate

```bash
python3 scripts/epub_patch.py verify original.epub candidate.epub \
  --preserve-spine --report-dir reports
```

The spine check compares ordered, resolved ZIP member paths, linear flags, and page progression. Use it when those must stay the same. If an approved repair renames spine members, verify without the flag and compare the original and candidate orders using the planned filename mapping.

Compare navigation entries, note text and targets, and body text. Spot-check cover proportions, the opening location, note pop-ups, and text reflow in the target reader when available. Report conformance and reader testing separately.
