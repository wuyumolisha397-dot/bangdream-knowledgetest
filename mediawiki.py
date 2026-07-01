"""
bandori-knowledge MediaWiki 客户端模块

萌娘百科 API 限制较多（list=categorymembers / action=raw 均被封），
因此采用混合策略：
- 分类成员：从分类 HTML 页面解析
- 页面元数据：API prop=info + prop=categories
- 页面正文：API prop=extracts (explaintext) → 已清理的 Wiki 格式文本
"""

from __future__ import annotations

import asyncio
import random
import re
from datetime import datetime
from typing import AsyncIterator, Optional
from urllib.parse import quote, unquote

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
)

from config import APIConfig, FilterConfig, NetworkConfig
from models import CrawlStats, CategoryMember, PageType, PageInfo


# ── 页面过滤器 ──────────────────────────────────────────────────────────────

# 预编译标题正则（FilterConfig 中的 skip_title_patterns）
_SKIP_TITLE_RE = re.compile(
    "|".join(f"(?:{p})" for p in FilterConfig().skip_title_patterns),
    re.IGNORECASE,
)

# 预编译内容正则（FilterConfig 中的 skip_content_patterns）
_SKIP_CONTENT_RE = re.compile(
    "|".join(f"(?:{p})" for p in FilterConfig().skip_content_patterns),
    re.IGNORECASE,
)


def should_skip_by_title(title: str, filter_cfg: FilterConfig | None = None) -> tuple[bool, str]:
    """发现期过滤：仅基于标题判断是否跳过

    Args:
        title: 页面标题
        filter_cfg: 过滤配置，为 None 时使用默认值

    Returns:
        (是否跳过, 跳过原因)
    """
    if filter_cfg is None:
        filter_cfg = FilterConfig()

    # 1. 命名空间前缀
    for prefix in filter_cfg.skip_namespace_prefixes:
        if title.startswith(prefix):
            return True, f"命名空间前缀: {prefix}"

    # 2. 标题关键字
    for kw in filter_cfg.skip_title_keywords:
        if kw in title:
            return True, f"标题关键字: {kw}"

    # 3. 标题正则
    if _SKIP_TITLE_RE.search(title):
        return True, f"标题匹配正则"

    return False, ""


def should_skip_by_categories(
    categories: list[str],
    filter_cfg: FilterConfig | None = None,
) -> tuple[bool, str]:
    """获取期过滤：基于分类标签判断是否跳过

    Args:
        categories: 页面分类列表（不含 Category: 前缀）
        filter_cfg: 过滤配置

    Returns:
        (是否跳过, 匹配的分类)
    """
    if filter_cfg is None:
        filter_cfg = FilterConfig()

    for cat in categories:
        for kw in filter_cfg.skip_category_keywords:
            if kw in cat:
                return True, cat

    return False, ""


def should_skip_by_content(
    wikitext: str,
    filter_cfg: FilterConfig | None = None,
) -> tuple[bool, str]:
    """获取期过滤：基于正文内容判断是否跳过

    仅检查前 500 字符，避免对长页面做全量扫描。

    Args:
        wikitext: 页面正文（前 500 字符即可）
        filter_cfg: 过滤配置

    Returns:
        (是否跳过, 匹配的模式)
    """
    if not wikitext:
        return True, "空页面"

    if filter_cfg is None:
        filter_cfg = FilterConfig()

    # 重定向
    if wikitext.startswith("Redirect to:"):
        return True, "重定向页"

    sample = wikitext[:500]
    match = _SKIP_CONTENT_RE.search(sample)
    if match:
        return True, f"内容模式: {match.group(0)}"

    return False, ""


