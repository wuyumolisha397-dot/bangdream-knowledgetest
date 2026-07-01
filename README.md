# bandori-knowledge

BanG Dream! 知识库 + AstrBot 插件 — 一键部署，QQ 机器人可用。

## 快速开始

```bash
# 1. 下载知识库
git clone -b kb-data https://github.com/wuyumolisha397-dot/astrbot_plugin_bandori-knowledge.git bandori-kb
cd bandori-kb
tar -xzf releases/bandori-kb-v1.1.tar.gz

# 2. 下载插件
git clone https://github.com/wuyumolisha397-dot/astrbot_plugin_bandori-knowledge.git

# 3. 部署
cp -r astrbot_plugin_bandori-knowledge <astrbot>/data/plugins/astrbot_plugin_bandori
export BANDORI_KB_PATH=$(pwd)/output
# 重启 AstrBot
```

## 插件命令

| 命令 | 功能 |
|------|------|
| `/角色 丰川祥子` / `/随机角色` | 角色查询 |
| `/歌曲 壱雫空` / `/随机歌曲` | 歌曲查询 |
| `/乐队 Roselia` / `/随机乐队` | 乐队查询 |
| `/声优 爱美` / `/随机声优` | 声优查询 |
| `/萌百搜索 Roselia` | 全站搜索 |
| `/bandori` | 帮助 |

所有查询支持图文卡片回复。图片需运行 `tools/download_images.py` 下载。

## 知识库

| 分类 | 条目数 | 图文 |
|------|--------|------|
| 角色 | 137 | ✅ 69 张 |
| 歌曲 | 648 | 待下载 |
| 乐队 | 70 | ✅ 22 张 |
| 声优 | 64 | ✅ 62 张 |
| 其它 | 301 | - |

数据来源：萌娘百科 BanG Dream! 专题。定期更新。

## 图片下载

```bash
pip install httpx pyyaml
python tools/download_images.py          # 角色
python tools/download_images.py 声优      # 声优
python tools/download_images.py 歌曲      # 歌曲
python tools/download_images.py 乐队      # 乐队
```

图片自动匹配，插件回复时图文合并一条消息。

## 爬虫（可选）

如果你需要自己爬取最新数据：

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python crawler.py           # 完整爬取
python crawler.py update    # 增量更新
```

## 项目结构

```
├── crawler.py / parser.py / exporter.py   # 爬虫核心
├── config.py / models.py / utils.py       # 基础设施
├── astrbot_plugin_bandori/                # AstrBot 插件
├── tools/                                 # 辅助脚本
└── output/                                # 知识库数据
```

## 许可证

MIT License

## Vibe Coding 声明

本项目完全由 AI 辅助生成（Claude / Vibe Coding）。

> ⚠️ 生产使用前请自行审查代码。
