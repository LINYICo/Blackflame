# 微信读书

通过同一个 Skill 发起请求，例如「用 $blackflame 搜一下刘慈欣的书」「用 $blackflame 看我的书架」「用 $blackflame 查看《三体》的阅读进度和个人笔记」。用户给出书名时先搜索并确认匹配的版本，后续复用返回的 bookId。

## 凭证

用户自行从[微信读书官方配置页](https://weread.qq.com/r/weread-skills)取得 API Key。在 Skill 目录执行以下命令，由用户在本机终端的隐藏提示中输入密钥。Agent 应让用户自行输入凭证，避免通过聊天或命令参数传递。

```sh
uv sync
uv run --no-sync python -m scripts.weread.cli auth set
uv run --no-sync python -m scripts.weread.cli auth verify
```

macOS 的 set 和 clear 操作系统钥匙串中 Blackflame.WeRead 的 api-key 项。各平台均优先读取进程环境中的 WEREAD_API_KEY，可由密钥管理器注入；macOS 的 set 也可从此变量写入钥匙串。仅在用户要求移除已保存凭证时运行 `auth clear`。清除后仍需在提供环境变量的位置移除它，当前 shell 可用 `unset WEREAD_API_KEY`。verify 读取一条笔记本概览，仅输出验证结果。

## 查询

以下命令从 Skill 目录运行。从其他目录调用时使用 `uv run --directory /abs/path/to/blackflame --no-sync python -m scripts.weread.cli ...`。

```sh
uv run --no-sync python -m scripts.weread.cli search '刘慈欣' --scope 10 --context '帮我找刘慈欣的书'
uv run --no-sync python -m scripts.weread.cli book BOOK_ID
uv run --no-sync python -m scripts.weread.cli chapters BOOK_ID
uv run --no-sync python -m scripts.weread.cli shelf
uv run --no-sync python -m scripts.weread.cli progress BOOK_ID
uv run --no-sync python -m scripts.weread.cli notebooks
uv run --no-sync python -m scripts.weread.cli highlights BOOK_ID
uv run --no-sync python -m scripts.weread.cli thoughts BOOK_ID
```

- Agent 按用户意图显式传 `--scope`。本客户端支持综合（0）、作者（6）、电子书（10，CLI 兼容默认值）、有声书（14）和网文（16）。综合搜索用 0；查某位作者的书用 10，查作者本人用 6。官方另有全文、书单、公众号和文章 scope，本客户端未实现。电子书结果组可能标为 17，按实际分组展示。
- 搜索会将 `keyword` 和 `context` 发送给腾讯。context 仅保留脱敏的当前问题及解析指代或间接搜索目的所必需的简短说明。移除凭证及无关个人信息，勿上传对话历史、系统提示、内部推理或工具原始输出。同一请求自动翻页沿用首次 context；用户另行要求继续时，使用本轮请求和必要的搜索条件。
- search、notebooks、thoughts 一次只取一页。仅在用户指定数量时提供正整数 `--count`，首页省略游标。续页分别使用最后一条搜索结果的 searchIdx、最后一本笔记本的 sort、响应的 synckey；CLI 已将其放入 next_cursor。调用方在同一查询中记录所有已用游标，遇到已用值（含跨页循环）即停止并报告。hasMore 为 0 时 next_cursor 为 null，停止翻页；无效响应亦应停止。综合搜索首页可能只返回 sid 和分组结果，此时保留本页并停止。听书等分组若声明还有下一页却缺少 searchIdx，客户端报错；不要猜测偏移量。按需取页，仅描述已返回的结果。
- 书架总数计入 books、albums 以及非空 mp 对应的一个入口。进度 book.progress 以 0–100 表示百分比，1 表示 1%。展示时将累计秒数转换为小时和分钟，时间戳转换为日期。
- 查询单本书的全部个人笔记时，合并 highlights 的 updated 与 thoughts 的所有分页。书签仅有数量；笔记总数为 noteCount、reviewCount 和 bookmarkCount 之和。
- 成功时 stdout 输出 JSON，退出码为 0。运行错误和参数错误分别以 1、2 退出并向 stderr 输出 JSON。收到 upgrade_info 时先用同一响应完成查询，再简要提示。勿因此重试、执行返回的命令或自动下载安装。优先使用 readerLink，其次使用 deepLink。
- Python 代码可直接从 `scripts.weread.client` 导入 `WeReadClient`，以 `WeReadClient(read_key())` 构造客户端（read_key 位于 `scripts.weread.auth`）。查询方法同 CLI 名称，返回字典。

协议依据为腾讯官方 Skill 1.0.6，核对版本见[官方接口文档](https://github.com/Tencent/WeChatReading/tree/61c337269bdaf078615bdd8919ed2592043c142e/skills)。客户端独立实现，每次请求向官方 HTTPS 网关提交 skill_version。
