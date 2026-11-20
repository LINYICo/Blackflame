# Tool reference

The bundled command uses the Python standard library and `lxml`. Applying edits also requires an EPUBCheck executable. The remaining libraries support optional inspection and discovery.

```bash
python3 --version
python3 -m pip show lxml
epubcheck --version
```

## Package inspection and validation

- **Python `zipfile` and `hashlib`** provide access to the original ZIP members and SHA-256 digests. Digests compare uncompressed member contents. ZIP serialization can change compressed bytes and archive-level metadata. [zipfile](https://docs.python.org/3/library/zipfile.html) · [hashlib](https://docs.python.org/3/library/hashlib.html)
- **`lxml.etree`** parses package and content documents with strict XML settings and namespace-aware XPath. Disable network access, DTD loading, and entity resolution. Preserve whitespace, comments, processing instructions, and CDATA when preparing replacements. [Parser options](https://lxml.de/parsing.html) · [XPath](https://lxml.de/xpathxslt.html)
- **EPUBCheck** checks EPUB conformance and produces structured JSON diagnostics. Use `--maxOfEachMessage unlimited` with `--json` for a before-and-after comparison that includes every reported occurrence. [Installation](https://www.w3.org/publishing/epubcheck/docs/installation/) · [CLI](https://www.w3.org/publishing/epubcheck/docs/cli/)

Container layout, package metadata, and font obfuscation are defined by the [EPUB specification](https://www.w3.org/TR/epub/).

## Optional reading and discovery

- **EPUBLib (`epublib`)** exposes EPUB 3 package metadata, manifest, spine, and navigation. Open it through `EPUB(path, generator_tag=False)` for inspection. The documents collection can include the navigation document. For EPUB 2 or unsupported packages, read the original ZIP, OPF, and NCX. [API](https://epublib.readthedocs.io/en/stable/epublib.html)
- **EbookLib (`ebooklib`)** provides a separate EPUB 2 and EPUB 3 reading API through `epub.read_epub(path)`. Use the original ZIP member bytes for edits that must preserve document structure. EbookLib's writer can regenerate markup and navigation during serialization. [Tutorial](https://github.com/aerkalov/ebooklib/blob/master/docs/tutorial.rst) · [Round-trip behavior](https://docs.sourcefabric.org/projects/ebooklib/en/v0.21/faq.html)
- **Beautiful Soup 4 (`bs4`)** helps identify text, links, and repeated markup. Specify the parser explicitly and confirm any candidate against the original document parsed as strict XML. [Parser differences](https://www.crummy.com/software/BeautifulSoup/bs4/doc/#differences-between-parsers)
