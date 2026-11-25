# Format Conversion

Use this guide when converting e-books between EPUB and other formats using the installed `ebook-convert` CLI (PyPI `ebook-convert`, a standalone Qt-free packaging of the Calibre conversion pipeline).

## Scope & Limitations

- **Distinguish PyPI `ebook-convert` from full Calibre.** This skill uses the standalone PyPI `ebook-convert` package, not the full Calibre desktop suite. Do not assume GUI features, Calibre library database commands (`calibredb`), or Qt-dependent PDF rendering plugins are present.
- **Check actual installed capabilities.** Supported input/output formats and format-specific flags depend on the installed version. Inspect options for a specific format pair before running:

```sh
ebook-convert input.ext output.ext -h
```

- **Never claim unsupported formats.** Only perform conversions supported by the installed `ebook-convert` binary and report any unsupported format clearly.

## Safe Conversion Workflow

1. **Protect the source.** Always write to a new output path (never overwrite the original file).
2. **Run `ebook-convert` directly.** Invoke the CLI via the project's `uv` environment (or active PATH) with explicit input and output paths:

```sh
ebook-convert source.epub output.docx
ebook-convert source.mobi output.epub
```

3. **Check exit status and output integrity.** Confirm exit code `0`, non-empty output file, and valid target format structure.
4. **Verify content and resources.** Conversion is expected to change internal markup and ZIP layout—do not require byte-identical members. Instead, verify:
   - Key metadata (title, author, language) survived conversion.
   - Chapter count, reading order, and core body text are intact.
   - Cover and key illustrations were retained without obvious loss.
   - When the output format is EPUB, run EPUBCheck (`epub_safe.run_epubcheck()`) to verify specification conformance.
5. **Report clearly.** State the exact command/options used, any EPUBCheck diagnostics (for EPUB output), and what still requires visual spot-checking in a reader.
