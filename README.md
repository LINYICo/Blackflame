# EpubLib

用于检查和精确编辑现有 EPUB 2/3 的 Agent Skill。适合修订元数据、纠正章节文字和清理明确的推广内容。局部补丁保留原始导航、阅读顺序和未修改资源。

## 安装

将 [`epublib/`](epublib/) 放入客户端的技能目录。例如，Codex 默认使用 `~/.agents/skills/`。

```bash
git clone https://github.com/LINYICo/EpubLib.git
mkdir -p ~/.agents/skills
cp -R EpubLib/epublib ~/.agents/skills/
cp EpubLib/LICENSE ~/.agents/skills/epublib/
```

在已有环境使用 Python 3.11+ 和 `lxml`。应用补丁还需要可运行的 EPUBCheck。可选分析工具与官方文档见[工具参考](epublib/references/tools.md)。

## 使用

> 用 $epublib 把这本书的书名改为《修订版》，只处理明确的推广段落，并输出校验过的副本。

`inspect` 查看原书结构。准备好逐文件替换后，`apply` 校验并生成副本。命令、补丁格式和基线诊断的处理方式见[编辑流程](epublib/references/editing.md)。

## 许可证

[MIT](LICENSE)
