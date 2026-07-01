"""
LLM 摘要标准化——把所有词条统一成 ~500 字的高质量百科正文

用法：
    cd ~/bangdream-knowledgetest
    source .venv/bin/activate

    # 先设置 API
    export OPENAI_API_KEY="your-key"
    export OPENAI_BASE_URL="https://api.openai.com/v1"
    export LLM_MODEL="gpt-4o-mini"

    # 运行
    python tools/llm_normalize.py          # 处理全部
    python tools/llm_normalize.py 角色       # 只处理 角色
    python tools/llm_normalize.py --dry      # 预览模式，不写入
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
import yaml

PROMPT = """你是 BanG Dream! 百科编辑。请把以下萌娘百科词条改写成一篇约 500 字的精炼中文百科条目。

要求：
1. 去除所有 wiki 标记、注释、外部链接、歌词、谱面等非正文内容
2. 保留核心信息：身份、关系、经历、特点、代表作品
3. 语言流畅自然，像一篇微型百科
4. 不要出现"本条目""注：""参考资料"等元描述
5. 不要改变事实，只精简表达
6. 输出纯中文正文，不要 markdown 标题

原始内容：
{content}

改写（约 500 字）："""


async def call_llm(
    client: httpx.AsyncClient, content: str, sem: asyncio.Semaphore
) -> str:
    """调用 LLM 改写"""
    async with sem:
        try:
            resp = await client.post(
                f"{LLM_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [{"role": "user", "content": PROMPT.format(content=content[:6000])}],
                    "max_tokens": 1200,
                    "temperature": 0.3,
                },
                timeout=60,
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"  LLM 调用失败: {e}")
            return ""


async def process_file(
    client: httpx.AsyncClient,
    filepath: Path,
    sem: asyncio.Semaphore,
    dry: bool,
    idx: int,
    total: int,
) -> bool:
    """处理一个文件"""
    with open(filepath, encoding="utf-8") as f:
        raw = f.read()

    # 提取 frontmatter + body
    fm_text = ""
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2]

    # 跳过已经太短的页面（通常是导航/注释残页）
    body_clean = body.strip()
    if len(body_clean) < 100:
        return True

    title = filepath.stem
    print(f"  [{idx}/{total}] {title} ...", end=" ", flush=True)

    new_body = await call_llm(client, body_clean, sem)
    if not new_body:
        print("✗")
        return False

    if dry:
        print(f"✓ (预览) {len(new_body)} 字")
        return True

    # 写入
    new_fm = fm_text
    # 去掉不需要的分类标签
    if new_fm:
        try:
            fm = yaml.safe_load(new_fm)
            if isinstance(fm, dict) and "categories" in fm:
                fm["categories"] = [
                    c for c in fm["categories"]
                    if c not in ("需要长期关注及更新的条目", "使用标题替换的页面",
                                   "含有受损文件链接的页面", "带有失效视频的条目",
                                   "条目中存在只限中国内地播放的音频")
                ]
            new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception:
            pass

    new_raw = f"---\n{new_fm}---\n\n{new_body}\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_raw)

    print(f"✓ {len(new_body)} 字")
    return True


async def main():
    global LLM_KEY, LLM_BASE, LLM_MODEL
    LLM_KEY = os.getenv("OPENAI_API_KEY", "")
    LLM_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

    if not LLM_KEY:
        print("请设置 OPENAI_API_KEY 环境变量")
        return

    dry = "--dry" in sys.argv
    category = None
    for a in sys.argv[1:]:
        if a in ("角色", "歌曲", "乐队", "声优", "其它"):
            category = a
            break

    output_root = Path("output")
    dirs = [category] if category else ["角色", "歌曲", "乐队", "声优", "其它"]
    files = []
    for d in dirs:
        dpath = output_root / d
        if dpath.exists():
            files.extend(sorted(dpath.glob("*.md")))

    print(f"{'[预览模式] ' if dry else ''}处理 {len(files)} 个文件 (分类: {category or '全部'})\n")

    sem = asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=60) as client:
        for i, fp in enumerate(files, 1):
            await process_file(client, fp, sem, dry, i, len(files))
            await asyncio.sleep(0.5)

    print(f"\n{'预览' if dry else '处理'}完成！")


if __name__ == "__main__":
    asyncio.run(main())
