"""
bandori-knowledge Wiki 解析模块

将 API extracts 返回的 Wiki 格式文本转换为干净的 Markdown。

extracts 格式特点：
- 已去除 HTML 标签和大部分模板
- 标题保留为 == H2 ==, === H3 === 格式
- 列表项以 * / # / ; 开头
- 链接可能保留 [[target|text]] 形式
"""

from __future__ import annotations

import re
from typing import Optional

import mwparserfromhell
from loguru import logger

from config import OutputConfig
from models import PageInfo, SplitPage


# ── 正则模式 ────────────────────────────────────────────────────────────────

# Wiki 标题: == Title ==  →  ## Title
_WIKI_HEADING = re.compile(r"^(=+)\s*(.+?)\s*\1\s*$", re.MULTILINE)

# Wiki 链接: [[Target]] 或 [[Target|Text]]
_WIKI_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

# 外部链接: [URL Text] 或 http://url
_EXTERNAL_LINK = re.compile(r"\[(https?://[^\s\]]+)\s+([^\]]*)\]")

# 裸 URL
_BARE_URL = re.compile(r"(?<!\[)https?://[^\s]+")

# 模板残留: {{xxx}}
_TEMPLATE_RESIDUE = re.compile(r"\{\{[^}]*\}\}")

# HTML 注释
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# ref 标签残留
_REF_TAG = re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL)
_REF_SELF_CLOSE = re.compile(r"<ref[^/]*/>", re.DOTALL)

# HTML 标签
_HTML_TAG = re.compile(r"</?[^>]+>")

# 文件/图片链接
_FILE_LINK = re.compile(r"\[\[(File|文件|Image|Media):[^\]]*\]\]", re.IGNORECASE)

# 分类标签
_CATEGORY_LINK = re.compile(r"\[\[Category:[^\]]*\]\]", re.IGNORECASE)

# Lua 残留
_LUA_INVOKE = re.compile(r"\{\{#invoke:[^}]*\}\}", re.IGNORECASE)

# Wiki 列表项 (* / # / ; / :)
_WIKI_LIST_ITEM = re.compile(r"^([*#;:]+)\s*(.+)$", re.MULTILINE)

# Wiki 粗体/斜体 '''bold''', ''italic''
_WIKI_BOLD = re.compile(r"'''(.+?)'''")
_WIKI_ITALIC = re.compile(r"''(.+?)''")

# 缩进行（以 : 开头）
_WIKI_INDENT = re.compile(r"^:(?!\s)(.+)$", re.MULTILINE)

# 定义列表（以 ; 开头）
_WIKI_DEF = re.compile(r"^;(.+?):\s*(.+)$", re.MULTILINE)

# 水平线 ----
_WIKI_HR = re.compile(r"^-{4,}$", re.MULTILINE)

# 多个空行
_MULTI_NEWLINE = re.compile(r"\n{3,}")

# 行首空白
_LEADING_WS = re.compile(r"^[ \t]+", re.MULTILINE)

# 表格残留（{| ... |}）
_TABLE_RESIDUE = re.compile(r"\{\|[\s\S]*?\|\}", re.DOTALL)

# 无值属性（|xxx= 等模板参数残留）
_PIPE_ATTR = re.compile(r"\|[a-zA-Z_]+\s*=\s*", re.MULTILINE)


