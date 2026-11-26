# Format Conversion

Use this guide for direct e-book format conversion via the installed `ebook-convert` CLI (PyPI `ebook-convert`, standalone Qt-free Calibre conversion pipeline—do not assume Calibre GUI tools, `calibredb`, or Qt PDF plugins exist).

## Direct Invocation & Default EPUB Output

Per [SKILL.md](../SKILL.md), conversions targeting EPUB default to **EPUB Latest** (never silently EPUB 2), while non-EPUB targets (DOCX, TXT, MOBI, AZW3, etc.) output directly.

1. Use the client sandbox to restrict network and file access when converting untrusted inputs. Inspect referenced HTML/CSS resources without fetching them. If you cannot enforce isolation for untrusted input, stop before invoking the converter.
2. Check supported flags for the format pair first (`-h`), then invoke directly from the skill environment. Run the following commands from a private staging directory as described in [Candidate Files and Delivery](validation.md#candidate-files-and-delivery), with source paths pointing to the approved inputs:

```sh
uv run --project /abs/path/to/blackflame --no-sync ebook-convert input.ext output.ext -h

# Convert to EPUB Latest (currently pass --epub-version 3; verify actual OPF version afterward)
uv run --project /abs/path/to/blackflame --no-sync ebook-convert /abs/path/to/source.docx candidate.epub --epub-version 3

# Convert TXT/Markdown/HTML to EPUB with verified metadata (never guess from first line or fabricate fields)
uv run --project /abs/path/to/blackflame --no-sync ebook-convert /abs/path/to/source.txt candidate.epub \
  --epub-version 3 --title "Verified Title" --authors "Verified Author" --language zh

# Convert EPUB to TXT or DOCX
uv run --project /abs/path/to/blackflame --no-sync ebook-convert /abs/path/to/source.epub candidate.txt
```

3. **Preserve verified metadata & language precision.** Inspect source metadata first and reuse reliable values. For `TXT`, Markdown, or bare HTML inputs, pass verified `--title`, `--authors`, and `--language` so `ebook-convert` does not guess titles from body lines (such as `THE CONTENTS` or `Section 1`); leave unverified fields unknown and never guess regions or convert between Simplified and Traditional Chinese. Because `ebook-convert` may normalize tags (e.g., `zh-CN` → `zh`), check the output `dc:language` afterward and restore verified tags (`zh-Hans`, `zh-Hant`, `zh-CN`, `zh-TW`, `zh-HK`, etc.) via `lxml` + `epub_safe.replace_members()` while updating `dcterms:modified` and preserving legitimate local XHTML `lang`/`xml:lang` attributes.
4. Never treat `EPUB → TXT → EPUB` or same-converter round-trips as lossless or independent quality proof; if the original EPUB is available, restore verified metadata from it and note TXT's inherent loss of images, styling, TOC, and footnote semantics.

## Format-Appropriate Verification & Post-Conversion Fixes

A `0` exit code alone never proves conversion succeeded. Verify according to what the source and target formats support:

- **EPUB outputs only**: Confirm actual OPF `version` matches **EPUB Latest**, confirm EPUBCheck supports the target standard, verify body text, chapters, TOC, images, and key metadata, and run `epub_safe.run_epubcheck()` using a fresh temporary report path ([validation.md](validation.md)).
  - **Targeted post-conversion fixes**: Converters (especially `AZW3`/`MOBI → EPUB 3`) can exit `0` while leaving fixable EPUBCheck errors—for example, stripping `epub:` prefixes into invalid bare `type="..."` attributes (`RSC-005`) or dropping `<html epub:prefix="z3998: ...">` declarations (`OPF-028`). Inspect the EPUBCheck JSON report and fix only flagged elements with `lxml` + `epub_safe.replace_members()`. Restore an invalid bare `type` to `epub:type` only when its original semantic intent is confirmed; never globally strip or rewrite legitimate HTML `type` attributes (`<link>`, `<script>`, `<style>`, `<ol>`, `<input>`, etc.), and treat sample-specific fixes as diagnostic patterns rather than blanket rules for every book. Update `dcterms:modified`, re-run EPUBCheck, and never report an EPUB with unresolved errors as fully conformant.
- **Non-EPUB outputs (DOCX, MOBI, AZW3, TXT)**: File existence, non-empty size, and magic headers are only basic checks—inspect actual body text, headings, punctuation, CJK survival, images, and supported structure where possible, explicitly state any unverified aspects or lossy TXT limitations, and never run EPUBCheck on non-EPUB inputs or outputs.
