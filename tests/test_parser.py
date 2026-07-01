"""
Wiki 解析器 (parser.py) 测试
"""

from __future__ import annotations

import pytest

from models import PageInfo, CrawlStatus, SplitPage
from parser import WikiParser
from config import OutputConfig


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def parser() -> WikiParser:
    return WikiParser(OutputConfig())


def _make_page(title: str, wikitext: str) -> PageInfo:
    """快速构建 PageInfo 测试对象"""
    return PageInfo(
        title=title,
        wikitext=wikitext,
        url=f"https://zh.moegirl.org.cn/{title}",
        status=CrawlStatus.PENDING,
    )


# ── 基础文本 ────────────────────────────────────────────────────────────────


class TestBasicText:
    """纯文本解析测试"""

    def test_plain_text(self, parser: WikiParser) -> None:
        page = _make_page("测试", "这是一段纯文本。")
        result = parser.parse(page)
        assert "这是一段纯文本" in result

    def test_bold_text(self, parser: WikiParser) -> None:
        page = _make_page("测试", "这是'''加粗'''文本。")
        result = parser.parse(page)
        assert "**加粗**" in result

    def test_italic_text(self, parser: WikiParser) -> None:
        page = _make_page("测试", "这是''斜体''文本。")
        result = parser.parse(page)
        assert "*斜体*" in result

    def test_empty_wikitext(self, parser: WikiParser) -> None:
        page = _make_page("空页面", "")
        result = parser.parse(page)
        assert result == ""


# ── 标题 ─────────────────────────────────────────────────────────────────────


class TestHeadings:
    """标题解析测试"""

    def test_h2(self, parser: WikiParser) -> None:
        page = _make_page("测试", "== 二级标题 ==\n正文内容")
        result = parser.parse(page)
        assert "## 二级标题" in result

    def test_h3(self, parser: WikiParser) -> None:
        page = _make_page("测试", "=== 三级标题 ===\n正文内容")
        result = parser.parse(page)
        assert "### 三级标题" in result

    def test_h4(self, parser: WikiParser) -> None:
        page = _make_page("测试", "==== 四级标题 ====\n正文内容")
        result = parser.parse(page)
        assert "#### 四级标题" in result

    def test_multiple_headings(self, parser: WikiParser) -> None:
        wikitext = """
== 概述 ==
概述内容

== 详细 ==
=== 子节 ===
详细内容
"""
        page = _make_page("测试", wikitext)
        result = parser.parse(page)
        assert "## 概述" in result
        assert "## 详细" in result
        assert "### 子节" in result


# ── 链接 ─────────────────────────────────────────────────────────────────────


class TestLinks:
    """链接解析测试"""

    def test_internal_link(self, parser: WikiParser) -> None:
        page = _make_page("测试", "参见[[千早爱音]]。")
        result = parser.parse(page)
        assert "千早爱音" in result

    def test_internal_link_with_display(self, parser: WikiParser) -> None:
        page = _make_page("测试", "参见[[千早爱音|爱音]]。")
        result = parser.parse(page)
        assert "爱音" in result

    def test_category_link_removed(self, parser: WikiParser) -> None:
        page = _make_page("测试", "正文[[Category:BanG Dream!]]")
        result = parser.parse(page)
        assert "Category:" not in result

    def test_file_link_removed(self, parser: WikiParser) -> None:
        page = _make_page("测试", "正文[[File:Test.jpg|thumb]]")
        result = parser.parse(page)
        assert "File:" not in result


# ── 模板清理 ─────────────────────────────────────────────────────────────────


class TestTemplateRemoval:
    """模板清理测试"""

    def test_infobox_removed(self, parser: WikiParser) -> None:
        page = _make_page("测试", "{{Infobox|name=测试}}正文")
        result = parser.parse(page)
        assert "Infobox" not in result
        assert "正文" in result

    def test_navbox_removed(self, parser: WikiParser) -> None:
        page = _make_page("测试", "正文{{Navbox|标题=导航}}结尾")
        result = parser.parse(page)
        assert "Navbox" not in result
        assert "正文" in result

    def test_ref_removed(self, parser: WikiParser) -> None:
        page = _make_page("测试", "正文<ref>引用内容</ref>结尾")
        result = parser.parse(page)
        assert "<ref>" not in result
        assert "引用内容" not in result
        assert "正文" in result
        assert "结尾" in result


# ── HTML 注释 ────────────────────────────────────────────────────────────────


class TestComments:
    """HTML 注释清理测试"""

    def test_html_comment_removed(self, parser: WikiParser) -> None:
        page = _make_page("测试", "正文<!-- 这是一条注释 -->结尾")
        result = parser.parse(page)
        assert "这是一条注释" not in result
        assert "正文" in result
        assert "结尾" in result


# ── 长页面拆分 ──────────────────────────────────────────────────────────────


class TestSplitLongPage:
    """长页面拆分测试"""

    def test_short_page_not_split(self, parser: WikiParser) -> None:
        """短页面不拆分"""
        page = _make_page("短页面", "这是一段短文本。")
        markdown = "这是一段短文本。"
        result = parser.split_long_page(page, markdown)
        assert len(result) == 1
        assert result[0].title == "短页面"

    def test_long_page_split_by_h2(self, parser: WikiParser) -> None:
        """长页面按 H2 拆分"""
        long_text = "前言内容 " * 500  # ~2500 字
        section1 = "## 概述\n\n" + "概述内容 " * 500
        section2 = "## 详细\n\n" + "详细内容 " * 500
        markdown = long_text + "\n\n" + section1 + "\n\n" + section2

        page = _make_page("长页面", "")
        result = parser.split_long_page(page, markdown)
        assert len(result) >= 2

    def test_no_headings_no_split(self, parser: WikiParser) -> None:
        """无标题的长页面不拆分"""
        markdown = "这是一段非常长的文本。" * 2000  # ~18000 字
        page = _make_page("无标题长页面", "")
        result = parser.split_long_page(page, markdown)
        # 无法按标题拆分，整体输出
        assert len(result) == 1


# ── 后处理 ──────────────────────────────────────────────────────────────────


class TestPostProcess:
    """后处理测试"""

    def test_multiple_blank_lines_merged(self, parser: WikiParser) -> None:
        page = _make_page("测试", "正文\n\n\n\n\n结尾")
        result = parser.parse(page)
        # 最多两个连续换行
        assert "\n\n\n" not in result

    def test_lua_residue_removed(self, parser: WikiParser) -> None:
        page = _make_page("测试", "正文{{#invoke:Test|main}}结尾")
        result = parser.parse(page)
        assert "#invoke" not in result


# ── 降级清理 ─────────────────────────────────────────────────────────────────


class TestFallbackClean:
    """降级清理测试"""

    def test_fallback_basic(self, parser: WikiParser) -> None:
        text = "正文[[Category:测试]][[File:A.jpg]]结尾"
        result = parser._fallback_clean(text)
        assert "Category:" not in result
        assert "File:" not in result
        assert "正文" in result
