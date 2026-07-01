# -*- coding: utf-8 -*-
import os, re, sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
output_dir = 'output'

# Issues to detect
empty_body_files = []  # body has essentially nothing (just whitespace + headings)
nav_only_files = []    # body only contains navigation/link text
broken_links = []      # Wiki double-bracket links
truncated_content = [] # Files ending abruptly (no proper ending)
frontmatter_issues = [] # Frontmatter problems
ref_section_only = []  # "注释" or "参考资料" sections only, empty
near_duplicate_body = defaultdict(list)  # near-identical bodies

for root, dirs, files in os.walk(output_dir):
    for fname in files:
        if not fname.endswith('.md'):
            continue
        filepath = os.path.join(root, fname).replace('\\', '/')

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = f.read()
        except:
            continue

        # Split frontmatter and body
        body = raw
        frontmatter_text = ''
        if raw.startswith('---'):
            parts = raw.split('---', 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1]
                body = parts[2]

        # Check frontmatter issues
        if frontmatter_text:
            # Trailing dash in categories list
            if re.search(r'-\s*$', frontmatter_text, re.MULTILINE):
                frontmatter_issues.append((filepath, 'categories末尾有空项'))

        # Check for Wiki double-bracket links [[xxx]]
        wiki_links = re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]', body)
        if wiki_links:
            broken_links.append((filepath, wiki_links))

        # Strip headings and whitespace
        body_stripped = body.strip()
        body_no_headings = re.sub(r'^#{1,6}\s+[^\n]*\n?', '', body_stripped, flags=re.MULTILINE)
        body_no_headings = body_no_headings.strip()

        # Check for essentially empty body (only headings)
        if len(body_no_headings) < 5:
            empty_body_files.append(filepath)

        # Check for "注释" or "参考资料" section that's empty
        # These are pages where the content is just "# Title\n\n## 注释\n" with nothing else
        section_pattern = re.search(r'^##\s*(注释|参考资料|外部链接|注释及参考资料)', body_stripped, re.MULTILINE)
        if section_pattern and len(body_no_headings) < 10:
            ref_section_only.append(filepath)

        # Check for truncated content patterns
        # Files ending with just a header, or with just bullet points
        last_line = body_stripped.split('\n')[-1] if body_stripped else ''
        if re.match(r'^#{1,6}\s+', last_line):
            truncated_content.append((filepath, 'ends with heading'))

        # Near-duplicate detection: hash of body without heading
        body_no_h1 = re.sub(r'^#\s+[^\n]+\n?', '', body, count=1).strip()
        body_hash = body_no_h1[:200]  # first 200 chars as fingerprint
        near_duplicate_body[body_hash].append(filepath)

# Find near-duplicates
near_dups = {h: fs for h, fs in near_duplicate_body.items() if len(fs) > 1}

print("=" * 60)
print("深度扫描结果")
print("=" * 60)

print(f"\n## A. 空正文文档 (仅含标题，无实质内容)")
print(f"数量: {len(empty_body_files)}")
for f in empty_body_files[:40]:
    print(f"  - {f}")
if len(empty_body_files) > 40:
    print(f"  ... 还有 {len(empty_body_files) - 40} 个")

print(f"\n## B. 仅含注释/参考资料的空文档")
print(f"数量: {len(ref_section_only)}")
for f in ref_section_only:
    print(f"  - {f}")

print(f"\n## C. 含 Wiki 双括号链接 [[xxx]]")
print(f"数量: {len(broken_links)}")
for f, links in broken_links[:20]:
    print(f"  - {f}: {links[:5]}")
if len(broken_links) > 20:
    print(f"  ... 还有 {len(broken_links) - 20} 个")

print(f"\n## D. Frontmatter 问题")
print(f"数量: {len(frontmatter_issues)}")
for f, issue in frontmatter_issues[:20]:
    print(f"  - {f}: {issue}")
if len(frontmatter_issues) > 20:
    print(f"  ... 还有 {len(frontmatter_issues) - 20} 个")

print(f"\n## E. 截断内容 (以标题结尾)")
print(f"数量: {len(truncated_content)}")
for f, reason in truncated_content[:20]:
    # Show last 3 lines
    with open(f, 'r', encoding='utf-8') as fh:
        lines = fh.readlines()
    last_lines = ''.join(lines[-4:])
    print(f"  - {f}: {reason}")
    print(f"    最后几行: {last_lines[:200]}")
if len(truncated_content) > 20:
    print(f"  ... 还有 {len(truncated_content) - 20} 个")

print(f"\n## F. 近似重复 (正文前200字相同)")
print(f"近似重复组数: {len(near_dups)}")
for h, files in sorted(near_dups.items(), key=lambda x: -len(x[1]))[:15]:
    print(f"  - 组 ({len(files)}个文件):")
    for f in files[:4]:
        print(f"      {f}")
    if len(files) > 4:
        print(f"      ... 还有 {len(files)-4} 个")

# Write report
with open('deep_scan_report.txt', 'w', encoding='utf-8') as f:
    f.write("=" * 60 + "\n")
    f.write("深度扫描结果\n")
    f.write("=" * 60 + "\n")
    f.write(f"\n## A. 空正文文档: {len(empty_body_files)}\n")
    for fp in empty_body_files:
        f.write(f"  - {fp}\n")
    f.write(f"\n## B. 仅含注释的空文档: {len(ref_section_only)}\n")
    for fp in ref_section_only:
        f.write(f"  - {fp}\n")
    f.write(f"\n## C. Wiki双括号链接: {len(broken_links)}\n")
    for fp, links in broken_links:
        f.write(f"  - {fp}: {links}\n")
    f.write(f"\n## D. Frontmatter问题: {len(frontmatter_issues)}\n")
    for fp, issue in frontmatter_issues:
        f.write(f"  - {fp}: {issue}\n")
    f.write(f"\n## E. 截断内容: {len(truncated_content)}\n")
    for fp, reason in truncated_content:
        f.write(f"  - {fp}: {reason}\n")
    f.write(f"\n## F. 近似重复组: {len(near_dups)}\n")
    for h, files in sorted(near_dups.items(), key=lambda x: -len(x[1])):
        f.write(f"  - ({len(files)} files):\n")
        for fpp in files:
            f.write(f"      {fpp}\n")

print("\nDone! Reports written.")
print(f"Empty body: {len(empty_body_files)}")
print(f"Ref-only: {len(ref_section_only)}")
print(f"Broken Wiki links: {len(broken_links)}")
print(f"Frontmatter issues: {len(frontmatter_issues)}")
print(f"Truncated: {len(truncated_content)}")
print(f"Near-duplicate groups: {len(near_dups)}")
