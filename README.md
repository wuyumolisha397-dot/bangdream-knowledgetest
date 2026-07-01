# bandori-knowledge

BanG Dream! 知识库自动构建工具 — 从萌娘百科爬取词条并导出高质量 Markdown，供 AstrBot 直接导入知识库。

## 功能特性

- 🔄 **全自动爬取** — 从 `Category:BanG Dream!` 开始，递归所有子分类
- 📄 **高质量 Markdown** — 使用 mwparserfromhell 解析 wikitext，生成干净 Markdown
- 📁 **自动分类** — 按角色/歌曲/乐队/动画/专辑/Live/其它分目录
- ✂️ **超长页面拆分** — 超过 5000 字自动按 H2/H3 拆分
- 💾 **断点续爬** — 基于 SQLite 缓存，Ctrl+C 后可继续
- 🔄 **增量更新** — 仅下载 RevisionID 变更的页面
- 🚀 **高性能** — httpx AsyncClient + HTTP/2 + 连接池 + 速率控制
- 📊 **详细统计** — 页面数/分类数/失败数/重试次数/耗时

## 安装

```bash
# 克隆项目
git clone https://github.com/your-repo/bandori-knowledge.git
cd bandori-knowledge

# 安装依赖（建议使用虚拟环境）
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 系统要求

- Python 3.11+
- 网络（需访问 zh.moegirl.org.cn）

## 使用

### 完整爬取

```bash
python crawler.py
```

首次运行将：
1. 从 `Category:BanG Dream!` 递归发现所有子分类
2. 获取所有页面内容
3. 解析 wikitext 为 Markdown
4. 按分类导出到 `output/` 目录

### 增量更新

```bash
python crawler.py update
# 或
python crawler.py --update
```

仅下载 RevisionID 发生变化的页面，大幅减少请求量。

### 查看统计

```bash
python crawler.py stats
# 或
python crawler.py --stats
```

### 清空缓存

```bash
python crawler.py clean-cache
# 或
python crawler.py --clean-cache
```

清除所有缓存数据，下次运行将从头爬取。

## 输出结构

```
output/
├── 角色/
│   ├── 千早爱音.md
│   ├── 高松灯.md
│   └── ...
├── 歌曲/
│   ├── 碧天伴走.md
│   └── ...
├── 乐队/
│   ├── MyGO!!!!!!.md
│   ├── Ave_Mujica.md
│   └── ...
├── 动画/
│   └── ...
├── 专辑/
│   └── ...
├── Live/
│   └── ...
├── 其它/
│   └── ...
├── _index.json          # 页面索引（供 AstrBot 使用）
└── _crawl_stats.json    # 爬取统计
```

### Markdown 格式

每个文件包含 YAML frontmatter：

```markdown
---
title: 千早爱音
url: https://zh.moegirl.org.cn/千早爱音
revision: 123456
updated: 2026-07-01
categories:
  - BanG Dream!
  - MyGO!!!!!
---

# 千早爱音

正文内容……
```

## AstrBot 导入

本项目提供完整的 AstrBot 插件，详见 [astrbot_plugin_bandori/](astrbot_plugin_bandori/) 目录：

```bash
# 1. 复制插件
cp -r astrbot_plugin_bandori/ <astrbot>/data/plugins/

# 2. 设置知识库路径
export BANDORI_KB_PATH=/path/to/bandori-knowledge/output

# 3. 重启 AstrBot
```

插件命令：`/角色` `/歌曲` `/乐队` `/随机角色` `/随机歌曲` `/萌百搜索`

## 环境变量配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `BANDORI_RATE_LIMIT` | 请求间隔（秒） | 0.5 |
| `BANDORI_MAX_CONCURRENT` | 最大并发数 | 3 |
| `BANDORI_DB_PATH` | 缓存数据库路径 | cache/pages.db |
| `BANDORI_OUTPUT_DIR` | 输出目录 | output/ |
| `BANDORI_ROOT_CATEGORY` | 起始分类 | Category:BanG Dream! |
| `BANDORI_HTTP2` | 启用 HTTP/2 | true |
| `BANDORI_LOG_LEVEL` | 日志级别 | INFO |

## 项目结构

```
bandori-knowledge/
├── crawler.py            # 主入口（CLI + 爬虫编排）
├── parser.py             # wikitext → Markdown 解析器
├── exporter.py           # Markdown 文件导出器
├── mediawiki.py          # MediaWiki API 异步客户端
├── cache.py              # SQLite 缓存管理
├── models.py             # 数据模型定义
├── config.py             # 配置管理
├── utils.py              # 工具函数
├── requirements.txt      # 运行时依赖
├── requirements-dev.txt  # 开发依赖（含测试）
├── README.md             # 本文件
├── LICENSE               # MIT License
├── tools/                # 辅助脚本
│   ├── crawl_voice_actors.py  # 声优抓取
│   ├── scan_quality.py        # 质量扫描
│   └── auto_fix.py            # 自动修复
├── astrbot_plugin_bandori/    # AstrBot 插件
├── tests/                # 测试目录
├── logs/                 # 日志目录（gitignored）
├── cache/                # 缓存目录（gitignored）
└── output/               # 输出目录（gitignored）
```

## 技术栈

- **HTTP 客户端**: httpx (AsyncClient + HTTP/2)
- **Wiki 解析**: mwparserfromhell
- **重试策略**: tenacity (指数退避 + 随机抖动)
- **缓存**: SQLite (WAL 模式)
- **序列化**: orjson, PyYAML
- **CLI**: typer
- **日志**: loguru
- **进度条**: rich

## FAQ

### Q: 爬取速度太慢怎么办？

调低请求间隔、提高并发数：

```bash
export BANDORI_RATE_LIMIT=0.2
export BANDORI_MAX_CONCURRENT=5
python crawler.py
```

⚠️ 请注意不要对服务器造成过大压力。

### Q: 爬取中断了怎么办？

直接重新运行 `python crawler.py`，缓存会自动跳过已完成的页面。如需完全重新爬取，先运行 `python crawler.py clean-cache`。

### Q: 如何只更新部分页面？

使用增量更新模式：`python crawler.py update`，只会下载 RevisionID 变化的页面。

### Q: 输出目录如何给 AstrBot 使用？

将 `output/` 目录整体导入 AstrBot 知识库，或使用 `_index.json` 索引文件。

### Q: 某些页面导出为空？

可能原因：
- 页面是重定向页（自动跳过）
- 页面内容被模板/导航框占满（解析后被清理）
- 页面实际内容为空

### Q: 如何添加新的分类映射？

编辑 `config.py` 中的 `OutputConfig.category_dir_map`，添加新的关键字 → 目录映射。

## 许可证

MIT License

## 免责声明

本项目仅供学习交流使用。爬取的数据来源于萌娘百科，请遵守萌娘百科的使用条款。请合理控制请求频率，不要对服务器造成过大压力。