def should_skip_page(
    title: str,
    categories: list[str],
    wikitext: str,
    filter_cfg: FilterConfig | None = None,
) -> tuple[bool, str]:
    """综合过滤：标题 + 分类 + 内容

    按顺序检查，任一命中即跳过。

    Args:
        title: 页面标题
        categories: 页面分类列表
        wikitext: 页面正文
        filter_cfg: 过滤配置

    Returns:
        (是否跳过, 跳过原因)
    """
    # 1. 标题检查（发现期已过滤，此处兜底）
    skip, reason = should_skip_by_title(title, filter_cfg)
    if skip:
        return True, reason

    # 2. 分类标签检查
    skip, reason = should_skip_by_categories(categories, filter_cfg)
    if skip:
        return True, f"分类标签: {reason}"

    # 3. 正文内容检查
    skip, reason = should_skip_by_content(wikitext, filter_cfg)
    if skip:
        return True, reason

    return False, ""


# ── 自定义异常 ──────────────────────────────────────────────────────────────


class MediaWikiError(Exception):
    """MediaWiki API 错误"""

    def __init__(self, code: str, info: str = "") -> None:
        self.code = code
        self.info = info
        super().__init__(f"MediaWiki API error: {code} - {info}")


class RateLimitError(Exception):
    """速率限制错误"""

    pass


class ServerError(Exception):
    """服务端错误"""

    pass


# ── 分类页面 HTML 解析 ──────────────────────────────────────────────────────


def _parse_category_html(html: str) -> tuple[list[CategoryMember], Optional[str]]:
    """从分类页面 HTML 中提取成员和下一页链接

    MediaWiki 分类页面结构：
    <div id="mw-subcategories"> ... <a title="Category:XXX"> ... </div>
    <div id="mw-pages"> ... <a title="PageName"> ... </div>
    <a href="...&pagefrom=...">下一页</a>

    Args:
        html: 分类页面完整 HTML

    Returns:
        (成员列表, 下一页 URL 或 None)
    """
    soup = BeautifulSoup(html, "lxml")
    members: list[CategoryMember] = []

    # ── 子分类 ──
    subcats_div = soup.find("div", id="mw-subcategories")
    if subcats_div:
        for a_tag in subcats_div.find_all("a"):
            title = a_tag.get("title", "")
            href = a_tag.get("href", "")
            if title and title.startswith("Category:"):
                members.append(CategoryMember(
                    title=title,
                    page_type=PageType.SUBCATEGORY,
                ))

    # ── 普通页面 ──
    pages_div = soup.find("div", id="mw-pages")
    if pages_div:
        for li in pages_div.find_all("li"):
            a_tag = li.find("a")
            if a_tag:
                title = a_tag.get("title", "")
                if title and not title.startswith((
                    "Category:", "Template:", "Module:", "File:", "Image:",
                    "Special:", "Help:", "MediaWiki:", "User:",
                )):
                    # 发现期标题过滤：跳过消歧义页等非内容页
                    skip, reason = should_skip_by_title(title)
                    if skip:
                        logger.debug(f"跳过页面: {title} ({reason})")
                        continue
                    members.append(CategoryMember(
                        title=title,
                        page_type=PageType.PAGE,
                    ))

    # ── 下一页链接 ──
    next_url: Optional[str] = None
    next_link = soup.find("a", string=re.compile(r"下一页"))
    if next_link:
        href = next_link.get("href", "")
        if href:
            # 处理相对路径
            if href.startswith("/"):
                next_url = "https://zh.moegirl.org.cn" + href
            elif href.startswith("http"):
                next_url = href
            else:
                next_url = "https://zh.moegirl.org.cn/" + href

    return members, next_url


def _build_category_url(category: str, pagefrom: Optional[str] = None) -> str:
    """构建分类页面的 URL"""
    # Category 页面路径: /Category:XXX
    path = category.replace(" ", "_")
    url = f"https://zh.moegirl.org.cn/{path}"
    if pagefrom:
        url += f"?pagefrom={quote(pagefrom)}"
    return url


# ── API 客户端 ──────────────────────────────────────────────────────────────


