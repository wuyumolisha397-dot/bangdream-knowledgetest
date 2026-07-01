"""
缓存模块 (cache.py) 测试
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from cache import CacheDB
from config import CacheConfig
from models import CategoryInfo, CrawlStatus, CrawlStats, PageInfo


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def cache_db(tmp_path: Path) -> CacheDB:
    """创建临时缓存数据库"""
    db_path = tmp_path / "test.db"
    config = CacheConfig(db_path=db_path)
    db = CacheDB(config)
    yield db
    db.close()


def _make_page(title: str = "测试页面", **kwargs) -> PageInfo:
    """快速构建 PageInfo 测试对象"""
    defaults = dict(
        title=title,
        page_id=1,
        revision_id=100,
        updated=datetime(2026, 7, 1),
        categories=["BanG Dream!"],
        wikitext="== 概述 ==\n测试内容",
        markdown="## 概述\n\n测试内容",
        url=f"https://zh.moegirl.org.cn/{title}",
        status=CrawlStatus.COMPLETED,
    )
    defaults.update(kwargs)
    return PageInfo(**defaults)


# ── 页面操作 ────────────────────────────────────────────────────────────────


class TestPageOperations:
    """页面 CRUD 测试"""

    def test_save_and_get_page(self, cache_db: CacheDB) -> None:
        page = _make_page("千早爱音")
        cache_db.save_page(page)

        result = cache_db.get_page("千早爱音")
        assert result is not None
        assert result.title == "千早爱音"
        assert result.revision_id == 100
        assert result.status == CrawlStatus.COMPLETED

    def test_get_nonexistent_page(self, cache_db: CacheDB) -> None:
        result = cache_db.get_page("不存在的页面")
        assert result is None

    def test_update_page(self, cache_db: CacheDB) -> None:
        page = _make_page("测试", revision_id=100)
        cache_db.save_page(page)

        # 更新
        updated = _make_page("测试", revision_id=200)
        cache_db.save_page(updated)

        result = cache_db.get_page("测试")
        assert result is not None
        assert result.revision_id == 200

    def test_page_exists(self, cache_db: CacheDB) -> None:
        page = _make_page("存在页面")
        cache_db.save_page(page)

        assert cache_db.page_exists("存在页面") is True
        assert cache_db.page_exists("不存在页面") is False

    def test_get_page_revision(self, cache_db: CacheDB) -> None:
        page = _make_page("测试", revision_id=42)
        cache_db.save_page(page)

        assert cache_db.get_page_revision("测试") == 42
        assert cache_db.get_page_revision("不存在") == 0

    def test_get_all_page_titles(self, cache_db: CacheDB) -> None:
        for name in ["页面A", "页面B", "页面C"]:
            cache_db.save_page(_make_page(name))

        titles = cache_db.get_all_page_titles()
        assert titles == {"页面A", "页面B", "页面C"}


# ── 分类操作 ────────────────────────────────────────────────────────────────


class TestCategoryOperations:
    """分类 CRUD 测试"""

    def test_save_and_get_category(self, cache_db: CacheDB) -> None:
        cat = CategoryInfo(title="Category:BanG Dream!", depth=0)
        cache_db.save_category(cat)

        result = cache_db.get_category("Category:BanG Dream!")
        assert result is not None
        assert result.title == "Category:BanG Dream!"
        assert result.depth == 0

    def test_mark_category_crawled(self, cache_db: CacheDB) -> None:
        cat = CategoryInfo(title="Category:测试分类", crawled=False)
        cache_db.save_category(cat)

        cache_db.mark_category_crawled("Category:测试分类")

        result = cache_db.get_category("Category:测试分类")
        assert result is not None
        assert result.crawled is True

    def test_get_uncrawled_categories(self, cache_db: CacheDB) -> None:
        cache_db.save_category(CategoryInfo(title="Cat:A", depth=0, crawled=True))
        cache_db.save_category(CategoryInfo(title="Cat:B", depth=1, crawled=False))
        cache_db.save_category(CategoryInfo(title="Cat:C", depth=2, crawled=False))

        uncrawled = cache_db.get_uncrawled_categories()
        assert len(uncrawled) == 2
        # 按深度排序，浅的优先
        assert uncrawled[0].title == "Cat:B"
        assert uncrawled[1].title == "Cat:C"


# ── 统计操作 ────────────────────────────────────────────────────────────────


class TestStatsOperations:
    """统计信息测试"""

    def test_save_and_load_stats(self, cache_db: CacheDB) -> None:
        stats = CrawlStats(
            total_pages=100,
            pages_crawled=90,
            pages_failed=3,
            start_time=datetime(2026, 7, 1, 10, 0, 0),
            end_time=datetime(2026, 7, 1, 11, 0, 0),
        )
        cache_db.save_stats(stats)

        loaded = cache_db.load_stats()
        assert loaded.total_pages == 100
        assert loaded.pages_crawled == 90
        assert loaded.pages_failed == 3

    def test_count_methods(self, cache_db: CacheDB) -> None:
        cache_db.save_page(_make_page("页面1", status=CrawlStatus.COMPLETED))
        cache_db.save_page(_make_page("页面2", status=CrawlStatus.COMPLETED))
        cache_db.save_page(_make_page("页面3", status=CrawlStatus.FAILED))

        assert cache_db.get_total_page_count() == 3
        assert cache_db.get_completed_page_count() == 2
        assert cache_db.get_failed_page_count() == 1


# ── 清理操作 ────────────────────────────────────────────────────────────────


class TestClean:
    """缓存清理测试"""

    def test_clean_empties_database(self, cache_db: CacheDB) -> None:
        cache_db.save_page(_make_page("页面"))
        cache_db.save_category(CategoryInfo(title="Cat:A"))
        cache_db.save_stats(CrawlStats(total_pages=1))

        cache_db.clean()

        assert cache_db.get_total_page_count() == 0
        assert cache_db.get_total_category_count() == 0
