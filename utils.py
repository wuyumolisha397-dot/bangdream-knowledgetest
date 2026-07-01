"""
bandori-knowledge 工具函数模块

提供路径清理、分类映射、文本处理等通用工具。
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

from config import OutputConfig


# ── 文件名清理 ──────────────────────────────────────────────────────────────

# Windows 文件名非法字符
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# 连续空白 / 下划线
_MULTI_WS = re.compile(r"[\s_]+")
# 末尾的点号和空格（Windows 不允许）
_TRAILING_DOT_SPACE = re.compile(r"[.\s]+$")


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """将页面标题清理为合法文件名

    Args:
        name: 原始标题
        max_length: 最大长度限制

    Returns:
        清理后的文件名（不含扩展名）
    """
    # Unicode NFC 规范化
    name = unicodedata.normalize("NFC", name)
    # 替换非法字符为下划线
    name = _ILLEGAL_CHARS.sub("_", name)
    # 合并连续空白 / 下划线
    name = _MULTI_WS.sub("_", name)
    # 去除首尾空白
    name = name.strip(" _")
    # 去除末尾点号和空格
    name = _TRAILING_DOT_SPACE.sub("", name)
    # 截断
    if len(name) > max_length:
        name = name[:max_length].rstrip(" _.")
    # 空名兜底
    if not name:
        name = "unnamed"
    return name


# ── 分类 → 目录映射 ─────────────────────────────────────────────────────────


def map_category_to_dir(categories: list[str], config: OutputConfig) -> str:
    """根据页面分类列表，确定输出子目录

    匹配逻辑：
    1. 遍历 categories 中的每个分类名
    2. 检查分类名是否包含 config.category_dir_map 中的任意关键字
    3. 命中第一个匹配的关键字 → 对应目录
    4. 无匹配 → "其它"

    Args:
        categories: 页面所属分类列表
        config: 输出配置

    Returns:
        子目录名，如 "角色", "歌曲", "其它"
    """
    for cat in categories:
        for keyword, dir_name in config.category_dir_map.items():
            if keyword in cat:
                return dir_name
    return "其它"


# ── Wiki 标题处理 ────────────────────────────────────────────────────────────


def normalize_category_title(title: str) -> str:
    """规范化分类标题

    确保分类标题以 'Category:' 开头（MediaWiki 命名空间）。

    Args:
        title: 原始标题

    Returns:
        规范化后的分类标题
    """
    if not title.startswith("Category:"):
        return f"Category:{title}"
    return title


def strip_namespace(title: str) -> str:
    """去除标题的命名空间前缀

    Args:
        title: 含命名空间的标题

    Returns:
        去除前缀后的标题
    """
    for prefix in ("Category:", "Template:", "Module:", "Help:", "File:"):
        if title.startswith(prefix):
            return title[len(prefix):]
    return title


def build_page_url(title: str, base_url: str = "https://zh.moegirl.org.cn") -> str:
    """构建页面 URL

    Args:
        title: 页面标题
        base_url: 站点基础 URL

    Returns:
        完整页面 URL
    """
    from urllib.parse import quote

    encoded = quote(title, safe="")
    return f"{base_url}/{encoded}"


# ── 文本处理 ─────────────────────────────────────────────────────────────────


def count_chinese_chars(text: str) -> int:
    """统计文本中的中文字符数（含标点）

    用于判断页面长度是否超过阈值。

    Args:
        text: 待统计文本

    Returns:
        字符数
    """
    return len(text)


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本用于日志显示

    Args:
        text: 原始文本
        max_length: 最大长度

    Returns:
        截断后的文本
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


# ── 路径工具 ─────────────────────────────────────────────────────────────────


def ensure_dir(path: Path) -> Path:
    """确保目录存在

    Args:
        path: 目录路径

    Returns:
        创建后的目录路径
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_output_filepath(
    title: str,
    sub_dir: str,
    output_dir: Path,
    suffix: str = "",
) -> Path:
    """获取页面输出文件路径

    Args:
        title: 页面标题
        sub_dir: 子目录名（如 "角色", "歌曲"）
        output_dir: 输出根目录
        suffix: 文件名后缀（用于拆分页面，如 "_1"）

    Returns:
        完整文件路径
    """
    filename = sanitize_filename(title)
    if suffix:
        filename = f"{filename}{suffix}"
    dir_path = ensure_dir(output_dir / sub_dir)
    return dir_path / f"{filename}.md"