class MediaWikiClient:
    """萌娘百科混合客户端

    - 分类遍历：HTML 页面解析
    - 页面数据：API (prop=info + prop=categories + prop=extracts)
    """

    BASE_URL = "https://zh.moegirl.org.cn"

    def __init__(
        self,
        api_config: APIConfig,
        network_config: NetworkConfig,
        stats: Optional[CrawlStats] = None,
    ) -> None:
        self._api = api_config
        self._net = network_config
        self._stats = stats or CrawlStats()
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(network_config.max_concurrent)
        self._last_request_time: float = 0.0

    # ── 生命周期 ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动 HTTP 客户端"""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=self._net.connect_timeout,
                read=self._net.read_timeout,
                write=self._net.write_timeout,
                pool=self._net.pool_timeout,
            ),
            limits=httpx.Limits(
                max_connections=self._net.max_concurrent + 2,
                max_keepalive_connections=self._net.max_concurrent,
            ),
            http2=self._net.http2,
            headers={
                "User-Agent": self._api.user_agent,
                "Accept": "text/html,application/json,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            follow_redirects=True,
        )
        logger.info(f"MediaWiki 客户端已启动 (HTTP/2={'开启' if self._net.http2 else '关闭'})")

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("MediaWiki 客户端已关闭")

    async def __aenter__(self) -> "MediaWikiClient":
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ── 速率限制 ─────────────────────────────────────────────────────────────

    async def _rate_limit_wait(self) -> None:
        """请求间隔控制 + 随机抖动"""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        wait_time = self._net.rate_limit - elapsed
        if wait_time > 0:
            jitter = random.uniform(0, self._net.jitter_max)
            await asyncio.sleep(wait_time + jitter)
        self._last_request_time = asyncio.get_event_loop().time()

    # ── HTML 请求（用于分类页面）─────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type((RateLimitError, ServerError, httpx.HTTPError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1.0, exp_base=2.0, jitter=2.0, max=60.0),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )
    async def _fetch_html(self, url: str) -> str:
        """获取 HTML 页面"""
        assert self._client is not None

        async with self._semaphore:
            await self._rate_limit_wait()

            response = await self._client.get(url)

            if response.status_code == 429:
                self._stats.retries += 1
                retry_after = float(response.headers.get("Retry-After", "5"))
                logger.warning(f"触发速率限制 (429)，等待 {retry_after}s")
                await asyncio.sleep(retry_after)
                raise RateLimitError("HTTP 429")

            if response.status_code >= 500:
                self._stats.retries += 1
                raise ServerError(f"HTTP {response.status_code}")

            if response.status_code != 200:
                raise MediaWikiError(f"http_{response.status_code}", f"HTTP {response.status_code}")

            # 检查是否为"未授权"页面
            if "未授权操作" in response.text[:500]:
                raise MediaWikiError("unauthorized", "页面需要授权访问")

            return response.text

    # ── API 请求（用于页面数据）──────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type((RateLimitError, ServerError, httpx.HTTPError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1.0, exp_base=2.0, jitter=2.0, max=60.0),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )
    async def _api_request(self, params: dict) -> dict:
        """发送 API 请求"""
        assert self._client is not None
        params["format"] = "json"

        async with self._semaphore:
            await self._rate_limit_wait()

            response = await self._client.get(self._api.base_url, params=params)

            if response.status_code == 429:
                self._stats.retries += 1
                retry_after = float(response.headers.get("Retry-After", "5"))
                await asyncio.sleep(retry_after)
                raise RateLimitError("HTTP 429")

            if response.status_code >= 500:
                self._stats.retries += 1
                raise ServerError(f"HTTP {response.status_code}")

            if response.status_code != 200:
                raise MediaWikiError(f"http_{response.status_code}", str(response.status_code))

            data = response.json()
            if "error" in data:
                error = data["error"]
                code = error.get("code", "unknown")
                info = error.get("info", "")
                if code in ("missingtitle", "nosuchpageid"):
                    return data
                raise MediaWikiError(code, info)

            return data

    # ── 分类成员获取（HTML 方式）─────────────────────────────────────────────

    async def get_category_members(
        self,
        category: str,
    ) -> AsyncIterator[CategoryMember]:
        """获取分类下的所有成员（通过 HTML 解析，自动翻页）

        Args:
            category: 分类标题（如 "Category:BanG Dream!"）

        Yields:
            CategoryMember 成员
        """
        pagefrom: Optional[str] = None
        page_count = 0
        pages_processed = 0

        while True:
            url = _build_category_url(category, pagefrom)
            try:
                html = await self._fetch_html(url)
            except Exception as e:
                logger.error(f"获取分类页面失败 [{category}]: {e}")
                break

            members, next_url = _parse_category_html(html)
            page_count += 1

            for member in members:
                pages_processed += 1
                yield member

            # 检查是否有下一页
            if next_url is None or len(members) == 0:
                break

            # 提取 pagefrom 参数
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(next_url)
            params = parse_qs(parsed.query)
            pagefrom_list = params.get("pagefrom", [None])
            pagefrom = pagefrom_list[0] if pagefrom_list else None

            if pagefrom is None:
                break

        logger.debug(f"分类 {category}: {pages_processed} 个成员 ({page_count} 页)")

    # ── 页面获取 ─────────────────────────────────────────────────────────────

    async def get_page_content(self, title: str) -> Optional[PageInfo]:
        """获取页面内容

        通过 API 获取：
        - prop=info：页面基本信息（pageid, lastrevid, touched）
        - prop=categories：分类列表
        - prop=extracts&explaintext=1：纯文本正文（保留 Wiki 标题结构）

        Args:
            title: 页面标题

        Returns:
            PageInfo 或 None
        """
        try:
            data = await self._api_request({
                "action": "query",
                "titles": title,
                "prop": "info|categories|extracts",
                "explaintext": "1",
                "exsectionformat": "wiki",
                "cllimit": "max",
                "redirects": "1",
            })
        except Exception as e:
            logger.error(f"获取页面失败 [{title}]: {e}")
            return None

        query = data.get("query", {})

        # 重定向处理
        redirects = query.get("redirects", [])
        if redirects:
            redirect_target = redirects[-1].get("to", "")
            logger.debug(f"重定向: {title} → {redirect_target}")

        pages = query.get("pages", {})
        if not pages:
            return None

        page_data = next(iter(pages.values()))
        if "missing" in page_data:
            return None

        page_title = page_data.get("title", title)
        page_id = page_data.get("pageid", 0)
        revision_id = page_data.get("lastrevid", 0)
        touched = page_data.get("touched", "")

        # 解析更新时间
        updated = None
        if touched:
            try:
                updated = datetime.fromisoformat(touched.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # 分类
        categories: list[str] = []
        for cat in page_data.get("categories", []):
            cat_title = cat.get("title", "")
            if cat_title.startswith("Category:"):
                cat_title = cat_title[len("Category:"):]
            categories.append(cat_title)

        # 正文（extracts 已清理 HTML 和模板）
        wikitext = page_data.get("extract", "")

        # 检测重定向（extracts 为 "Redirect to: XXX" 时）
        redirect_target = None
        if wikitext.startswith("Redirect to:"):
            redirect_target = wikitext[len("Redirect to:"):].strip()
            logger.debug(f"重定向页: {title} → {redirect_target}")

        # URL
        from utils import build_page_url
        url = build_page_url(page_title)

        return PageInfo(
            title=page_title,
            page_id=page_id,
            revision_id=revision_id,
            updated=updated,
            categories=categories,
            wikitext=wikitext,
            url=url,
            redirect_target=redirect_target,
        )

    async def get_pages_batch(
        self,
        titles: list[str],
    ) -> list[PageInfo]:
        """批量获取页面（利用 titles=| 机制）

        MediaWiki exlimit 限制：多页面查询时最多返回 20 个 extracts。
        因此批次大小设为 20，超出部分拆分请求。
        """
        if not titles:
            return []

        # exlimit 对多页面查询上限为 20
        batch_size = 20
        results: list[PageInfo] = []

        for i in range(0, len(titles), batch_size):
            batch = titles[i:i + batch_size]
            titles_str = "|".join(batch)

            try:
                data = await self._api_request({
                    "action": "query",
                    "titles": titles_str,
                    "prop": "info|categories|extracts",
                    "explaintext": "1",
                    "exsectionformat": "wiki",
                    "exlimit": "max",
                    "cllimit": "max",
                    "redirects": "1",
                })
            except Exception as e:
                logger.error(f"批量获取失败: {e}")
                continue

            query = data.get("query", {})

            # 重定向映射
            redirect_map: dict[str, str] = {}
            for rd in query.get("redirects", []):
                redirect_map[rd.get("from", "")] = rd.get("to", "")

            pages = query.get("pages", {})
            for _pid, page_data in pages.items():
                if "missing" in page_data:
                    continue

                page_title = page_data.get("title", "")
                page_id = page_data.get("pageid", 0)
                revision_id = page_data.get("lastrevid", 0)
                touched = page_data.get("touched", "")

                updated = None
                if touched:
                    try:
                        updated = datetime.fromisoformat(touched.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                categories: list[str] = []
                for cat in page_data.get("categories", []):
                    cat_title = cat.get("title", "")
                    if cat_title.startswith("Category:"):
                        cat_title = cat_title[len("Category:"):]
                    categories.append(cat_title)

                wikitext = page_data.get("extract", "")

                # 如果批量获取 extract 为空（exlimit 限制），单独获取
                if not wikitext and not redirect_map.get(page_title):
                    logger.debug(f"批量获取 extract 为空，单独获取: {page_title}")
                    single = await self.get_page_content(page_title)
                    if single and single.wikitext:
                        wikitext = single.wikitext
                        revision_id = single.revision_id
                        updated = single.updated
                        if single.categories:
                            categories = single.categories

                redirect_target: Optional[str] = None
                if wikitext.startswith("Redirect to:"):
                    redirect_target = wikitext[len("Redirect to:"):].strip()

                if page_title in redirect_map:
                    redirect_target = redirect_map[page_title]

                from utils import build_page_url
                url = build_page_url(page_title)

                results.append(PageInfo(
                    title=page_title,
                    page_id=page_id,
                    revision_id=revision_id,
                    updated=updated,
                    categories=categories,
                    wikitext=wikitext,
                    url=url,
                    redirect_target=redirect_target,
                ))

        return results

    # ── 页面发现（HTML 递归）─────────────────────────────────────────────────

    async def discover_pages(
        self,
        root_category: str,
        max_depth: int = 10,
    ) -> AsyncIterator[tuple[CategoryMember, int]]:
        """从分类树中发现所有页面

        BFS 遍历：先获取根分类的成员 → 子分类加入队列 → 普通页面直接 yield。

        Args:
            root_category: 根分类标题
            max_depth: 最大深度

        Yields:
            (CategoryMember, depth)
        """
        visited_cats: set[str] = set()
        visited_pages: set[str] = set()
        queue: list[tuple[str, int]] = [(root_category, 0)]

        while queue:
            cat_title, depth = queue.pop(0)

            if cat_title in visited_cats:
                continue
            visited_cats.add(cat_title)

            if depth > max_depth:
                logger.debug(f"达到最大深度 {max_depth}，跳过: {cat_title}")
                continue

            logger.info(f"遍历分类 [{depth}]: {cat_title}")

            try:
                async for member in self.get_category_members(cat_title):
                    if member.page_type == PageType.SUBCATEGORY:
                        if member.title not in visited_cats:
                            queue.append((member.title, depth + 1))
                    elif member.page_type == PageType.PAGE:
                        if member.title not in visited_pages:
                            visited_pages.add(member.title)
                            yield (member, depth)
            except Exception as e:
                logger.error(f"遍历分类异常 [{cat_title}]: {e}")

        logger.info(f"页面发现完成: {len(visited_pages)} 页面, {len(visited_cats)} 分类")
