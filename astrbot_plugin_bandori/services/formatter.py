"""
响应格式化模块

将检索结果转换为美观的 Markdown 格式。
支持 AstrBot 的 Markdown 渲染（QQ 适配器等）。
"""

from __future__ import annotations

from .kb_index import IndexEntry


# ── 格式常量 ────────────────────────────────────────────────────────────────

HR = "———"

EMOJI = {
    "角色": "🎸",
    "歌曲": "🎵",
    "乐队": "🎪",
    "其它": "📖",
    "star": "⭐",
    "music": "🎶",
    "search": "🔍",
    "random": "🎲",
    "notfound": "😿",
    "link": "🔗",
    "tag": "🏷️",
    "page": "📄",
}


def _emd(key: str) -> str:
    """快捷表情"""
    return EMOJI.get(key, "•")


# ── 单条结果 ────────────────────────────────────────────────────────────────

def format_entry_detail(entry: IndexEntry, content: str, max_len: int = 1200) -> str:
    """单条目详细信息

    用于 /角色 /歌曲 /乐队 精确命中时。
    """
    emoji = _emd(entry.category_dir)

    lines = [
        f"{emoji} **{entry.title}**",
        "",
    ]

    # 分类标签
    if entry.categories:
        tags = ", ".join(f"`{c}`" for c in entry.categories[:6])
        if len(entry.categories) > 6:
            tags += f" +{len(entry.categories) - 6}"
        lines.append(f"{_emd('tag')} {tags}")
        lines.append("")

    # 正文
    if content:
        # 截断过长的内容
        if len(content) > max_len:
            content = content[:max_len] + "\n\n> …(内容过长，已截断)"
        lines.append(content)
    else:
        lines.append("> 暂无详细内容")

    lines.append("")
    lines.append(HR)
    lines.append(f"{_emd('link')} [萌娘百科](https://zh.moegirl.org.cn/)  ·  {_emd('page')} 本地知识库")

    return "\n".join(lines)


# ── 搜索结果列表 ────────────────────────────────────────────────────────────

def format_search_results(
    results: list[tuple[IndexEntry, float]],
    query: str,
    category: str = "",
    is_rag: bool = False,
) -> str:
    """多条搜索结果

    用于 /萌百搜索 或模糊匹配时。
    """
    cat_label = category or "全部"
    source = "RAG 云端" if is_rag else "本地知识库"

    lines = [
        f"{_emd('search')} 搜索 **「{query}」**  ({cat_label} · {source})",
        "",
    ]

    if not results:
        lines.append(f"{_emd('notfound')} 未找到相关结果，建议缩短关键词或换用其他关键词重试。")
        return "\n".join(lines)

    lines.append(f"共找到 **{len(results)}** 条结果：")
    lines.append("")

    for i, (entry, score) in enumerate(results, 1):
        emoji = _emd(entry.category_dir)
        preview = entry.preview[:80].replace("\n", " ") if entry.preview else "(无简介)"

        lines.append(f"**{i}.** {emoji} **{entry.title}**  `匹配度 {score:.0f}%`")
        lines.append(f"      {preview}…")
        lines.append("")

    lines.append(f"{HR}")
    lines.append(f"💡 使用 `/角色 <名称>` `/歌曲 <名称>` `/乐队 <名称>` 查看详情")

    return "\n".join(lines)


# ── 随机结果 ────────────────────────────────────────────────────────────────

def format_random(entry: IndexEntry, content: str) -> str:
    """随机抽取结果"""
    emoji = _emd(entry.category_dir)
    cat_label = entry.category_dir or "其它"

    lines = [
        f"{_emd('random')} 随机{cat_label} — {emoji} **{entry.title}**",
        "",
    ]

    # 分类标签
    if entry.categories:
        tags = ", ".join(f"`{c}`" for c in entry.categories[:5])
        lines.append(f"{_emd('tag')} {tags}")
        lines.append("")

    # 正文
    if content:
        if len(content) > 800:
            content = content[:800] + "\n\n> …(内容过长，已截断)"
        lines.append(content)
    else:
        lines.append("> 暂无详细内容")

    lines.append("")
    lines.append(HR)
    lines.append(f"🎲 再抽一次发送 `/随机{cat_label}`  ·  {_emd('link')} [萌娘百科](https://zh.moegirl.org.cn/)")

    return "\n".join(lines)


# ── 帮助信息 ────────────────────────────────────────────────────────────────

def format_help() -> str:
    """插件帮助信息"""
    return f"""🎸 **BanG Dream! 知识库** v1.0

{HR}

**可用命令：**

| 命令 | 说明 | 示例 |
|------|------|------|
| `/角色 <名称>` | 查询角色信息 | `/角色 丰川祥子` |
| `/歌曲 <名称>` | 查询歌曲信息 | `/歌曲 -N-E-M-E-S-I-S-` |
| `/乐队 <名称>` | 查询乐队信息 | `/乐队 Ave Mujica` |
| `/随机角色` | 随机一位角色 | `/随机角色` |
| `/随机歌曲` | 随机一首歌曲 | `/随机歌曲` |
| `/萌百搜索 <关键词>` | 全站搜索 | `/萌百搜索 Roselia` |

{HR}

💡 **提示：** 优先查询本地知识库，无结果时自动回退到 RAG 检索。
📖 数据来源：[萌娘百科 BanG Dream! 专题](https://zh.moegirl.org.cn/Category:BanG_Dream!)
"""


# ── 错误信息 ────────────────────────────────────────────────────────────────

def format_error(msg: str) -> str:
    """错误消息"""
    return f"😿 {msg}"


def format_not_found(query: str, category: str = "") -> str:
    """未找到结果"""
    cat_label = f"在 {category} 中" if category else ""
    return (
        f"{_emd('notfound')} 未{cat_label}找到关于 **「{query}」** 的结果。\n\n"
        f"建议：\n"
        f"• 检查拼写是否正确\n"
        f"• 尝试更简短的关键词\n"
        f"• 使用 `/萌百搜索 {query}` 全局搜索\n"
        f"• 使用 `/随机{category}` 浏览条目"
    )
