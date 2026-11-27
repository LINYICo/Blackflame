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
uv run --no-sync python -m scripts.weread.cli search '刘慈欣' --context '帮我找刘慈欣的书'
uv run --no-sync python -m scripts.weread.cli book BOOK_ID
uv run --no-sync python -m scripts.weread.cli chapters BOOK_ID
uv run --no-sync python -m scripts.weread.cli shelf
uv run --no-sync python -m scripts.weread.cli progress BOOK_ID
uv run --no-sync python -m scripts.weread.cli notebooks
uv run --no-sync python -m scripts.weread.cli highlights BOOK_ID
uv run --no-sync python -m scripts.weread.cli thoughts BOOK_ID
```

- 搜索默认查电子书。按意图用 `--scope` 选择综合（0）、作者（6）、电子书（10）、有声书（14）或网文（16）。查询作者所著的书时，使用作者名作为电子书检索词。context 填用户原问题，多轮仅补必要指代，先移除凭证及无关上下文。
- search、notebooks、thoughts 每次返回一页，含官方响应 data 和 next_cursor。仅在用户指定数量时传 `--count N`。需要更多时将 next_cursor 原样传入 `--cursor N`，直至 null。遇到重复游标即停止并报告。自动续搜沿用原 context。结果分组以回包为准。
- 书架总数计入 books、albums 以及非空 mp 对应的一个入口。进度 book.progress 以 0–100 表示百分比，1 表示 1%。展示时将累计秒数转换为小时和分钟，时间戳转换为日期。
- 查询单本书的全部个人笔记时，合并 highlights 的 updated 与 thoughts 的所有分页。书签仅有数量；笔记总数为 noteCount、reviewCount 和 bookmarkCount 之和。
- 成功时 stdout 输出 JSON，退出码为 0。运行错误和参数错误分别以 1、2 退出并向 stderr 输出 JSON。upgrade_info 为服务端升级提示，继续使用当前结果。优先使用 readerLink，其次使用 deepLink。
- Python 代码可直接从 `scripts.weread.client` 导入 `WeReadClient`，以 `WeReadClient(read_key())` 构造客户端（read_key 位于 `scripts.weread.auth`）。查询方法同 CLI 名称，返回字典。

协议依据为腾讯官方 Skill 1.0.6，核对版本见[官方接口文档](https://github.com/Tencent/WeChatReading/tree/61c337269bdaf078615bdd8919ed2592043c142e/skills)。客户端独立实现，每次请求向官方 HTTPS 网关提交 skill_version。
