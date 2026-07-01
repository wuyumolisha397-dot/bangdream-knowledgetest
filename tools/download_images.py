"""
从萌娘百科下载角色图片

用法：
    cd ~/bangdream-knowledgetest
    source .venv/bin/activate
    python tools/download_images.py           # 下载 角色 图片
    python tools/download_images.py 声优       # 下载 声优 图片
    python tools/download_images.py 歌曲       # 下载 歌曲 封面
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import unquote

import httpx
import yaml

API_URL = "https://zh.moegirl.org.cn/api.php"

CATEGORY = sys.argv[1] if len(sys.argv) > 1 else "角色"
DIR_MAP = {"角色": "character", "声优": "声优", "歌曲": "song", "乐队": "band"}
SUBDIR = DIR_MAP.get(CATEGORY, CATEGORY)
OUTPUT_DIR = Path(f"output/images/{SUBDIR}")
CHAR_DIR = Path(f"output/{CATEGORY}")


def get_character_pages() -> list[tuple[str, str]]:
    """从 markdown 文件提取 (标题名, wiki 页面标题)"""
    pages = []
    for f in sorted(CHAR_DIR.glob("*.md")):
        with open(f, encoding="utf-8") as fh:
            raw = fh.read()
        # 按 --- 分割取 frontmatter（第2段）
        parts = raw.split("---", 2)
        if len(parts) < 3:
            continue
        fm = yaml.safe_load(parts[1])
        url = fm.get("url", "")
        title = fm.get("title", f.stem)

        # 从 URL 提取 wiki 页面标题
        # https://zh.moegirl.org.cn/%E4%B8%B0%E5%B7%9D%E7%A5%A5%E5%AD%90
        wiki_title = ""
        if url:
            encoded = url.rsplit("/", 1)[-1]
            wiki_title = unquote(encoded)
        if not wiki_title:
            wiki_title = title.split(" - ")[0]

        # 只取主页面（_1 结尾或无后缀）
        if "_1" in f.name or not any(f"_1" != f.name and c in f.name for c in "0123456789"):
            pass  # 所有页面都处理，但去重
        pages.append((title.split(" - ")[0], wiki_title, str(f)))

    # 去重（按角色名）
    seen = set()
    unique = []
    for name, wiki_title, filepath in pages:
        if name not in seen:
            seen.add(name)
            unique.append((name, wiki_title))
    return unique


async def fetch_image(
    client: httpx.AsyncClient, wiki_title: str, _delay: float
) -> tuple[str, str]:
    """获取页面的主图 URL"""
    await asyncio.sleep(_delay)

    # 尝试 1: pageimages (最快)
    try:
        params = {
            "action": "query", "titles": wiki_title,
            "prop": "pageimages", "piprop": "original", "format": "json",
        }
        resp = await client.get(API_URL, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            for pid, page in data.get("query", {}).get("pages", {}).items():
                src = page.get("original", {}).get("source", "")
                if src:
                    return (wiki_title, src)
    except Exception:
        pass

    # 尝试 2: images 列表
    try:
        await asyncio.sleep(2)
        params = {
            "action": "query", "titles": wiki_title,
            "prop": "images", "format": "json",
        }
        resp = await client.get(API_URL, params=params, timeout=30)
        if resp.status_code != 200:
            return (wiki_title, "")
        data = resp.json()
        for pid, page in data.get("query", {}).get("pages", {}).items():
            for img in page.get("images", [])[:3]:
                img_title = img.get("title", "")
                if any(s in img_title.lower() for s in (".svg", "logo", "icon", "symbol")):
                    continue
                await asyncio.sleep(2)
                img_params = {
                    "action": "query", "titles": img_title,
                    "prop": "imageinfo", "iiprop": "url", "format": "json",
                }
                img_resp = await client.get(API_URL, params=img_params, timeout=30)
                if img_resp.status_code != 200:
                    continue
                img_data = img_resp.json()
                for ipage in img_data.get("query", {}).get("pages", {}).values():
                    ii = ipage.get("imageinfo", [{}])[0]
                    url = ii.get("url", "")
                    if url:
                        return (wiki_title, url)
                break
    except Exception:
        pass

    return (wiki_title, "")


async def download_image(client: httpx.AsyncClient, url: str, filepath: Path) -> bool:
    """下载图片到本地"""
    if filepath.exists():
        return True
    try:
        resp = await client.get(url, timeout=30)
        if resp.status_code == 200:
            filepath.write_bytes(resp.content)
            return True
    except Exception:
        pass
    return False


async def main():
    pages = get_character_pages()
    print(f"共 {len(pages)} 个角色\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(
        headers={"User-Agent": "BandoriImageBot/1.0 (knowledge base builder)"},
        follow_redirects=True,
        timeout=30,
    ) as client:
        # 顺序获取，每次间隔 3 秒
        print("=== 获取图片 URL ===")
        results = []
        for i, (name, wt) in enumerate(pages):
            delay = 3.0  # 间隔秒数
            print(f"  [{i+1}/{len(pages)}] {name} ...", end=" ", flush=True)
            wiki_title, url = await fetch_image(client, wt, delay)
            results.append((name, wiki_title, url))
            if url:
                print("✓")
            else:
                print("✗ 无图")

        # 第2步：下载
        print("\n=== 下载图片 ===")
        count = 0
        for name, wiki_title, url in results:
            if not url:
                continue

            ext = ".jpg"
            if ".png" in url.lower():
                ext = ".png"
            elif ".webp" in url.lower():
                ext = ".webp"

            filepath = OUTPUT_DIR / f"{name}{ext}"
            ok = await download_image(client, url, filepath)
            if ok:
                count += 1
                print(f"  ✓ {name} ({filepath.stat().st_size // 1024} KB)")
            else:
                print(f"  ✗ {name}: 下载失败")

            await asyncio.sleep(1.0)

    print(f"\n完成！下载 {count}/{len(pages)} 张图片到 {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
