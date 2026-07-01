"""
乐队服务
"""

from __future__ import annotations


class BandService:
    def __init__(self, index, formatter) -> None:
        self._index = index
        self._fmt = formatter

    async def query(self, name: str) -> str:
        if not name.strip():
            return self._fmt.format_help()

        results = self._index.search(name, category="乐队", limit=5)
        if results:
            best_entry, score = results[0]
            if score >= 20:
                content = self._index.read_content(best_entry)
                return self._fmt.format_entry_detail(best_entry, content)
            return self._fmt.format_search_results(results, name, category="乐队")

        return self._fmt.format_not_found(name, category="乐队")
