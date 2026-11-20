# 工具参考

## 环境

沿用当前解释器和已安装版本。检查与写入只依赖 `lxml`、Python 标准库和编辑时需要的 EPUBCheck。按任务需要检查可选库。

```bash
python3 --version
python3 -m pip show lxml epublib EbookLib beautifulsoup4
epubcheck --version
```

## 选择工具

- **Python `zipfile` 与 `hashlib`**读取原始容器、定位成员并比较解压内容的 SHA-256。ZIP 重打包会重新编码归档，保存证据以成员内容为准。[zipfile](https://docs.python.org/3/library/zipfile.html) · [hashlib](https://docs.python.org/3/library/hashlib.html)
- **`lxml.etree`**严格解析原始 XML，以命名空间感知的 XPath 定位节点。在各次解析显式使用 `no_network=True`、`load_dtd=False`、`resolve_entities=False`、`recover=False` 和 `huge_tree=False`。保留注释、处理指令、空白和 CDATA。[lxml 解析选项](https://lxml.de/parsing.html) · [XPath](https://lxml.de/xpathxslt.html)
- **Beautiful Soup 4（`bs4`）**用于扫描推广语、链接、图片和重复模板。扫描明确指定解析器，例如 `BeautifulSoup(data, "xml")`。容错解析产生的节点只用于预览，提交补丁前在原始字节上用严格 XML 验证位置。[解析器差异](https://www.crummy.com/software/BeautifulSoup/bs4/doc/#differences-between-parsers)
- **EPUBLib（`epublib`）**面向 EPUB 3。可用 `with EPUB(path, generator_tag=False) as book:` 查看 `metadata`、`manifest`、`spine`、`documents`、`nav` 和 `ncx`。文档集合可含 NAV。遇到缺少 EPUB 3 导航的 EPUB 2 或其他解析失败时，以 ZIP、OPF 和 NCX 为准。[API](https://epublib.readthedocs.io/en/stable/epublib.html) · [PyPI](https://pypi.org/project/epublib/0.1.7/)
- **EbookLib（`ebooklib`）**是独立的可选库，可用 `epub.read_epub(path)` 辅助提取 EPUB 2/3 的目录和资源。需要原样检查 XHTML 时，从 ZIP 读取成员字节。编辑现有书籍走局部补丁流程，避免两个库的整书写入接口重建章节或导航。[EbookLib 教程](https://github.com/aerkalov/ebooklib/blob/master/docs/tutorial.rst) · [往返限制](https://docs.sourcefabric.org/projects/ebooklib/en/v0.21/faq.html)
- **EPUBCheck**校验 EPUB 2/3 规范，由独立命令或 Java 发行包提供。使用同一版本执行前后对照。CLI 的 `--json <report>` 保存结构化诊断。规范校验需要结合差异审阅和阅读器抽查。[安装](https://www.w3.org/publishing/epubcheck/docs/installation/) · [CLI](https://www.w3.org/publishing/epubcheck/docs/cli/) · [发行版](https://github.com/w3c/epubcheck/releases)

容器路径、ZIP 约束、字体混淆和包元数据定义见 [EPUB 3.3](https://www.w3.org/TR/epub-33/) 与 [EPUB 3.4](https://www.w3.org/TR/epub-34/)。
