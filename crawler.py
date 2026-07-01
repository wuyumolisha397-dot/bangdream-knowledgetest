"""
bandori-knowledge 爬虫主入口

使用方式：
    python crawler.py              # 完整爬取
    python crawler.py update       # 增量更新
    python crawler.py clean-cache  # 清空缓存
    python crawler.py stats        # 查看统计
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from cache import CacheDB
from config import AppConfig, DEFAULT_CONFIG
from exporter import Exporter
from mediawiki import MediaWikiClient, should_skip_page
from models import CrawlStats, CrawlStatus, PageInfo
from parser import WikiParser
from utils import ensure_dir

# ── Typer CLI ───────────────────────────────────────────────────────────────

app = typer.Typer(
    name="bandori-knowledge",
    help="BanG Dream! 知识库自动构建工具 — 从萌娘百科爬取并导出 Markdown",
    add_completion=False,
)

console = Console(force_terminal=True)
# 修复 Windows GBK 编码问题
import locale
if sys.platform == "win32":
    try:
        locale.setlocale(locale.LC_ALL, "zh_CN.UTF-8")
    except locale.Error:
        pass
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── 日志配置 ─────────────────────────────────────────────────────────────────


def setup_logging(config: AppConfig) -> None:
    """配置 loguru 日志

    输出到：
    - 彩色控制台
    - logs/crawler.log 文件
    """
    # 移除默认 handler
    logger.remove()

    # 控制台：彩色输出
    logger.add(
        sys.stderr,
        level=config.log.log_level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件：纯文本 + 轮转
    ensure_dir(config.log.log_dir)
    logger.add(
        str(config.log.log_dir / config.log.log_file),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=config.log.rotation,
        retention=config.log.retention,
        encoding="utf-8",
    )


# ── 爬虫核心 ────────────────────────────────────────────────────────────────


class BandoriCrawler:
    """BanG Dream! 知识库爬虫

    编排 MediaWiki API 客户端、缓存、解析器、导出器，
    实现完整的爬取-解析-导出流水线。
    """

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self._config = config or DEFAULT_CONFIG
        self._cache = CacheDB(self._config.cache)
        self._stats = CrawlStats()
        self._parser = WikiParser(self._config.output)
        self._exporter = Exporter(self._config.output, self._parser)
        self._shutdown = False

        # 注册信号处理（优雅退出）
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_signal)
        except (RuntimeError, NotImplementedError):
            pass  # Windows 下 add_signal_handler 不可用，使用其他方式

    def _handle_signal(self) -> None:
        """处理中断信号（Ctrl+C）"""
        if self._shutdown:
            logger.warning("收到第二次中断，强制退出")
            sys.exit(1)
        self._shutdown = True
        logger.info("收到中断信号，正在优雅退出（缓存已保存，可断点续爬）...")

    # ── 完整爬取 ─────────────────────────────────────────────────────────────

    async def crawl(self) -> CrawlStats:
        """完整爬取流程

        1. 发现所有分类
        2. 发现所有页面
        3. 获取页面内容
        4. 解析为 Markdown
        5. 导出文件

        Returns:
            爬取统计
        """
        self._stats = CrawlStats(start_time=datetime.now())
        self._shutdown = False

        console.print(
            Panel.fit(
                "[bold cyan]BanG Dream! 知识库爬虫[/bold cyan]\n"
                f"数据源: {self._config.api.base_url}\n"
                f"起始分类: {self._config.api.root_category}",
                border_style="cyan",
            )
        )

        async with MediaWikiClient(
            self._config.api, self._config.network, self._stats
        ) as client:
            # ── 阶段 1: 发现页面 ─────────────────────────────────────────────
            console.print("\n[bold yellow]阶段 1/3: 发现页面...[/bold yellow]")

            discovered_pages: list[tuple[str, int]] = []  # (title, depth)
            discovered_categories: set[str] = set()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed} 个页面"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("发现中...", total=None)

                async for member, depth in client.discover_pages(
                    self._config.api.root_category,
                    max_depth=10,
                ):
                    if self._shutdown:
                        break
                    discovered_pages.append((member.title, depth))
                    progress.update(task, completed=len(discovered_pages))

            self._stats.total_pages = len(discovered_pages)
            logger.info(f"发现 {len(discovered_pages)} 个页面")

            if self._shutdown:
                self._stats.end_time = datetime.now()
                self._cache.save_stats(self._stats)
                console.print("[yellow]爬取已中断，缓存已保存[/yellow]")
                return self._stats

            # ── 阶段 2: 获取页面内容 ─────────────────────────────────────────
            console.print(f"\n[bold yellow]阶段 2/3: 获取页面内容 ({len(discovered_pages)} 页)...[/bold yellow]")

            pages: list[PageInfo] = []

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("获取中...", total=len(discovered_pages))

                # 使用信号量控制并发（逐页获取，避免 exlimit 问题）
                sem = asyncio.Semaphore(self._config.network.max_concurrent)

                async def fetch_one(title: str) -> Optional[PageInfo]:
                    async with sem:
                        try:
                            return await client.get_page_content(title)
                        except Exception as e:
                            logger.error(f"获取页面失败 [{title}]: {e}")
                            self._stats.pages_failed += 1
                            return None

                # 分批创建任务，避免一次创建过多
                batch_size = 50
                for i in range(0, len(discovered_pages), batch_size):
                    if self._shutdown:
                        break
                    batch_titles = [title for title, _ in discovered_pages[i:i + batch_size]]
                    tasks = [fetch_one(t) for t in batch_titles]
                    results = await asyncio.gather(*tasks)
                    for page in results:
                        if page and not page.is_redirect:
                            # 获取期过滤：基于分类标签 + 正文内容判断
                            filter_cfg = self._config.filter
                            skip, reason = should_skip_page(
                                page.title, page.categories, page.wikitext, filter_cfg
                            )
                            if skip:
                                logger.info(f"过滤页面: {page.title} ({reason})")
                                self._stats.pages_filtered += 1
                                # 可选：保存到缓存标记为已过滤，避免重复抓取
                                page.status = CrawlStatus.SKIPPED
                                self._cache.save_page(page)
                                progress.update(task, advance=1)
                                continue
                            pages.append(page)
                            self._cache.save_page(page)
                        progress.update(task, advance=1)

            self._stats.pages_crawled = len(pages)
            logger.info(f"成功获取 {len(pages)} 个页面")

            if self._shutdown:
                self._stats.end_time = datetime.now()
                self._cache.save_stats(self._stats)
                console.print("[yellow]爬取已中断，缓存已保存[/yellow]")
                return self._stats

            # ── 阶段 3: 导出 Markdown ────────────────────────────────────────
            console.print(f"\n[bold yellow]阶段 3/3: 导出 Markdown ({len(pages)} 页)...[/bold yellow]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("导出中...", total=len(pages))

                for idx, page in enumerate(pages):
                    try:
                        # 标记状态
                        page.status = CrawlStatus.COMPLETED
                        self._exporter.export_page(page)
                        self._cache.save_page(page)
                    except Exception as e:
                        logger.error(f"导出失败 [{page.title}]: {e}")
                        page.status = CrawlStatus.FAILED
                        page.error = str(e)
                        self._cache.save_page(page)
                        self._stats.pages_failed += 1

                    progress.update(task, completed=idx + 1)

            # 导出统计和索引
            self._stats.end_time = datetime.now()
            self._cache.save_stats(self._stats)
            self._exporter.export_stats(self._stats, self._config.output.output_dir)
            self._exporter.export_index(pages, self._config.output.output_dir)

        # 显示结果
        self._print_summary()

        return self._stats

    # ── 增量更新 ─────────────────────────────────────────────────────────────

    async def update(self) -> CrawlStats:
        """增量更新

        仅下载 RevisionID 发生变化的页面。
        """
        self._stats = CrawlStats(start_time=datetime.now())
        self._shutdown = False

        console.print(
            Panel.fit(
                "[bold cyan]BanG Dream! 增量更新[/bold cyan]",
                border_style="cyan",
            )
        )

        # 获取已缓存的页面
        cached_pages = self._cache.get_pages_by_status(CrawlStatus.COMPLETED)

        if not cached_pages:
            console.print("[yellow]缓存为空，执行完整爬取[/yellow]")
            return await self.crawl()

        console.print(f"缓存中有 {len(cached_pages)} 个页面，检查更新...")

        async with MediaWikiClient(
            self._config.api, self._config.network, self._stats
        ) as client:
            updated_pages: list[PageInfo] = []

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("({task.completed}/{task.total})"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("检查更新...", total=len(cached_pages))

                for cached_page in cached_pages:
                    if self._shutdown:
                        break

                    # 获取最新 RevisionID
                    fresh_page = await client.get_page_content(cached_page.title)

                    if fresh_page is None:
                        progress.update(task, advance=1)
                        continue

                    # 比较 RevisionID
                    if fresh_page.revision_id <= cached_page.revision_id:
                        # 未变更
                        self._stats.pages_skipped += 1
                        progress.update(task, advance=1)
                        continue

                    # 有更新 — 先检查过滤规则
                    filter_cfg = self._config.filter
                    skip, reason = should_skip_page(
                        fresh_page.title, fresh_page.categories, fresh_page.wikitext, filter_cfg
                    )
                    if skip:
                        logger.info(f"过滤页面（已更新但被跳过）: {fresh_page.title} ({reason})")
                        self._stats.pages_filtered += 1
                        progress.update(task, advance=1)
                        continue

                    logger.info(f"页面已更新: {cached_page.title} (rev {cached_page.revision_id} → {fresh_page.revision_id})")
                    updated_pages.append(fresh_page)
                    progress.update(task, advance=1)

            # 导出更新的页面
            if updated_pages:
                console.print(f"\n[bold green]{len(updated_pages)} 个页面有更新，重新导出...[/bold green]")

                for page in updated_pages:
                    try:
                        page.status = CrawlStatus.COMPLETED
                        self._exporter.export_page(page)
                        self._cache.save_page(page)
                        self._stats.pages_crawled += 1
                    except Exception as e:
                        logger.error(f"导出失败 [{page.title}]: {e}")
                        self._stats.pages_failed += 1
            else:
                console.print("[green]所有页面均为最新，无需更新[/green]")

        self._stats.end_time = datetime.now()
        self._cache.save_stats(self._stats)

        self._print_summary()
        return self._stats

    # ── 统计显示 ─────────────────────────────────────────────────────────────

    def show_stats(self) -> None:
        """显示缓存统计信息"""
        table = Table(title="缓存统计", show_header=True, header_style="bold magenta")
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green", justify="right")

        table.add_row("已缓存页面数", str(self._cache.get_total_page_count()))
        table.add_row("已完成页面数", str(self._cache.get_completed_page_count()))
        table.add_row("失败页面数", str(self._cache.get_failed_page_count()))
        table.add_row("已发现分类数", str(self._cache.get_total_category_count()))

        # 上次统计
        last_stats = self._cache.load_stats()
        if last_stats.start_time:
            table.add_row("上次爬取时间", last_stats.start_time.strftime("%Y-%m-%d %H:%M:%S"))
        if last_stats.elapsed_seconds > 0:
            table.add_row("上次耗时", f"{last_stats.elapsed_seconds:.1f} 秒")
            table.add_row("上次速率", f"{last_stats.pages_per_second:.2f} 页/秒")

        console.print(table)

    # ── 结果摘要 ─────────────────────────────────────────────────────────────

    def _print_summary(self) -> None:
        """打印爬取结果摘要"""
        stats = self._stats

        table = Table(title="爬取结果", show_header=True, header_style="bold green")
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green", justify="right")

        table.add_row("发现页面", str(stats.total_pages))
        table.add_row("成功爬取", str(stats.pages_crawled))
        table.add_row("跳过（未变更）", str(stats.pages_skipped))
        table.add_row("过滤（非内容）", str(stats.pages_filtered))
        table.add_row("失败", str(stats.pages_failed))
        table.add_row("重试次数", str(stats.retries))
        table.add_row("耗时", f"{stats.elapsed_seconds:.1f} 秒")
        table.add_row("速率", f"{stats.pages_per_second:.2f} 页/秒")
        table.add_row("导出文件", str(self._exporter.exported_count))

        console.print(table)

    # ── 清理 ─────────────────────────────────────────────────────────────────

    def clean_cache(self) -> None:
        """清空缓存数据库"""
        self._cache.clean()
        console.print("[green]缓存已清空[/green]")

    def close(self) -> None:
        """关闭资源"""
        self._cache.close()


# ── CLI 命令 ────────────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def main(
    update: bool = typer.Option(False, "--update", "-u", help="增量更新模式"),
    clean_cache: bool = typer.Option(False, "--clean-cache", help="清空缓存"),
    stats: bool = typer.Option(False, "--stats", "-s", help="查看统计"),
) -> None:
    """BanG Dream! 知识库爬虫 — 从萌娘百科自动构建 AstrBot 知识库"""
    config = AppConfig.from_env()
    setup_logging(config)

    crawler = BandoriCrawler(config)

    try:
        if clean_cache:
            crawler.clean_cache()
            return

        if stats:
            crawler.show_stats()
            return

        if update:
            asyncio.run(crawler.update())
        else:
            asyncio.run(crawler.crawl())
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.exception(f"爬虫异常: {e}")
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(code=1)
    finally:
        crawler.close()


# ── 快捷子命令 ──────────────────────────────────────────────────────────────


@app.command()
def update() -> None:
    """增量更新"""
    config = AppConfig.from_env()
    setup_logging(config)
    crawler = BandoriCrawler(config)
    try:
        asyncio.run(crawler.update())
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.exception(f"爬虫异常: {e}")
        raise typer.Exit(code=1)
    finally:
        crawler.close()


@app.command(name="clean-cache")
def clean_cache_cmd() -> None:
    """清空缓存"""
    config = AppConfig.from_env()
    setup_logging(config)
    crawler = BandoriCrawler(config)
    try:
        crawler.clean_cache()
    finally:
        crawler.close()


@app.command()
def stats() -> None:
    """查看统计"""
    config = AppConfig.from_env()
    setup_logging(config)
    crawler = BandoriCrawler(config)
    try:
        crawler.show_stats()
    finally:
        crawler.close()


# ── Windows 事件循环策略 ────────────────────────────────────────────────────

if sys.platform == "win32":
    # Windows 下需要使用 ProactorEventLoop 以支持信号处理
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── 入口 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