class WikiParser:
    """Wiki 文本 → Markdown 转换器

    处理 extracts API 返回的文本：
    1. Wiki 标题 → Markdown 标题
    2. Wiki 链接 → Markdown 链接/纯文本
    3. 粗体/斜体转换
    4. 列表处理
    5. 残留清理
    """

    def __init__(self, config: Optional[OutputConfig] = None) -> None:
        self._config = config or OutputConfig()

    # ── 主入口 ───────────────────────────────────────────────────────────────

    def parse(self, page: PageInfo) -> str:
        """将页面 wikitext/extract 转换为 Markdown

        Args:
            page: 页面信息

        Returns:
            清理后的 Markdown 文本
        """
        text = page.wikitext

        if not text:
            return ""

        # 检测并跳过重定向
        if text.startswith("Redirect to:"):
            return ""

        try:
            return self._convert(text)
        except Exception as e:
            logger.error(f"解析页面失败 [{page.title}]: {e}")
            return self._fallback_clean(text)

    def _convert(self, text: str) -> str:
        """核心转换流程"""
        # 1. 删除不需要的内容
        text = self._remove_unwanted(text)

        # 2. 转换 Wiki 语法为 Markdown
        text = self._convert_bold_italic(text)
        text = self._convert_links(text)
        text = self._convert_lists(text)        # 必须在 headings 之前
        text = self._convert_headings(text)
        text = self._convert_hr(text)
        text = self._convert_def_list(text)

        # 3. 后处理
        text = self._post_process(text)

        return text.strip()

    # ── 删除不需要的内容 ─────────────────────────────────────────────────────

    def _remove_unwanted(self, text: str) -> str:
        """删除不需要的内容"""
        # HTML 注释
        text = _HTML_COMMENT.sub("", text)
        # ref 标签
        text = _REF_TAG.sub("", text)
        text = _REF_SELF_CLOSE.sub("", text)
        # 分类标签
        text = _CATEGORY_LINK.sub("", text)
        # 文件链接
        text = _FILE_LINK.sub("", text)
        # Lua 残留
        text = _LUA_INVOKE.sub("", text)
        # 模板残留
        text = _TEMPLATE_RESIDUE.sub("", text)
        # 表格残留
        text = _TABLE_RESIDUE.sub("", text)
        # 无值属性
        text = _PIPE_ATTR.sub("", text)
        # HTML 标签（在去除 ref 之后）
        text = _HTML_TAG.sub("", text)

        return text

    # ── 标题转换 ─────────────────────────────────────────────────────────────

    def _convert_headings(self, text: str) -> str:
        """Wiki 标题 → Markdown 标题

        == H2 ==  →  ## H2
        === H3 ===  →  ### H3
        """
        def _replace(m: re.Match) -> str:
            level = len(m.group(1))
            title = m.group(2).strip()
            prefix = "#" * level
            return f"\n\n{prefix} {title}\n\n"

        return _WIKI_HEADING.sub(_replace, text)

    # ── 粗体/斜体 ────────────────────────────────────────────────────────────

    def _convert_bold_italic(self, text: str) -> str:
        """Wiki 粗体/斜体 → Markdown"""
        text = _WIKI_BOLD.sub(r"**\1**", text)
        text = _WIKI_ITALIC.sub(r"*\1*", text)
        return text

    # ── 链接转换 ─────────────────────────────────────────────────────────────

    def _convert_links(self, text: str) -> str:
        """转换链接

        [[Target]] → Target
        [[Target|Text]] → Text
        [URL Text] → [Text](URL)
        """
        # Wiki 链接
        def _wiki_link_repl(m: re.Match) -> str:
            target = m.group(1)
            display = m.group(2) if m.group(2) else target

            # 跳过命名空间链接
            if any(target.lower().startswith(p) for p in (
                "category:", "file:", "文件:", "image:",
                "template:", "module:", "help:", "special:",
            )):
                return ""
            return display

        text = _WIKI_LINK.sub(_wiki_link_repl, text)

        # 外部链接 [URL Text]
        def _ext_link_repl(m: re.Match) -> str:
            url = m.group(1)
            display = m.group(2) if m.group(2) else url
            return f"[{display}]({url})"

        text = _EXTERNAL_LINK.sub(_ext_link_repl, text)

        return text

    # ── 列表转换 ─────────────────────────────────────────────────────────────

    def _convert_lists(self, text: str) -> str:
        """Wiki 列表 → Markdown 列表

        * item → - item（无序列表）
        # item → 1. item（有序列表）
        ** item →   - item（嵌套）
        """
        lines = text.split("\n")
        result: list[str] = []

        for line in lines:
            stripped = line.lstrip()
            match = _WIKI_LIST_ITEM.match(stripped)
            if match:
                prefix = match.group(1)
                content = match.group(2).strip()

                # 计算缩进层级
                indent_level = len(prefix) - 1
                indent = "  " * indent_level

                # 判断类型
                if "#" in prefix:
                    # 有序列表
                    marker = "1."
                    result.append(f"{indent}{marker} {content}")
                elif "*" in prefix:
                    # 无序列表
                    marker = "-"
                    result.append(f"{indent}{marker} {content}")
                else:
                    result.append(f"{indent}{content}")
            else:
                result.append(line)

        return "\n".join(result)

    # ── 定义列表 ─────────────────────────────────────────────────────────────

    def _convert_def_list(self, text: str) -> str:
        """定义列表 ;term:definition → **term**: definition"""
        def _repl(m: re.Match) -> str:
            term = m.group(1).strip()
            definition = m.group(2).strip()
            return f"**{term}**: {definition}"

        return _WIKI_DEF.sub(_repl, text)

    # ── 水平线 ───────────────────────────────────────────────────────────────

    def _convert_hr(self, text: str) -> str:
        """---- → ---"""
        return _WIKI_HR.sub("---", text)

    # ── 后处理 ───────────────────────────────────────────────────────────────

    def _post_process(self, text: str) -> str:
        """清理残余"""
        # 合并多个空行
        text = _MULTI_NEWLINE.sub("\n\n", text)
        # 清理行首空白
        text = _LEADING_WS.sub("", text)
        # 清理空列表项
        text = re.sub(r"^[\s]*[-*]\s*$", "", text, flags=re.MULTILINE)
        # 清理行尾空白
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        # 去首尾空白
        text = text.strip()

        return text

    # ── 降级清理 ─────────────────────────────────────────────────────────────

    def _fallback_clean(self, text: str) -> str:
        """正则降级清理"""
        text = _HTML_COMMENT.sub("", text)
        text = _REF_TAG.sub("", text)
        text = _REF_SELF_CLOSE.sub("", text)
        text = _CATEGORY_LINK.sub("", text)
        text = _FILE_LINK.sub("", text)
        text = _TEMPLATE_RESIDUE.sub("", text)
        text = _TABLE_RESIDUE.sub("", text)
        text = _HTML_TAG.sub("", text)
        text = _WIKI_LINK.sub(r"\2", text)
        text = _WIKI_BOLD.sub(r"**\1**", text)
        text = _WIKI_ITALIC.sub(r"*\1*", text)
        text = self._convert_headings(text)
        text = _MULTI_NEWLINE.sub("\n\n", text)
        return text.strip()

    # ── 长页面拆分 ───────────────────────────────────────────────────────────

    def split_long_page(
        self,
        page: PageInfo,
        markdown: str,
    ) -> list[SplitPage]:
        """将超长页面按标题层级拆分"""
        threshold = self._config.long_page_threshold

        if len(markdown) <= threshold:
            return [SplitPage(title=page.display_title, markdown=markdown)]

        # H2 优先
        sections = self._split_by_heading(markdown, level=2)
        if len(sections) <= 1:
            sections = self._split_by_heading(markdown, level=3)

        if len(sections) <= 1:
            return [SplitPage(title=page.display_title, markdown=markdown)]

        result: list[SplitPage] = []

        if sections[0][0] == "__preamble__":
            pre = sections[0][1]
            if sections[1:]:
                sections[1] = (sections[1][0], pre + "\n\n" + sections[1][1])
            else:
                result.append(SplitPage(title=page.display_title, markdown=pre))
            sections = sections[1:]

        for idx, (heading, content) in enumerate(sections, 1):
            if len(content) > threshold * 1.5:
                subs = self._split_by_heading(content, level=3)
                if len(subs) > 1:
                    for si, (sh, sc) in enumerate(subs, 1):
                        st = f"{page.display_title} - {sh}" if sh != "__preamble__" else f"{page.display_title} ({idx}-{si})"
                        result.append(SplitPage(title=st, markdown=sc, section_level=3))
                    continue

            section_title = f"{page.display_title} - {heading}" if heading != "__preamble__" else f"{page.display_title} ({idx})"
            result.append(SplitPage(title=section_title, markdown=content, section_level=2))

        logger.info(f"长页面拆分: {page.title} → {len(result)} 个子页面")
        return result

    @staticmethod
    def _split_by_heading(markdown: str, level: int = 2) -> list[tuple[str, str]]:
        """按标题级别拆分 Markdown"""
        prefix = "#" * level + " "
        parts = re.split(rf"(?m)^({re.escape(prefix)}.+)$", markdown)
        sections: list[tuple[str, str]] = []

        if not parts:
            return [("__preamble__", markdown)]

        preamble = parts[0].strip()
        if preamble:
            sections.append(("__preamble__", preamble))

        for i in range(1, len(parts), 2):
            heading_text = parts[i].strip()
            heading_clean = re.sub(r"^#+\s*", "", heading_text)
            content = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections.append((heading_clean, f"{heading_text}\n\n{content}" if content else heading_text))

        return sections if sections else [("__preamble__", markdown)]
