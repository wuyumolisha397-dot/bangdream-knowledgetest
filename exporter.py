"""
bandori-knowledge 导出模块

负责将解析后的页面数据导出为 Markdown 文件，
包括 YAML frontmatter 生成、目录分类、长页面拆分。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import orjson
import yaml
from loguru import logger

from config import OutputConfig
from models import CrawlStats, PageInfo, SplitPage
from parser import WikiParser
from utils import ensure_dir, get_output_filepath, map_category_to_dir


class Exporter:
    """Markdown 文件导出器

    职责：
    - 生成 YAML frontmatter
    - 按分类确定输出子目录
    - 长页面拆分
    - 写入 .md 文件
    - 导出爬取统计
    """

    def __init__(
        self,
        config: Optional[OutputConfig] = None,
        parser: Optional[WikiParser] = None,
    ) -> None:
        self._config = config or OutputConfig()
        self._parser = parser or WikiParser(self._config)
        self._exported_count: int = 0
        self._skipped_count: int = 0

    # ── 导出入口 ─────────────────────────────────────────────────────────────

    def export_page(self, page: PageInfo) -> list[Path]:
        """导出单个页面为 Markdown 文件

        流程：
        1. 解析 wikitext → Markdown
        2. 检查长度，必要时拆分
        3. 生成 frontmatter
        4. 写入文件

        Args:
            page: 页面信息

        Returns:
            写入的文件路径列表
        """
        # 跳过重定向页（不输出文件）
        if page.is_redirect:
            logger.debug(f"跳过重定向页: {page.title} → {page.redirect_target}")
            self._skipped_count += 1
            return []

        # 解析 wikitext
        markdown = self._parser.parse(page)

        if not markdown or not markdown.strip():
            logger.debug(f"页面正文为空，跳过: {page.title}")
            self._skipped_count += 1
            return []

        # 更新 page 的 markdown 字段
        page.markdown = markdown

        # 确定输出子目录
        sub_dir = map_category_to_dir(page.categories, self._config)

        # 检查是否需要拆分
        split_pages = self._parser.split_long_page(page, markdown)

        output_paths: list[Path] = []

        for idx, split in enumerate(split_pages):
            if len(split_pages) == 1:
                # 不拆分
                suffix = ""
            else:
                suffix = f"_{idx + 1}"

            # 生成 frontmatter
            frontmatter = self._build_frontmatter(page, split)

            # 组装完整文件内容
            content = f"---\n{frontmatter}---\n\n# {split.title}\n\n{split.markdown}\n"

            # 写入文件
            filepath = get_output_filepath(
                title=page.display_title,
                sub_dir=sub_dir,
                output_dir=self._config.output_dir,
                suffix=suffix,
            )
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")

            output_paths.append(filepath)
            self._exported_count += 1

        logger.debug(f"导出页面: {page.title} → {len(output_paths)} 个文件")
        return output_paths

    def export_pages(self, pages: list[PageInfo]) -> list[Path]:
        """批量导出页面

        Args:
            pages: 页面列表

        Returns:
            所有写入的文件路径
        """
        all_paths: list[Path] = []

        for page in pages:
            try:
                paths = self.export_page(page)
                all_paths.extend(paths)
            except Exception as e:
                logger.error(f"导出页面失败 [{page.title}]: {e}")

        return all_paths

    # ── Frontmatter ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_frontmatter(page: PageInfo, split: SplitPage) -> str:
        """构建 YAML frontmatter

        格式：
        ---
        title: 千早爱音
        url: https://zh.moegirl.org.cn/千早爱音
        revision: 123456
        updated: 2026-07-01
        categories:
          - BanG Dream!
          - MyGO!!!!!
        ---

        Args:
            page: 页面信息
            split: 拆分子页面

        Returns:
            YAML frontmatter 字符串（含 --- 分隔符）
        """
        # 更新日期格式化
        updated_str = ""
        if page.updated:
            if hasattr(page.updated, "strftime"):
                updated_str = page.updated.strftime("%Y-%m-%d")
            else:
                updated_str = str(page.updated)[:10]

        data: dict = {
            "title": split.title,
            "url": page.url,
        }

        if page.revision_id:
            data["revision"] = page.revision_id

        if updated_str:
            data["updated"] = updated_str

        if page.categories:
            data["categories"] = page.categories

        # 使用 yaml.dump，确保中文不转义
        frontmatter = yaml.dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

        return frontmatter

    # ── 统计导出 ─────────────────────────────────────────────────────────────

    def export_stats(self, stats: CrawlStats, output_dir: Path) -> Path:
        """导出爬取统计为 JSON 文件

        Args:
            stats: 统计数据
            output_dir: 输出目录

        Returns:
            统计文件路径
        """
        ensure_dir(output_dir)
        stats_path = output_dir / "_crawl_stats.json"

        data = stats.to_dict()
        data["exported_files"] = self._exported_count
        data["skipped_files"] = self._skipped_count

        json_bytes = orjson.dumps(data, option=orjson.OPT_INDENT_2)
        stats_path.write_bytes(json_bytes)

        logger.info(f"统计信息已导出: {stats_path}")
        return stats_path

    def export_index(self, pages: list[PageInfo], output_dir: Path) -> Path:
        """导出页面索引为 JSON 文件（方便 AstrBot 检索）

        Args:
            pages: 已完成的页面列表
            output_dir: 输出目录

        Returns:
            索引文件路径
        """
        ensure_dir(output_dir)
        index_path = output_dir / "_index.json"

        entries: list[dict] = []
        for page in pages:
            if page.is_redirect or not page.markdown:
                continue

            sub_dir = map_category_to_dir(page.categories, self._config)
            entries.append({
                "title": page.display_title,
                "url": page.url,
                "categories": page.categories,
                "revision": page.revision_id,
                "updated": page.updated.strftime("%Y-%m-%d") if page.updated else None,
                "directory": sub_dir,
            })

        json_bytes = orjson.dumps(entries, option=orjson.OPT_INDENT_2)
        index_path.write_bytes(json_bytes)

        logger.info(f"索引已导出: {index_path} ({len(entries)} 条)")
        return index_path

    # ── 清理 ─────────────────────────────────────────────────────────────────

    @staticmethod
    def clean_output(output_dir: Path) -> None:
        """清空输出目录

        Args:
            output_dir: 输出目录
        """
        import shutil

        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"输出目录已清空: {output_dir}")

    # ── 统计 ─────────────────────────────────────────────────────────────────

    @property
    def exported_count(self) -> int:
        """已导出文件数"""
        return self._exported_count

    @property
    def skipped_count(self) -> int:
        """跳过文件数"""
        return self._skipped_count
