"""
导出模块 (exporter.py) 测试
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from config import OutputConfig
from exporter import Exporter
from models import CrawlStats, CrawlStatus, PageInfo
from parser import WikiParser


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """创建临时输出目录"""
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.fixture
def exporter(output_dir: Path) -> Exporter:
    """创建导出器实例"""
    config = OutputConfig(output_dir=output_dir)
    return Exporter(config)


def _make_page(
    title: str = "千早爱音",
    categories: list[str] | None = None,
    wikitext: str = "== 概述 ==\n这是千早爱音的页面。",
) -> PageInfo:
    """快速构建 PageInfo 测试对象"""
    return PageInfo(
        title=title,
        revision_id=12345,
        updated=datetime(2026, 7, 1),
        categories=categories or ["BanG Dream!", "MyGO!!!!!"],
        wikitext=wikitext,
        url=f"https://zh.moegirl.org.cn/{title}",
        status=CrawlStatus.COMPLETED,
    )


# ── 单页导出 ────────────────────────────────────────────────────────────────


class TestExportPage:
    """单页导出测试"""

    def test_export_basic_page(self, exporter: Exporter, output_dir: Path) -> None:
        page = _make_page()
        paths = exporter.export_page(page)

        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].suffix == ".md"

        content = paths[0].read_text(encoding="utf-8")
        assert "---" in content  # frontmatter
        assert "千早爱音" in content
        assert "概述" in content

    def test_export_redirect_skipped(self, exporter: Exporter) -> None:
        page = _make_page()
        page.redirect_target = "目标页面"

        paths = exporter.export_page(page)
        assert len(paths) == 0

    def test_export_empty_page_skipped(self, exporter: Exporter) -> None:
        page = _make_page(wikitext="")
        paths = exporter.export_page(page)
        assert len(paths) == 0

    def test_export_with_categories(self, exporter: Exporter, output_dir: Path) -> None:
        page = _make_page(categories=["BanG Dream!", "角色"])
        paths = exporter.export_page(page)

        assert len(paths) == 1
        # 应该在 "角色" 目录下
        assert "角色" in str(paths[0])

    def test_export_uncategorized_goes_to_other(
        self, exporter: Exporter, output_dir: Path
    ) -> None:
        page = _make_page(categories=["未知分类"])
        paths = exporter.export_page(page)

        assert len(paths) == 1
        assert "其它" in str(paths[0])


# ── Frontmatter ─────────────────────────────────────────────────────────────


class TestFrontmatter:
    """YAML frontmatter 测试"""

    def test_frontmatter_has_title(self, exporter: Exporter, output_dir: Path) -> None:
        page = _make_page()
        paths = exporter.export_page(page)
        content = paths[0].read_text(encoding="utf-8")

        assert "title:" in content

    def test_frontmatter_has_url(self, exporter: Exporter, output_dir: Path) -> None:
        page = _make_page()
        paths = exporter.export_page(page)
        content = paths[0].read_text(encoding="utf-8")

        assert "url:" in content
        assert "zh.moegirl.org.cn" in content

    def test_frontmatter_has_revision(self, exporter: Exporter, output_dir: Path) -> None:
        page = _make_page()
        paths = exporter.export_page(page)
        content = paths[0].read_text(encoding="utf-8")

        assert "revision:" in content

    def test_frontmatter_has_updated(self, exporter: Exporter, output_dir: Path) -> None:
        page = _make_page()
        paths = exporter.export_page(page)
        content = paths[0].read_text(encoding="utf-8")

        assert "updated:" in content
        assert "2026" in content

    def test_frontmatter_has_categories(
        self, exporter: Exporter, output_dir: Path
    ) -> None:
        page = _make_page()
        paths = exporter.export_page(page)
        content = paths[0].read_text(encoding="utf-8")

        assert "categories:" in content


# ── 批量导出 ────────────────────────────────────────────────────────────────


class TestExportPages:
    """批量导出测试"""

    def test_export_multiple_pages(
        self, exporter: Exporter, output_dir: Path
    ) -> None:
        pages = [
            _make_page("页面A", categories=["角色"]),
            _make_page("页面B", categories=["歌曲"]),
            _make_page("页面C", categories=["未知"]),
        ]

        paths = exporter.export_pages(pages)
        assert len(paths) == 3

    def test_export_stats(self, exporter: Exporter, output_dir: Path) -> None:
        stats = CrawlStats(total_pages=10, pages_crawled=9)
        stats_path = exporter.export_stats(stats, output_dir)

        assert stats_path.exists()
        assert stats_path.name == "_crawl_stats.json"

    def test_export_index(self, exporter: Exporter, output_dir: Path) -> None:
        pages = [
            _make_page("页面A", categories=["角色"]),
            _make_page("页面B", categories=["歌曲"]),
        ]

        index_path = exporter.export_index(pages, output_dir)
        assert index_path.exists()
        assert index_path.name == "_index.json"


# ── 清理 ────────────────────────────────────────────────────────────────────


class TestCleanOutput:
    """输出目录清理测试"""

    def test_clean_output(self, output_dir: Path) -> None:
        # 创建一些文件
        (output_dir / "test.md").write_text("test", encoding="utf-8")

        Exporter.clean_output(output_dir)

        assert output_dir.exists()
        assert not (output_dir / "test.md").exists()
