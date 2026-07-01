"""
角色服务
"""

from __future__ import annotations


class CharacterService:
    def __init__(self, index, formatter) -> None:
        self._index = index
        self._fmt = formatter

    async def query(self, name: str) -> str:
        if not name.strip():
            return self._fmt.format_help()

        results = self._index.search(name, category="角色", limit=5)
        if results:
            best_entry, score = results[0]
            if score >= 30:
                content = self._index.read_content(best_entry)
                return self._fmt.format_entry_detail(best_entry, content)
            return self._fmt.format_search_results(results, name, category="角色")

        return self._fmt.format_not_found(name, category="角色")

    async def random(self) -> str:
        entry = self._index.random_pick("角色")
        if entry is None:
            return self._fmt.format_error("角色库为空")
        content = self._index.read_content(entry, max_len=800)
        return self._fmt.format_random(entry, content)
