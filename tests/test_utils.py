"""
工具函数 (utils.py) 测试
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config import OutputConfig
from utils import (
    build_page_url,
    count_chinese_chars,
    get_output_filepath,
    map_category_to_dir,
    normalize_category_title,
    sanitize_filename,
    strip_namespace,
    truncate_text,
)


# ── sanitize_filename ───────────────────────────────────────────────────────


class TestSanitizeFilename:
    """文件名清理测试"""

    def test_basic_chinese(self) -> None:
        assert sanitize_filename("千早爱音") == "千早爱音"

    def test_illegal_chars_replaced(self) -> None:
        result = sanitize_filename('A<B>C:D"E/F\\G|H?I*J')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "|" not in result

    def test_consecutive_spaces_merged(self) -> None:
        result = sanitize_filename("a   b   c")
        assert "   " not in result

    def test_trailing_dots_removed(self) -> None:
        result = sanitize_filename("test...")
        assert not result.endswith(".")

    def test_empty_string_default(self) -> None:
        result = sanitize_filename("")
        assert result == "unnamed"

    def test_long_filename_truncated(self) -> None:
        long_name = "a" * 300
        result = sanitize_filename(long_name, max_length=200)
        assert len(result) <= 200


# ── map_category_to_dir ────────────────────────────────────────────────────


class TestMapCategoryToDir:
    """分类→目录映射测试"""

    def test_character_category(self) -> None:
        config = OutputConfig()
        result = map_category_to_dir(["BanG Dream!角色"], config)
        assert result == "角色"

    def test_song_category(self) -> None:
        config = OutputConfig()
        result = map_category_to_dir(["BanG Dream!歌曲"], config)
        assert result == "歌曲"

    def test_band_category(self) -> None:
        config = OutputConfig()
        result = map_category_to_dir(["BanG Dream!乐队"], config)
        assert result == "乐队"

    def test_unknown_category_goes_to_other(self) -> None:
        config = OutputConfig()
        result = map_category_to_dir(["未知分类"], config)
        assert result == "其它"

    def test_empty_categories_goes_to_other(self) -> None:
        config = OutputConfig()
        result = map_category_to_dir([], config)
        assert result == "其它"

    def test_multiple_categories_first_match(self) -> None:
        config = OutputConfig()
        result = map_category_to_dir(["BanG Dream!", "角色"], config)
        # "角色" 在第二个分类中匹配
        assert result == "角色"


# ── normalize_category_title ────────────────────────────────────────────────


class TestNormalizeCategoryTitle:
    """分类标题规范化测试"""

    def test_add_prefix(self) -> None:
        assert normalize_category_title("BanG Dream!") == "Category:BanG Dream!"

    def test_already_has_prefix(self) -> None:
        assert normalize_category_title("Category:BanG Dream!") == "Category:BanG Dream!"


# ── strip_namespace ─────────────────────────────────────────────────────────


class TestStripNamespace:
    """命名空间去除测试"""

    def test_category(self) -> None:
        assert strip_namespace("Category:BanG Dream!") == "BanG Dream!"

    def test_template(self) -> None:
        assert strip_namespace("Template:Infobox") == "Infobox"

    def test_no_namespace(self) -> None:
        assert strip_namespace("千早爱音") == "千早爱音"


# ── build_page_url ──────────────────────────────────────────────────────────


class TestBuildPageUrl:
    """URL 构建测试"""

    def test_basic_url(self) -> None:
        url = build_page_url("千早爱音")
        assert "zh.moegirl.org.cn" in url
        assert "%E5" in url  # URL 编码的中文字符

    def test_custom_base(self) -> None:
        url = build_page_url("Test", base_url="https://example.com")
        assert url.startswith("https://example.com/")


# ── count_chinese_chars ────────────────────────────────────────────────────


class TestCountChars:
    """字符计数测试"""

    def test_basic(self) -> None:
        assert count_chinese_chars("你好世界") == 4

    def test_mixed(self) -> None:
        text = "Hello 世界"
        assert count_chinese_chars(text) == len(text)


# ── truncate_text ───────────────────────────────────────────────────────────


class TestTruncateText:
    """文本截断测试"""

    def test_short_text_unchanged(self) -> None:
        assert truncate_text("短文本", 100) == "短文本"

    def test_long_text_truncated(self) -> None:
        text = "a" * 200
        result = truncate_text(text, 100)
        assert len(result) == 100
        assert result.endswith("...")


# ── get_output_filepath ─────────────────────────────────────────────────────


class TestGetOutputFilepath:
    """输出路径测试"""

    def test_basic_path(self, tmp_path: Path) -> None:
        path = get_output_filepath("测试页面", "角色", tmp_path)
        assert "角色" in str(path)
        assert path.suffix == ".md"

    def test_path_with_suffix(self, tmp_path: Path) -> None:
        path = get_output_filepath("测试页面", "角色", tmp_path, suffix="_1")
        assert "_1.md" in str(path)

    def test_directory_created(self, tmp_path: Path) -> None:
        output = tmp_path / "output"
        path = get_output_filepath("测试", "角色", output)
        assert path.parent.exists()
