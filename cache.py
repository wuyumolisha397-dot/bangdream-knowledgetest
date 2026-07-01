"""
bandori-knowledge 缓存模块

基于 SQLite 的持久化缓存，支持：
- 断点续爬
- 增量更新（基于 RevisionID）
- 爬取状态管理
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import orjson
from loguru import logger

from config import CacheConfig
from models import CategoryInfo, CrawlStatus, CrawlStats, PageInfo


class CacheDB:
    """SQLite 缓存数据库

    三张表：
    - pages: 页面元数据 + 正文缓存
    - categories: 分类信息 + 爬取状态
    - stats: 爬取统计
    """

    def __init__(self, config: CacheConfig) -> None:
        self._db_path = config.db_path
        self._conn: Optional[object] = None
        self._init_db()

    # ── 初始化 ───────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """初始化数据库和表结构"""
        # 确保目录存在
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        import sqlite3

        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

        self._create_tables()
        logger.debug(f"缓存数据库初始化完成: {self._db_path}")

    def _create_tables(self) -> None:
        """创建表结构"""
        assert self._conn is not None

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS pages (
                title        TEXT PRIMARY KEY,
                page_id      INTEGER DEFAULT 0,
                revision_id  INTEGER DEFAULT 0,
                updated      TEXT,
                categories   TEXT DEFAULT '[]',
                wikitext     TEXT DEFAULT '',
                markdown     TEXT DEFAULT '',
                url          TEXT DEFAULT '',
                redirect_target TEXT,
                status       TEXT DEFAULT 'pending',
                error        TEXT,
                created_at   TEXT DEFAULT (datetime('now')),
                updated_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS categories (
                title     TEXT PRIMARY KEY,
                page_id   INTEGER DEFAULT 0,
                depth     INTEGER DEFAULT 0,
                parent    TEXT,
                crawled   INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS stats (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_pages_status ON pages(status);
            CREATE INDEX IF NOT EXISTS idx_pages_revision ON pages(revision_id);
            CREATE INDEX IF NOT EXISTS idx_categories_depth ON categories(depth);
            CREATE INDEX IF NOT EXISTS idx_categories_crawled ON categories(crawled);
        """)
        self._conn.commit()

    # ── 页面操作 ─────────────────────────────────────────────────────────────

    def save_page(self, page: PageInfo) -> None:
        """保存或更新页面信息

        Args:
            page: 页面数据
        """
        assert self._conn is not None

        categories_json = orjson.dumps(
            page.categories
        ).decode("utf-8")
        updated_str = page.updated.isoformat() if page.updated else None

        self._conn.execute(
            """
            INSERT INTO pages (title, page_id, revision_id, updated, categories,
                               wikitext, markdown, url, redirect_target, status, error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(title) DO UPDATE SET
                page_id = excluded.page_id,
                revision_id = excluded.revision_id,
                updated = excluded.updated,
                categories = excluded.categories,
                wikitext = excluded.wikitext,
                markdown = excluded.markdown,
                url = excluded.url,
                redirect_target = excluded.redirect_target,
                status = excluded.status,
                error = excluded.error,
                updated_at = datetime('now')
            """,
            (
                page.title,
                page.page_id,
                page.revision_id,
                updated_str,
                categories_json,
                page.wikitext,
                page.markdown,
                page.url,
                page.redirect_target,
                page.status.value,
                page.error,
            ),
        )
        self._conn.commit()

    def get_page(self, title: str) -> Optional[PageInfo]:
        """获取页面信息

        Args:
            title: 页面标题

        Returns:
            PageInfo 或 None
        """
        assert self._conn is not None

        row = self._conn.execute(
            "SELECT * FROM pages WHERE title = ?", (title,)
        ).fetchone()

        if row is None:
            return None

        categories = orjson.loads(row["categories"]) if row["categories"] else []
        updated = None
        if row["updated"]:
            try:
                updated = datetime.fromisoformat(row["updated"])
            except (ValueError, TypeError):
                pass

        return PageInfo(
            title=row["title"],
            page_id=row["page_id"],
            revision_id=row["revision_id"],
            updated=updated,
            categories=categories,
            wikitext=row["wikitext"],
            markdown=row["markdown"],
            url=row["url"],
            redirect_target=row["redirect_target"],
            status=CrawlStatus(row["status"]),
            error=row["error"],
        )

    def get_page_revision(self, title: str) -> int:
        """获取页面最新 RevisionID（用于增量更新）

        Args:
            title: 页面标题

        Returns:
            RevisionID，0 表示未缓存
        """
        assert self._conn is not None

        row = self._conn.execute(
            "SELECT revision_id FROM pages WHERE title = ?", (title,)
        ).fetchone()
        return row["revision_id"] if row else 0

    def page_exists(self, title: str) -> bool:
        """检查页面是否已缓存

        Args:
            title: 页面标题

        Returns:
            是否存在
        """
        assert self._conn is not None

        row = self._conn.execute(
            "SELECT 1 FROM pages WHERE title = ?", (title,)
        ).fetchone()
        return row is not None

    def get_all_page_titles(self) -> set[str]:
        """获取所有已缓存的页面标题

        Returns:
            标题集合
        """
        assert self._conn is not None

        rows = self._conn.execute("SELECT title FROM pages").fetchall()
        return {row["title"] for row in rows}

    def get_pages_by_status(self, status: CrawlStatus) -> list[PageInfo]:
        """按状态获取页面列表

        Args:
            status: 爬取状态

        Returns:
            页面列表
        """
        assert self._conn is not None

        rows = self._conn.execute(
            "SELECT * FROM pages WHERE status = ?", (status.value,)
        ).fetchall()

        result: list[PageInfo] = []
        for row in rows:
            categories = orjson.loads(row["categories"]) if row["categories"] else []
            updated = None
            if row["updated"]:
                try:
                    updated = datetime.fromisoformat(row["updated"])
                except (ValueError, TypeError):
                    pass

            result.append(
                PageInfo(
                    title=row["title"],
                    page_id=row["page_id"],
                    revision_id=row["revision_id"],
                    updated=updated,
                    categories=categories,
                    wikitext=row["wikitext"],
                    markdown=row["markdown"],
                    url=row["url"],
                    redirect_target=row["redirect_target"],
                    status=CrawlStatus(row["status"]),
                    error=row["error"],
                )
            )
        return result

    # ── 分类操作 ─────────────────────────────────────────────────────────────

    def save_category(self, cat: CategoryInfo) -> None:
        """保存或更新分类信息

        Args:
            cat: 分类数据
        """
        assert self._conn is not None

        self._conn.execute(
            """
            INSERT INTO categories (title, page_id, depth, parent, crawled)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(title) DO UPDATE SET
                page_id = excluded.page_id,
                depth = excluded.depth,
                parent = excluded.parent,
                crawled = excluded.crawled
            """,
            (
                cat.title,
                cat.page_id,
                cat.depth,
                cat.parent,
                1 if cat.crawled else 0,
            ),
        )
        self._conn.commit()

    def get_category(self, title: str) -> Optional[CategoryInfo]:
        """获取分类信息

        Args:
            title: 分类标题

        Returns:
            CategoryInfo 或 None
        """
        assert self._conn is not None

        row = self._conn.execute(
            "SELECT * FROM categories WHERE title = ?", (title,)
        ).fetchone()

        if row is None:
            return None

        return CategoryInfo(
            title=row["title"],
            page_id=row["page_id"],
            depth=row["depth"],
            parent=row["parent"],
            crawled=bool(row["crawled"]),
        )

    def mark_category_crawled(self, title: str) -> None:
        """标记分类为已爬取

        Args:
            title: 分类标题
        """
        assert self._conn is not None

        self._conn.execute(
            "UPDATE categories SET crawled = 1 WHERE title = ?", (title,)
        )
        self._conn.commit()

    def get_uncrawled_categories(self) -> list[CategoryInfo]:
        """获取所有未爬取的分类（按深度排序，浅的优先）

        Returns:
            未爬取的分类列表
        """
        assert self._conn is not None

        rows = self._conn.execute(
            "SELECT * FROM categories WHERE crawled = 0 ORDER BY depth ASC"
        ).fetchall()

        return [
            CategoryInfo(
                title=row["title"],
                page_id=row["page_id"],
                depth=row["depth"],
                parent=row["parent"],
                crawled=bool(row["crawled"]),
            )
            for row in rows
        ]

    def get_all_category_titles(self) -> set[str]:
        """获取所有已发现的分类标题

        Returns:
            标题集合
        """
        assert self._conn is not None

        rows = self._conn.execute("SELECT title FROM categories").fetchall()
        return {row["title"] for row in rows}

    # ── 统计操作 ─────────────────────────────────────────────────────────────

    def save_stats(self, stats: CrawlStats) -> None:
        """保存爬取统计信息

        Args:
            stats: 统计数据
        """
        assert self._conn is not None

        data = stats.to_dict()
        # 额外存储时间字段
        if stats.start_time:
            data["start_time"] = stats.start_time.isoformat()
        if stats.end_time:
            data["end_time"] = stats.end_time.isoformat()

        for key, value in data.items():
            self._conn.execute(
                """
                INSERT INTO stats (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )
        self._conn.commit()

    def load_stats(self) -> CrawlStats:
        """加载上次爬取统计信息

        Returns:
            统计数据
        """
        assert self._conn is not None

        rows = self._conn.execute("SELECT key, value FROM stats").fetchall()
        data = {row["key"]: row["value"] for row in rows}

        stats = CrawlStats()
        if data.get("total_categories"):
            stats.total_categories = int(data["total_categories"])
        if data.get("total_pages"):
            stats.total_pages = int(data["total_pages"])
        if data.get("pages_crawled"):
            stats.pages_crawled = int(data["pages_crawled"])
        if data.get("pages_skipped"):
            stats.pages_skipped = int(data["pages_skipped"])
        if data.get("pages_failed"):
            stats.pages_failed = int(data["pages_failed"])
        if data.get("retries"):
            stats.retries = int(data["retries"])
        if data.get("start_time"):
            try:
                stats.start_time = datetime.fromisoformat(data["start_time"])
            except (ValueError, TypeError):
                pass
        if data.get("end_time"):
            try:
                stats.end_time = datetime.fromisoformat(data["end_time"])
            except (ValueError, TypeError):
                pass

        return stats

    # ── 辅助方法 ─────────────────────────────────────────────────────────────

    def get_total_page_count(self) -> int:
        """获取已缓存页面总数"""
        assert self._conn is not None
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM pages").fetchone()
        return row["cnt"] if row else 0

    def get_total_category_count(self) -> int:
        """获取已发现分类总数"""
        assert self._conn is not None
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM categories").fetchone()
        return row["cnt"] if row else 0

    def get_completed_page_count(self) -> int:
        """获取已完成页面数"""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM pages WHERE status = 'completed'"
        ).fetchone()
        return row["cnt"] if row else 0

    def get_failed_page_count(self) -> int:
        """获取失败页面数"""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM pages WHERE status = 'failed'"
        ).fetchone()
        return row["cnt"] if row else 0

    def clean(self) -> None:
        """清空所有缓存数据"""
        assert self._conn is not None
        self._conn.executescript("""
            DELETE FROM pages;
            DELETE FROM categories;
            DELETE FROM stats;
        """)
        self._conn.commit()
        logger.info("缓存已清空")

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("缓存数据库连接已关闭")
