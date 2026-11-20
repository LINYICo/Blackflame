# 编辑流程

从技能目录运行命令，替换示例路径。把计划、工作文件和诊断留在任务目录，避免公开书籍内容。

## 准备替换文件

```bash
python3 scripts/epub_patch.py inspect book.epub > inventory.json
```

- **元数据。** 从清单选定实际 OPF 路径。以 OPF 和 Dublin Core 命名空间定位现有字段。多个作者或标题时用 ID、角色和旧值确定目标，保留标识符、顺序、属性、`refines` 和自定义元数据。需要同步 EPUB 3 的 `dcterms:modified` 时，使用明确的 UTC 时间并记录变更。
- **正文。** 按 spine 扫描目标章节，检查推广语出现的位置、频次和上下文。记下 ZIP 路径、稳定定位、简短前后文和命中依据。原始 XHTML 中的目标必须唯一匹配；广告和正文混排时只编辑对应的文本片段。删除独立元素前检查后续 `tail` 文本、脚注、ID、链接和复用图片，保留仍被引用的结构。
- **序列化。** 保留原编码、XML 声明、doctype、命名空间、注释、处理指令和原有排版属性，关闭 pretty-print。检查每份 OPF 或 XHTML 的完整差异。关注 XHTML 的 `head`、样式、脚本、标题和锚点，以及 SVG、MathML 和 ruby。避免无关序列化变化；原始结构异常时改用可核实的定点编辑或报告阻碍。
- **引用。** 审阅修改目标及引用它的 NAV、NCX、landmarks、page-list、章节和媒体叠加层。以引用所在文件的位置解析相对 URL，解码路径和片段后核实本地资源及目标 ID。远程资源保留 URL 并结合上下文审阅。

将替换文件保存到计划附近。键是清单里的 ZIP 成员完整路径，值是相对于计划的本地文件路径（也支持绝对路径）。`source_sha256` 使用 `inspect` 的值。只列实际要更新的条目。

```json
{
  "source_sha256": "<从 inventory.json 复制>",
  "replacements": {
    "OPS/package.opf": "replacements/package.opf",
    "OPS/text/chapter.xhtml": "replacements/chapter.xhtml"
  }
}
```

## 应用与校验

```bash
python3 scripts/epub_patch.py apply book.epub edited.epub \
  --plan plan.json --report-dir reports
```

脚本只接受单一 OPF EPUB 2/3 的既有常用元数据字段文本和非 NAV 的 XHTML 正文补丁。它检查 ZIP 路径、重复项、压缩方式、首个 `mimetype` 条目和有界解压，并在源文件存在签名、权利管理或加密描述时拒绝写入。字体混淆也可使用 `encryption.xml`，此时先确认保护类型与处理范围。

脚本核对 OPF 非目标结构、XHTML 的 `head` 和根节点、`body` 属性及锚点，按原 ZIP 顺序写入候选文件，读取每个成员进行 SHA-256 比对。目标路径必须全新，候选文件通过检查后才发布。`changes.json` 记录源、输出及改动成员的哈希，前后 EPUBCheck JSON 和日志记录规范诊断。文字语义、段落定位、注释保留和具体排版仍需审阅。

默认要求基线无 EPUBCheck 错误。用户明确接受已知基线后，可加 `--allow-existing-errors`。同一版本的前后结果按严重度、诊断 ID、消息、成员路径和上下文比较计数，忽略行列位移；新增错误、严重错误或警告会阻止发布。需要查清诊断时，查看原始 JSON 中的行列和关联位置。若 EPUBCheck 不可用，先完成检查、候选识别和补丁准备，标明校验尚未完成。

交付时给出副本、改动摘要、验证报告以及残留的旧问题。具备阅读器时，抽查受影响章节、目录跳转和封面。章节级重排或资源增删要另行验证对应 manifest、spine、导航、落点和所有受影响的引用。
