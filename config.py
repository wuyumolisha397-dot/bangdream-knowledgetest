"""
bandori-knowledge 配置模块

集中管理所有可配置参数，包括 API、网络、缓存、输出等设置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# ── 项目根目录 ──────────────────────────────────────────────────────────────
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent


@dataclass(frozen=True)
class APIConfig:
    """MediaWiki API 相关配置"""

    base_url: str = "https://zh.moegirl.org.cn/api.php"
    """API 端点"""

    index_url: str = "https://zh.moegirl.org.cn/index.php"
    """index.php 端点（备用）"""

    root_category: str = "Category:BanG Dream!"
    """起始分类"""

    user_agent: str = (
        "BandoriKnowledgeBot/1.0 "
        "(https://github.com/bandori-knowledge; Python/httpx)"
    )
    """HTTP User-Agent"""


@dataclass(frozen=True)
class NetworkConfig:
    """网络请求相关配置"""

    rate_limit: float = 0.5
    """每次请求间隔（秒），默认 2 req/s"""

    max_concurrent: int = 3
    """最大并发请求数"""

    connect_timeout: float = 10.0
    """连接超时（秒）"""

    read_timeout: float = 30.0
    """读取超时（秒）"""

    write_timeout: float = 10.0
    """写入超时（秒）"""

    pool_timeout: float = 60.0
    """连接池超时（秒）"""

    max_retries: int = 5
    """最大重试次数"""

    retry_min_wait: float = 1.0
    """重试最小等待（秒）"""

    retry_max_wait: float = 30.0
    """重试最大等待（秒）"""

    retry_multiplier: float = 2.0
    """重试指数退避倍数"""

    jitter_max: float = 0.5
    """随机抖动最大值（秒）"""

    http2: bool = True
    """是否启用 HTTP/2"""


@dataclass(frozen=True)
class CacheConfig:
    """缓存相关配置"""

    db_path: Path = field(default_factory=lambda: PROJECT_ROOT / "cache" / "pages.db")
    """SQLite 数据库路径"""


@dataclass(frozen=True)
class FilterConfig:
    """页面过滤规则

    在爬取阶段自动跳过非内容页面，减少噪音。
    过滤分为两级：
    - 发现期：基于标题前缀/关键字，零 API 消耗
    - 获取期：基于页面分类标签，需一次 info API 调用
    """

    # ── 发现期过滤（标题匹配，零 API 消耗）──────────────

    skip_namespace_prefixes: tuple[str, ...] = (
        "Category:", "Template:", "Module:", "File:", "Image:",
        "Special:", "Help:", "MediaWiki:", "User:",
    )
    """命名空间前缀 — 这些不是百科正文内容"""

    skip_title_keywords: tuple[str, ...] = (
        "消歧义",
        "导航模板",
        "/模板",         # 子页面名 "/模板"（如 "xxx/模板"）
        "模板:",
    )
    """标题关键字 — 命中则跳过。

    注意：不包含"列表" — 歌曲列表等有实际检索价值。
    """

    skip_title_patterns: tuple[str, ...] = (
        r"/\s*模板$",         # 结尾 "/模板"
        r"/\s*列表$",         # 结尾 "/列表"
    )
    """标题正则 — 命中则跳过（待编译）"""

    # ── 获取期过滤（分类标签匹配，需一次 API 调用）─────

    skip_category_keywords: tuple[str, ...] = (
        "消歧义",
        "导航模板",
        "维基百科模板",
        "维护",
        "需要清理",
        "需要更新",
        "需要长期关注",
        "需要扩充",
        "正在施工",
        "存根",
        "小作品",
        "已过时",
        "未完成",
        "草稿",
        "沙盒",
        "帮助页面",
        "方针",
        "指引",
        "模板说明",
        "文件说明",
    )
    """分类关键字 — 页面所属分类命中任一关键字则跳过"""

    # ── 获取期：内容模式（正文匹配）───────────────────

    skip_content_patterns: tuple[str, ...] = (
        r"本文介绍的是",           # 消歧义页首句
        r"这是一个消歧义",         # 消歧义页标记
        r"可以指：",               # 消歧义列表
        r"#重定向",               # 重定向标记
        r"{{消歧义",              # 消歧义模板
        r"{{disambig",           # 消歧义模板(英)
        r"{{导航模板",            # 导航模板页
        r"{{navbox",             # 导航模板(英)
    )
    """正文模式 — 检查正文前 500 字符，命中则跳过"""


@dataclass(frozen=True)
class OutputConfig:
    """输出相关配置"""

    output_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "output")
    """输出根目录"""

    long_page_threshold: int = 5000
    """超长页面字数阈值"""

    split_by_h2_first: bool = True
    """优先按 H2 拆分"""

    # 分类 → 输出子目录 映射
    category_dir_map: dict[str, str] = field(default_factory=lambda: {
        "角色": "角色",
        "人物": "角色",
        "歌曲": "歌曲",
        "音乐": "歌曲",
        "乐队": "乐队",
        "组合": "乐队",
        "动画": "动画",
        "动漫": "动画",
        "专辑": "专辑",
        "Live": "Live",
        "演唱会": "Live",
        "游戏": "其它",
        "漫画": "其它",
        "活动": "其它",
        "学校": "其它",
        "术语": "其它",
    })
    """分类关键字 → 输出子目录映射，未匹配的归入「其它」"""


@dataclass(frozen=True)
class LogConfig:
    """日志相关配置"""

    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")
    """日志目录"""

    log_file: str = "crawler.log"
    """日志文件名"""

    rotation: str = "10 MB"
    """日志轮转大小"""

    retention: str = "7 days"
    """日志保留时长"""

    log_level: str = "INFO"
    """日志级别"""


@dataclass(frozen=True)
class AppConfig:
    """应用全局配置"""

    api: APIConfig = field(default_factory=APIConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    log: LogConfig = field(default_factory=LogConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)

    @classmethod
    def from_env(cls) -> AppConfig:
        """从环境变量覆盖配置（可选）

        支持的环境变量：
        - BANDORI_RATE_LIMIT: 请求间隔秒数
        - BANDORI_MAX_CONCURRENT: 最大并发数
        - BANDORI_DB_PATH: 缓存数据库路径
        - BANDORI_OUTPUT_DIR: 输出目录
        - BANDORI_ROOT_CATEGORY: 起始分类
        - BANDORI_HTTP2: 是否启用 HTTP/2 (true/false)
        - BANDORI_LOG_LEVEL: 日志级别
        """
        network_overrides: dict = {}
        api_overrides: dict = {}
        cache_overrides: dict = {}
        output_overrides: dict = {}
        log_overrides: dict = {}

        if v := os.getenv("BANDORI_RATE_LIMIT"):
            network_overrides["rate_limit"] = float(v)
        if v := os.getenv("BANDORI_MAX_CONCURRENT"):
            network_overrides["max_concurrent"] = int(v)
        if v := os.getenv("BANDORI_DB_PATH"):
            cache_overrides["db_path"] = Path(v)
        if v := os.getenv("BANDORI_OUTPUT_DIR"):
            output_overrides["output_dir"] = Path(v)
        if v := os.getenv("BANDORI_ROOT_CATEGORY"):
            api_overrides["root_category"] = v
        if v := os.getenv("BANDORI_HTTP2"):
            network_overrides["http2"] = v.lower() in ("true", "1", "yes")
        if v := os.getenv("BANDORI_LOG_LEVEL"):
            log_overrides["log_level"] = v.upper()

        return cls(
            api=APIConfig(**api_overrides) if api_overrides else APIConfig(),
            network=NetworkConfig(**network_overrides) if network_overrides else NetworkConfig(),
            cache=CacheConfig(**cache_overrides) if cache_overrides else CacheConfig(),
            output=OutputConfig(**output_overrides) if output_overrides else OutputConfig(),
            log=LogConfig(**log_overrides) if log_overrides else LogConfig(),
        )


# 默认全局配置实例
DEFAULT_CONFIG: Final[AppConfig] = AppConfig.from_env()
