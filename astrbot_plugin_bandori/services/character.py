"""
角色服务

封装角色查询的完整业务流程：
1. 本地知识库检索
2. 无结果时回退 RAG（stub）
"""

from __future__ import annotations

from .kb_index import KnowledgeIndex
from . import formatter


class CharacterService:
    """角色查询服务"""

    def __init__(self, index: KnowledgeIndex) -> None:
        self._index = index

    async def query(self, name: str) -> str:
        """查询角色信息

        Args:
            name: 角色名称（支持模糊匹配）

        Returns:
            格式化的 Markdown 响应
        """
        if not name.strip():
            return formatter.format_help()

        # 1. 本地知识库检索
        results = self._index.search(name, category="角色", limit=5)

        if results:
            # 取最佳匹配
            best_entry, score = results[0]

            # 高置信度 (>30%) → 直接返回详情
            if score >= 30:
                content = self._index.read_content(best_entry)
                return formatter.format_entry_detail(best_entry, content)

            # 中等置信度 → 返回列表让用户选择
            return formatter.format_search_results(results, name, category="角色")

        # 2. 本地无结果 → RAG 回退
        rag_result = await self._rag_fallback(name)
        if rag_result:
            return rag_result

        return formatter.format_not_found(name, category="角色")

    async def random(self) -> str:
        """随机角色"""
        entry = self._index.random_pick("角色")
        if entry is None:
            return formatter.format_error("角色库为空，请先运行爬虫构建知识库。")

        content = self._index.read_content(entry, max_len=800)
        return formatter.format_random(entry, content)

    @staticmethod
    async def _rag_fallback(query: str) -> str:
        """RAG 回退 — 当前为 stub，可接入外部 API

        未来可选方案：
        - OpenAI Assistants + File Search
        - 本地向量数据库 (ChromaDB / Milvus)
        - AnythingLLM / Dify 等 RAG 框架
        """
        # Stub: 不生成回退结果
        return ""
