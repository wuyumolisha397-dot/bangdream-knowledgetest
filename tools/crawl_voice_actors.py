"""
抓取 BanG Dream! 相关声优页面

单独运行此脚本以从已有缓存中发现声优并抓取。
"""

import asyncio
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import orjson
import yaml
from loguru import logger

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import AppConfig
from mediawiki import MediaWikiClient
from parser import WikiParser
from exporter import Exporter
from models import CrawlStats, CrawlStatus, PageInfo
from utils import sanitize_filename, get_output_filepath


async def main() -> None:
    config = AppConfig.from_env()

    # 从缓存读取声优名
    conn = sqlite3.connect(str(config.cache.db_path))
    cur = conn.execute("SELECT categories FROM pages")
    va_names: set[str] = set()
    for (cats_json,) in cur:
        if not cats_json:
            continue
        try:
            cats = orjson.loads(cats_json)
        except Exception:
            continue
        for cat in cats:
            if "配音角色" in cat:
                name = cat.replace("配音角色", "").strip()
                if name and len(name) >= 2:
                    va_names.add(name)
    conn.close()

    logger.info(f"发现 {len(va_names)} 位声优需要抓取")
    names = sorted(va_names)
    for n in names:
        logger.debug(f"  {n}")

    stats = CrawlStats(start_time=datetime.now())
    parser = WikiParser(config.output)
    exporter = Exporter(config.output, parser)

    async with MediaWikiClient(config.api, config.network, stats) as client:
        for idx, name in enumerate(names, 1):
            logger.info(f"[{idx}/{len(names)}] 获取: {name}")
            try:
                page = await client.get_page_content(name)
                if page is None:
                    logger.warning(f"页面不存在: {name}")
                    continue

                # 只保留 BanG Dream! 相关分类
                page.categories.append("BanG Dream!")
                page.categories.append("声优")

                # 解析 & 导出
                markdown = parser.parse(page)
                page.markdown = markdown

                # 强制输出到 声优 目录
                output_path = get_output_filepath(
                    title=page.display_title,
                    sub_dir="声优",
                    output_dir=config.output.output_dir,
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # 生成 frontmatter + 内容
                frontmatter = {
                    "title": page.display_title,
                    "url": page.url,
                    "revision": page.revision_id,
                    "updated": page.updated.strftime("%Y-%m-%d") if page.updated else "",
                    "categories": page.categories,
                }
                fm_str = yaml.dump(
                    frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False
                )
                content = f"---\n{fm_str}---\n\n# {page.display_title}\n\n{markdown}\n"
                output_path.write_text(content, encoding="utf-8")
                logger.info(f"  ✓ {len(markdown)} 字 → {output_path.name}")

            except Exception as e:
                logger.error(f"  ✗ 失败: {e}")

    logger.info(f"完成! 输出在 {config.output.output_dir / '声优'}/")


if __name__ == "__main__":
    asyncio.run(main())
