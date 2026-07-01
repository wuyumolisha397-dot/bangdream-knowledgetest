"""
本地知识库索引与检索引擎

功能：
- 启动时扫描 output/ 目录下的所有 .md 文件
- 解析 YAML frontmatter 提取标题与分类
- 构建多级索引 (角色/歌曲/乐队/其他)
- 提供模糊搜索、精确搜索、随机抽取

数据结构：
{
    "characters": [{"title": "...", "file": "...", "categories": [...], "preview": "..."}, ...],
    "songs": [...],
    "bands": [...],
    "others": [...],
}
"""

from __future__ import annotations

import os
import random
import re
import yaml
from pathlib import Path
from typing import Optional


# ── 分类 → 子目录映射 ─────────────────────────────────────────────────────

CATEGORY_DIR_MAP = {
    "角色": "角色",
    "歌曲": "歌曲",
    "乐队": "乐队",
}

# 用于全局搜索的子目录列表
ALL_DIRS = ["角色", "歌曲", "乐队", "其它", "声优", "动画", "Live"]


# ── 索引结构 ──────────────────────────────────────────────────────────────

class IndexEntry:
    """单条索引项"""
    __slots__ = ("title", "filepath", "categories", "preview", "category_dir")

    def __init__(
        self,
        title: str,
        filepath: str,
        categories: list[str],
        preview: str = "",
        category_dir: str = "",
    ) -> None:
        self.title = title
        self.filepath = filepath
        self.categories = categories
        self.preview = preview
        self.category_dir = category_dir


class KnowledgeIndex:
    """知识库全文索引"""

    def __init__(self, kb_root: str) -> None:
        self._kb_root = Path(kb_root)
        self._entries: dict[str, list[IndexEntry]] = {
            "角色": [],
            "歌曲": [],
            "乐队": [],
            "其它": [],
        }
        self._all_entries: list[IndexEntry] = []
        self._loaded = False

    # ── 加载 ───────────────────────────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def total_count(self) -> int:
        return len(self._all_entries)

    def load(self) -> None:
        """扫描 KB 目录并构建索引"""
        if not self._kb_root.exists():
            raise FileNotFoundError(f"知识库目录不存在: {self._kb_root}")

        for dir_name in ALL_DIRS:
            dir_path = self._kb_root / dir_name
            if not dir_path.is_dir():
                continue

            bucket = CATEGORY_DIR_MAP.get(dir_name, "其它")

            for fname in os.listdir(dir_path):
                if not fname.endswith(".md"):
                    continue

                filepath = dir_path / fname
                entry = self._parse_file(filepath, bucket)
                if entry is None:
                    continue

                self._entries[bucket].append(entry)
                self._all_entries.append(entry)

        self._loaded = True

    def reload(self) -> None:
        """重建索引"""
        for key in self._entries:
            self._entries[key].clear()
        self._all_entries.clear()
        self._loaded = False
        self.load()

    # ── 解析 ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_file(filepath: Path, bucket: str) -> Optional[IndexEntry]:
        """解析单个 .md 文件"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            return None

        title = filepath.stem  # fallback
        categories: list[str] = []
        body = raw

        # 解析 YAML frontmatter
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                try:
                    fm = yaml.safe_load(parts[1])
                    if isinstance(fm, dict):
                        title = fm.get("title", title)
                        cats = fm.get("categories", [])
                        if isinstance(cats, list):
                            categories = [str(c) for c in cats if c]
                except yaml.YAMLError:
                    pass
                body = parts[2]

        # 提取正文预览（前 200 字符，去掉标题行和空行）
        body_clean = body.strip()
        body_clean = re.sub(r"^#.*\n", "", body_clean, count=1)  # 去 H1
        body_clean = re.sub(r"\n{2,}", " ", body_clean)
        body_clean = re.sub(r"#+\s", "", body_clean)
        preview = body_clean[:200].strip()

        rel_path = str(filepath).replace("\\", "/")

        return IndexEntry(
            title=title,
            filepath=rel_path,
            categories=categories,
            preview=preview,
            category_dir=bucket,
        )

    # ── 搜索 ───────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        category: str = "",
        limit: int = 5,
    ) -> list[tuple[IndexEntry, float]]:
        """模糊搜索，返回 (条目, 相关度分数) 列表

        Args:
            query: 搜索词
            category: 限定分类 ("角色"/"歌曲"/"乐队"/"")，空字符串表示全局搜索
            limit: 返回结果数上限

        Returns:
            按相关度降序排列的结果列表
        """
        if not query.strip():
            return []

        pool = self._entries.get(category, []) if category else self._all_entries
        query_lower = query.lower().strip()

        scored: list[tuple[IndexEntry, float]] = []

        for entry in pool:
            score = self._score(entry, query_lower)
            if score > 0:
                scored.append((entry, score))

        # 按分数降序
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    @staticmethod
    def _score(entry: IndexEntry, query_lower: str) -> float:
        """计算匹配分数"""
        title_lower = entry.title.lower()
        score = 0.0

        # 精确标题匹配 → 最高分
        if title_lower == query_lower:
            score = 100.0
        # 标题以查询开头
        elif title_lower.startswith(query_lower):
            score = 80.0
            # 「简介」页加权
            if "简介" in title_lower:
                score += 10
        # 标题包含查询
        elif query_lower in title_lower:
            score = 60.0 + (len(query_lower) / len(title_lower)) * 20.0
            if "简介" in title_lower:
                score += 5
        # 查询包含在分类中
        else:
            for cat in entry.categories:
                if query_lower in cat.lower():
                    score = 30.0
                    break
            if score == 0 and query_lower in entry.preview.lower():
                score = 15.0
            if score == 0 and len(query_lower) >= 2:
                overlap = sum(1 for ch in query_lower if ch in title_lower)
                if overlap >= len(query_lower) * 0.6:
                    score = 10.0 + overlap * 3.0

        # 惩罚空页 — 正文少于 30 字扣分
        if len(entry.preview) < 30:
            score -= 40

        return max(score, 0)

    # ── 精确获取 ───────────────────────────────────────────────────────────

    def get_by_title(self, title: str, category: str = "") -> Optional[IndexEntry]:
        """按标题精确匹配"""
        pool = self._entries.get(category, []) if category else self._all_entries
        title_lower = title.lower().strip()

        for entry in pool:
            if entry.title.lower() == title_lower:
                return entry
        return None

    # ── 随机 ────────────────────────────────────────────────────────────────

    def random_pick(self, category: str) -> Optional[IndexEntry]:
        """从指定分类中随机抽取，避开空页/注释页"""
        pool = self._entries.get(category, [])
        if not pool:
            return None
        # 过滤：只取正文超过 50 字的条目
        good = [e for e in pool if len(e.preview) > 50]
        if good:
            return random.choice(good)
        # 退而求其次
        decent = [e for e in pool if len(e.preview) > 10]
        if decent:
            return random.choice(decent)
        return random.choice(pool) if pool else None

    # ── 读取全文 ────────────────────────────────────────────────────────────

    @staticmethod
    def read_content(entry: IndexEntry, max_len: int = 1500) -> str:
        """读取文档全文（截断）"""
        try:
            with open(entry.filepath, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            return ""

        # 去掉 frontmatter
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()[:max_len]

        return raw.strip()[:max_len]

    # ── 统计 ───────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """各分类条目数"""
        return {k: len(v) for k, v in self._entries.items()}
