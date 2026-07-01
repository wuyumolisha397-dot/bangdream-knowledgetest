# -*- coding: utf-8 -*-
import os
import re
import hashlib
import sys
from collections import defaultdict

# Force UTF-8 output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

output_dir = 'output'

empty_files = []
title_only_files = []
wiki_residue_files = defaultdict(list)
short_files = []
all_md_files = []
duplicate_groups = defaultdict(list)

wiki_patterns = {
    '{{template}}': r'\{\{',
    '[[Category:': r'\[\[Category:',
    '<ref>': r'<ref[ >]',
    '[[File:': r'\[\[File:',
    '[[Image:': r'\[\[Image:',
    '__NOTOC__': r'__NOTOC__',
    '__TOC__': r'__TOC__',
    '<!-- comment -->': r'<!--',
    '&nbsp;': r'&nbsp;',
    '[[Media:': r'\[\[Media:',
}

for root, dirs, files in os.walk(output_dir):
    for fname in files:
        if not fname.endswith('.md'):
            continue
        filepath = os.path.join(root, fname).replace('\\', '/')
        all_md_files.append(filepath)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            continue

        if len(raw.strip()) == 0:
            empty_files.append(filepath)
            continue

        body = raw
        frontmatter = ''
        if raw.startswith('---'):
            parts = raw.split('---', 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                body = parts[2]

        # Wiki residues in body only
        for pname, pattern in wiki_patterns.items():
            if re.search(pattern, body):
                wiki_residue_files[filepath].append(pname)

        # Clean body text for word count
        body_text = body
        body_text = re.sub(r'<[^>]+>', '', body_text)
        body_text = re.sub(r'\[([^\]]*)\]\([^\)]+\)', r'\1', body_text)
        body_text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', body_text)
        body_text = re.sub(r'^#{1,6}\s+', '', body_text, flags=re.MULTILINE)
        body_text = re.sub(r'\*{1,3}', '', body_text)
        body_text = re.sub(r'_{1,3}', '', body_text)
        body_text = re.sub(r'^[\s]*[\*\-\+]\s+', '', body_text, flags=re.MULTILINE)
        body_text = re.sub(r'^[\s]*\d+\.\s+', '', body_text, flags=re.MULTILINE)
        body_text = re.sub(r'^>\s*', '', body_text, flags=re.MULTILINE)
        body_text = re.sub(r'^-{3,}$', '', body_text, flags=re.MULTILINE)
        body_text = re.sub(r'```.*?```', '', body_text, flags=re.DOTALL)
        body_text = re.sub(r'`[^`]+`', '', body_text)
        body_text = re.sub(r'\|', ' ', body_text)
        body_text = re.sub(r'\s+', ' ', body_text).strip()

        chinese_chars = len(re.findall(r'[一-鿿豈-﫿]', body_text))
        english_words = len(re.findall(r'[a-zA-Z]+', body_text))
        japanese_chars = len(re.findall(r'[぀-ゟ゠-ヿ]', body_text))

        total_words = chinese_chars + english_words + japanese_chars

        if total_words < 300:
            short_files.append((filepath, total_words))

        body_no_title = re.sub(r'^#\s+[^\n]+\n?', '', body, count=1)
        body_no_title = body_no_title.strip()
        if len(body_no_title) < 10:
            title_only_files.append(filepath)

        body_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()
        duplicate_groups[body_hash].append(filepath)

true_duplicates = {h: files for h, files in duplicate_groups.items() if len(files) > 1}

# ===== OUTPUT =====
lines = []
lines.append("=" * 60)
lines.append("质量报告 - output 目录 Markdown 文件扫描")
lines.append("=" * 60)
lines.append(f"\n总 Markdown 文件数: {len(all_md_files)}")

lines.append(f"\n{'='*60}")
lines.append(f"## 1. 空文档 (0 字节或仅空白字符)")
lines.append(f"数量: {len(empty_files)}")
for f in empty_files:
    lines.append(f"  - {f}")

lines.append(f"\n{'='*60}")
lines.append(f"## 2. 仅含标题的文档 (正文 < 10 字符)")
lines.append(f"数量: {len(title_only_files)}")
for f in title_only_files:
    lines.append(f"  - {f}")

lines.append(f"\n{'='*60}")
lines.append(f"## 3. 短文档 (< 300 字)")
lines.append(f"数量: {len(short_files)} ({len(short_files)*100//len(all_md_files)}%)")
short_files.sort(key=lambda x: x[1])

# Word count distribution
ranges = [(0, 10), (10, 50), (50, 100), (100, 200), (200, 300)]
lines.append("\n字数分布:")
for lo, hi in ranges:
    cnt = sum(1 for _, wc in short_files if lo <= wc < hi)
    lines.append(f"  {lo}-{hi}字: {cnt} 个文件")

lines.append("\n最短的 30 个文档:")
for f, wc in short_files[:30]:
    lines.append(f"  [{wc}字] {f}")

lines.append(f"\n{'='*60}")
lines.append(f"## 4. Wiki 残留")
lines.append(f"含有 Wiki 残留的文件数: {len(wiki_residue_files)}")
for f in sorted(wiki_residue_files.keys()):
    lines.append(f"  - {f}: {wiki_residue_files[f]}")

lines.append(f"\n{'='*60}")
lines.append(f"## 5. 重复文档")
lines.append(f"重复组数量: {len(true_duplicates)}")
total_dup = sum(len(files) for files in true_duplicates.values())
lines.append(f"涉及文件总数: {total_dup}")

# Also check for near-duplicates by checking frontmatter+body hash
# Check if files with same title exist
title_map = defaultdict(list)
for fpath in all_md_files:
    fname = os.path.basename(fpath)
    title_map[fname].append(fpath)
same_name = {n: ps for n, ps in title_map.items() if len(ps) > 1}
lines.append(f"\n## 6. 同名文件 (不同目录)")
lines.append(f"同名文件组数: {len(same_name)}")
for name, paths in sorted(same_name.items())[:30]:
    lines.append(f"  - {name}: {len(paths)} 个")
    for p in paths:
        lines.append(f"      {p}")
if len(same_name) > 30:
    lines.append(f"  ... 还有 {len(same_name)-30} 组")

# Category analysis
lines.append(f"\n{'='*60}")
lines.append(f"## 7. 子目录分布")
for d in sorted(os.listdir(output_dir)):
    dpath = os.path.join(output_dir, d)
    if os.path.isdir(dpath):
        cnt = sum(1 for _ in os.listdir(dpath) if _.endswith('.md'))
        lines.append(f"  {d}: {cnt} 个文件")

# Write to file
output_path = 'quality_report.txt'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Report written to {output_path}")
print(f"Total files: {len(all_md_files)}")
print(f"Empty: {len(empty_files)}")
print(f"Title-only: {len(title_only_files)}")
print(f"Short (<300 words): {len(short_files)}")
print(f"Wiki residues: {len(wiki_residue_files)}")
print(f"Duplicate groups: {len(true_duplicates)}")
print(f"Same-name groups: {len(same_name)}")
