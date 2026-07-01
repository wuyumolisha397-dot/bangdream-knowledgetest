"""
乐队服务

封装乐队查询的完整业务流程。
"""

from __future__ import annotations

from .kb_index import KnowledgeIndex
from . import formatter


class BandService:
    """乐队查询服务"""

    def __init__(self, index: KnowledgeIndex) -> None:
        self._index = index

    async def query(self, name: str) -> str:
        """查询乐队信息"""
        if not name.strip():
            return formatter.format_help()

        results = self._index.search(name, category="乐队", limit=5)

        if results:
            best_entry, score = results[0]

            if score >= 30:
                content = self._index.read_content(best_entry)
                return formatter.format_entry_detail(best_entry, content)

            return formatter.format_search_results(results, name, category="乐队")

        rag_result = await self._rag_fallback(name)
        if rag_result:
            return rag_result

        return formatter.format_not_found(name, category="乐队")

    @staticmethod
    async def _rag_fallback(query: str) -> str:
        return ""
