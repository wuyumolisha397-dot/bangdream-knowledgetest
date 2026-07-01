"""
全局搜索服务

封装全局搜索的完整业务流程。
"""

from __future__ import annotations

from .kb_index import KnowledgeIndex
from . import formatter


class SearchService:
    """全局搜索服务"""

    def __init__(self, index: KnowledgeIndex) -> None:
        self._index = index

    async def query(self, keyword: str) -> str:
        """全局搜索"""
        if not keyword.strip():
            return formatter.format_help()

        # 本地知识库全局搜索
        results = self._index.search(keyword, category="", limit=8)

        if results:
            return formatter.format_search_results(results, keyword)

        # RAG 回退
        rag_result = await self._rag_fallback(keyword)
        if rag_result:
            return rag_result

        return formatter.format_not_found(keyword)

    @staticmethod
    async def _rag_fallback(query: str) -> str:
        return ""
