"""
bandori-knowledge 数据模型模块

定义页面、分类、爬取状态等核心数据结构。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class PageType(enum.Enum):
    """页面类型枚举"""

    PAGE = "page"
    """普通页面"""

    SUBCATEGORY = "subcat"
    """子分类"""

    FILE = "file"
    """文件"""


class CrawlStatus(enum.Enum):
    """爬取状态枚举"""

    PENDING = "pending"
    """待爬取"""

    CRAWLING = "crawling"
    """爬取中"""

    COMPLETED = "completed"
    """已完成"""

    FAILED = "failed"
    """失败"""

    SKIPPED = "skipped"
    """跳过（未变更）"""


@dataclass
class CategoryInfo:
    """分类信息

    用于记录分类树中的节点，支持递归遍历。
    """

    title: str
    """分类标题，如 'Category:BanG Dream!角色'"""

    page_id: int = 0
    """页面 ID"""

    depth: int = 0
    """递归深度，0 为根分类"""

    parent: Optional[str] = None
    """父分类标题"""

    crawled: bool = False
    """是否已爬取子成员"""

    def __hash__(self) -> int:
        return hash(self.title)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CategoryInfo):
            return NotImplemented
        return self.title == other.title


@dataclass
class PageInfo:
    """页面信息

    包含从 MediaWiki API 获取的页面元数据和正文。
    """

    title: str
    """页面标题"""

    page_id: int = 0
    """页面 ID"""

    revision_id: int = 0
    """最新修订 ID"""

    updated: Optional[datetime] = None
    """最后更新时间"""

    categories: list[str] = field(default_factory=list)
    """页面所属分类列表（不含 'Category:' 前缀）"""

    wikitext: str = ""
    """原始 Wiki 标记文本"""

    markdown: str = ""
    """转换后的 Markdown 文本"""

    url: str = ""
    """页面 URL"""

    redirect_target: Optional[str] = None
    """重定向目标（如果该页是重定向页）"""

    status: CrawlStatus = CrawlStatus.PENDING
    """爬取状态"""

    error: Optional[str] = None
    """错误信息"""

    def __hash__(self) -> int:
        return hash(self.title)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PageInfo):
            return NotImplemented
        return self.title == other.title

    @property
    def is_redirect(self) -> bool:
        """是否为重定向页面"""
        return self.redirect_target is not None

    @property
    def display_title(self) -> str:
        """用于显示的标题（去除命名空间前缀）"""
        title = self.title
        # 去除常见命名空间前缀
        for prefix in ("Category:", "Template:", "Module:", "Help:"):
            if title.startswith(prefix):
                title = title[len(prefix):]
        return title


@dataclass
class CategoryMember:
    """分类成员

    从 categorymembers API 返回的单条记录。
    """

    title: str
    """成员标题"""

    page_id: int = 0
    """页面 ID"""

    page_type: PageType = PageType.PAGE
    """成员类型"""

    def __hash__(self) -> int:
        return hash(self.title)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CategoryMember):
            return NotImplemented
        return self.title == other.title


@dataclass
class CrawlStats:
    """爬取统计信息"""

    total_categories: int = 0
    """发现的分类总数"""

    total_pages: int = 0
    """发现的页面总数"""

    pages_crawled: int = 0
    """已爬取页面数"""

    pages_skipped: int = 0
    """跳过的页面数（未变更）"""

    pages_failed: int = 0
    """失败的页面数"""

    pages_filtered: int = 0
    """被过滤规则跳过的页面数"""

    retries: int = 0
    """重试总次数"""

    start_time: Optional[datetime] = None
    """爬取开始时间"""

    end_time: Optional[datetime] = None
    """爬取结束时间"""

    @property
    def elapsed_seconds(self) -> float:
        """已用时间（秒）"""
        if self.start_time is None:
            return 0.0
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def pages_per_second(self) -> float:
        """爬取速率（页/秒）"""
        elapsed = self.elapsed_seconds
        if elapsed <= 0:
            return 0.0
        return self.pages_crawled / elapsed

    def to_dict(self) -> dict:
        """导出为字典"""
        return {
            "total_categories": self.total_categories,
            "total_pages": self.total_pages,
            "pages_crawled": self.pages_crawled,
            "pages_skipped": self.pages_skipped,
            "pages_failed": self.pages_failed,
            "pages_filtered": self.pages_filtered,
            "retries": self.retries,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "pages_per_second": round(self.pages_per_second, 2),
        }


@dataclass
class SplitPage:
    """拆分后的子页面

    当原始页面超过字数阈值时，按标题层级拆分。
    """

    title: str
    """子页面标题（含原始标题前缀）"""

    markdown: str
    """子页面 Markdown 内容"""

    section_level: int = 2
    """拆分依据的标题层级"""

    @property
    def char_count(self) -> int:
        """字符数"""
        return len(self.markdown)
