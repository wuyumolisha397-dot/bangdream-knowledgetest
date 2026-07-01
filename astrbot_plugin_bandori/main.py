"""
astrbot_plugin_bandori — BanG Dream! 知识库插件

命令列表：
    /角色 <名称>      查询角色信息
    /歌曲 <名称>      查询歌曲信息
    /乐队 <名称>      查询乐队信息
    /随机角色         随机一位角色
    /随机歌曲         随机一首歌曲
    /萌百搜索 <关键词> 全局搜索

优先级：本地知识库 → RAG 回退
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star
from astrbot.api import logger

# ── 按文件路径加载 service 模块（绕过 AstrBot 插件包导入限制）────────────
_plugin_dir = Path(__file__).resolve().parent
_services_dir = _plugin_dir / "services"


def _load_module(name: str):
    """加载 services/ 下的 .py 文件为独立模块"""
    path = _services_dir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bandori_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_kb_index = _load_module("kb_index")
_character_svc = _load_module("character")
_song_svc = _load_module("song")
_band_svc = _load_module("band")
_search_svc = _load_module("search")
_formatter = _load_module("formatter")

KnowledgeIndex = _kb_index.KnowledgeIndex
CharacterService = _character_svc.CharacterService
SongService = _song_svc.SongService
BandService = _band_svc.BandService
SearchService = _search_svc.SearchService
formatter = _formatter


# ── 知识库路径 ────────────────────────────────────────────────────────────────

def _resolve_kb_path(context: Context | None = None) -> str:
    """解析知识库目录路径

    优先级：
    1. WebUI 配置 (context.config.kb_path)
    2. 环境变量 BANDORI_KB_PATH
    3. 相对路径（从插件目录出发）
    4. 当前工作目录 fallback
    """
    # 1. WebUI 配置
    if context is not None:
        try:
            webui_path = context.config.get("kb_path", "").strip()
            if webui_path and Path(webui_path).exists():
                return webui_path
        except Exception:
            pass

    # 2. 环境变量
    env_path = os.getenv("BANDORI_KB_PATH", "")
    if env_path and Path(env_path).exists():
        return env_path

    # 3. 从插件目录出发探测
    plugin_dir = Path(__file__).resolve().parent
    relative = plugin_dir / ".." / ".." / ".." / "output"
    if relative.exists():
        return str(relative.resolve())

    # 4. 当前工作目录下
    cwd_output = Path.cwd() / "output"
    if cwd_output.exists():
        return str(cwd_output)

    return ""


# ── 插件主类 ────────────────────────────────────────────────────────────────


class BandoriPlugin(Star):
    """BanG Dream! 知识库插件

    启动时构建本地知识库索引，提供角色/歌曲/乐队/搜索等命令。
    """

    def __init__(self, context: Context) -> None:
        super().__init__(context)

        kb_path = _resolve_kb_path(context)
        self._kb_ready = bool(kb_path)

        self._index = KnowledgeIndex(kb_path if kb_path else "")
        self._character_svc = CharacterService(self._index, formatter)
        self._song_svc = SongService(self._index, formatter)
        self._band_svc = BandService(self._index, formatter)
        self._search_svc = SearchService(self._index, formatter)

    # ── 生命周期 ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """插件启动时加载知识库索引"""
        if self._kb_ready:
            try:
                self._index.load()
                stats = self._index.stats()
                total = self._index.total_count
                logger.info(
                    f"[Bandori] 知识库索引加载完成 — 总计 {total} 篇 "
                    f"(角色:{stats.get('角色',0)} 歌曲:{stats.get('歌曲',0)} "
                    f"乐队:{stats.get('乐队',0)} 其它:{stats.get('其它',0)})"
                )
            except Exception as e:
                logger.error(f"[Bandori] 知识库索引加载失败: {e}")
                self._kb_ready = False
        else:
            logger.warning(
                "[Bandori] 未找到知识库目录，请设置环境变量 BANDORI_KB_PATH "
                "或将 output/ 目录放到插件可访问的位置"
            )

    async def terminate(self) -> None:
        """插件卸载"""
        logger.info("[Bandori] 插件已卸载")

    # ── 命令：/角色 ───────────────────────────────────────────────────────────

    @filter.command("角色")
    async def cmd_character(self, event: AstrMessageEvent) -> MessageEventResult:
        """查询角色信息

        用法: /角色 <名称>
        示例: /角色 丰川祥子
        """
        if not self._kb_ready:
            yield event.plain_result(
                formatter.format_error("知识库未就绪，请检查 BANDORI_KB_PATH 配置。")
            )
            return

        name = event.message_str.replace("/角色", "", 1).strip()
        result = await self._character_svc.query(name)
        yield event.plain_result(result)

    @filter.command("随机角色")
    async def cmd_random_character(self, event: AstrMessageEvent) -> MessageEventResult:
        """随机一位角色"""
        if not self._kb_ready:
            yield event.plain_result(
                formatter.format_error("知识库未就绪，请检查 BANDORI_KB_PATH 配置。")
            )
            return

        result = await self._character_svc.random()
        yield event.plain_result(result)

    # ── 命令：/歌曲 ───────────────────────────────────────────────────────────

    @filter.command("歌曲")
    async def cmd_song(self, event: AstrMessageEvent) -> MessageEventResult:
        """查询歌曲信息

        用法: /歌曲 <名称>
        示例: /歌曲 -N-E-M-E-S-I-S-
        """
        if not self._kb_ready:
            yield event.plain_result(
                formatter.format_error("知识库未就绪，请检查 BANDORI_KB_PATH 配置。")
            )
            return

        name = event.message_str.replace("/歌曲", "", 1).strip()
        result = await self._song_svc.query(name)
        yield event.plain_result(result)

    @filter.command("随机歌曲")
    async def cmd_random_song(self, event: AstrMessageEvent) -> MessageEventResult:
        """随机一首歌曲"""
        if not self._kb_ready:
            yield event.plain_result(
                formatter.format_error("知识库未就绪，请检查 BANDORI_KB_PATH 配置。")
            )
            return

        result = await self._song_svc.random()
        yield event.plain_result(result)

    # ── 命令：/乐队 ───────────────────────────────────────────────────────────

    @filter.command("乐队")
    async def cmd_band(self, event: AstrMessageEvent) -> MessageEventResult:
        """查询乐队信息

        用法: /乐队 <名称>
        示例: /乐队 Roselia
        """
        if not self._kb_ready:
            yield event.plain_result(
                formatter.format_error("知识库未就绪，请检查 BANDORI_KB_PATH 配置。")
            )
            return

        name = event.message_str.replace("/乐队", "", 1).strip()
        result = await self._band_svc.query(name)
        yield event.plain_result(result)

    # ── 命令：/萌百搜索 ───────────────────────────────────────────────────────

    @filter.command("萌百搜索")
    async def cmd_search(self, event: AstrMessageEvent) -> MessageEventResult:
        """全局搜索知识库

        用法: /萌百搜索 <关键词>
        示例: /萌百搜索 Roselia
        """
        if not self._kb_ready:
            yield event.plain_result(
                formatter.format_error("知识库未就绪，请检查 BANDORI_KB_PATH 配置。")
            )
            return

        keyword = event.message_str.replace("/萌百搜索", "", 1).strip()
        result = await self._search_svc.query(keyword)
        yield event.plain_result(result)

    # ── 命令：/bandori 帮助 ───────────────────────────────────────────────────

    @filter.command("bandori")
    async def cmd_help(self, event: AstrMessageEvent) -> MessageEventResult:
        """显示插件帮助"""
        yield event.plain_result(formatter.format_help())
