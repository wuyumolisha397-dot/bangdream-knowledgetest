# -*- coding: utf-8 -*-
"""
Auto-fix script for output directory markdown quality issues.
Fixes:
1. Remove trailing empty categories in frontmatter (e.g., "  -" with no value)
2. Delete empty reference-only pages (no substantive content)
3. Add placeholder to remaining empty-body pages
"""
import os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
output_dir = 'output'

fixes_applied = []
deletions = []
placeholder_added = []
errors = []

for root, dirs, files in os.walk(output_dir):
    for fname in files:
        if not fname.endswith('.md'):
            continue
        filepath = os.path.join(root, fname).replace('\\', '/')

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception as e:
            errors.append(f"无法读取 {filepath}: {e}")
            continue

        original_raw = raw

        # Split frontmatter and body
        if not raw.startswith('---'):
            continue
        parts = raw.split('---', 2)
        if len(parts) < 3:
            continue

        frontmatter = parts[1]
        body = parts[2]

        # ===== FIX 1: Remove trailing empty categories =====
        # Pattern: a category line that's just "  -" or "  - " with nothing after it
        fm_lines = frontmatter.split('\n')
        new_fm_lines = []
        fm_modified = False
        for i, line in enumerate(fm_lines):
            stripped = line.rstrip()
            # Check if this is an empty category entry (just "  -" or "  - ")
            if re.match(r'^\s*-\s*$', stripped):
                # Remove this line
                fm_modified = True
                continue
            new_fm_lines.append(line)

        if fm_modified:
            new_frontmatter = '\n'.join(new_fm_lines)
            # Also clean up double blank lines
            new_frontmatter = re.sub(r'\n{3,}', '\n\n', new_frontmatter)
            new_raw = '---' + new_frontmatter + '---' + body
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_raw)
                fixes_applied.append((filepath, '移除空的categories条目'))
            except Exception as e:
                errors.append(f"无法写入 {filepath}: {e}")

        # Re-parse after fix
        if fm_modified:
            parts = new_raw.split('---', 2)
            body = parts[2]

        # ===== FIX 2 & 3: Empty body files =====
        body_stripped = body.strip()
        # Remove all markdown headings and whitespace
        body_no_headings = re.sub(r'^#{1,6}\s+[^\n]*\n?', '', body_stripped, flags=re.MULTILINE)
        body_no_headings = body_no_headings.strip()

        # Extract the title for reference
        title_match = re.search(r'^#\s+([^\n]+)', body_stripped, re.MULTILINE)
        doc_title = title_match.group(1) if title_match else fname

        # Check if it's a reference-only page (注释/参考资料 section with no content)
        ref_section = re.search(r'^##\s*(注释|参考资料|外部链接|注释及参考资料|注释与外部链接)', body_stripped, re.MULTILINE)
        is_ref_only = ref_section and len(body_no_headings) < 10

        if is_ref_only:
            # FIX 2: Delete - it's just an empty reference page
            try:
                os.remove(filepath)
                deletions.append((filepath, f'空注释页: {doc_title}'))
            except Exception as e:
                errors.append(f"无法删除 {filepath}: {e}")
        elif len(body_no_headings) < 5:
            # FIX 3: Add placeholder
            placeholder = '\n\n> ⚠️ 此页面内容待补充。\n'
            # Insert after the first heading
            new_body = body_stripped + placeholder
            # Reconstruct file
            if fm_modified:
                new_raw2 = '---' + new_frontmatter + '---\n' + new_body
            else:
                new_raw2 = '---' + frontmatter + '---\n' + new_body
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_raw2)
                placeholder_added.append((filepath, doc_title))
            except Exception as e:
                errors.append(f"无法写入 {filepath}: {e}")

# ===== Report =====
print("=" * 60)
print("自动修复报告")
print("=" * 60)

print(f"\n## 1. 修复 Frontmatter 空 categories")
print(f"数量: {len(fixes_applied)}")
for f, desc in fixes_applied:
    print(f"  ✅ {f}: {desc}")

print(f"\n## 2. 删除空注释/引用页面")
print(f"数量: {len(deletions)}")
for f, desc in deletions:
    print(f"  🗑️  {f}: {desc}")

print(f"\n## 3. 添加内容待补充标记")
print(f"数量: {len(placeholder_added)}")
for f, title in placeholder_added:
    print(f"  📝 {f}: {title}")

if errors:
    print(f"\n## 错误")
    for e in errors:
        print(f"  ❌ {e}")

total = len(fixes_applied) + len(deletions) + len(placeholder_added)
print(f"\n总计修复: {total} 个文件")

# Save detailed report
with open('auto_fix_report.txt', 'w', encoding='utf-8') as f:
    f.write("自动修复详细报告\n")
    f.write("=" * 60 + "\n")
    f.write(f"Frontmatter修复: {len(fixes_applied)}\n")
    for fp, desc in fixes_applied:
        f.write(f"  {fp}: {desc}\n")
    f.write(f"\n删除空页面: {len(deletions)}\n")
    for fp, desc in deletions:
        f.write(f"  {fp}: {desc}\n")
    f.write(f"\n添加占位符: {len(placeholder_added)}\n")
    for fp, title in placeholder_added:
        f.write(f"  {fp}: {title}\n")
    if errors:
        f.write(f"\n错误: {len(errors)}\n")
        for e in errors:
            f.write(f"  {e}\n")
    f.write(f"\n总计: {total}\n")

print("\n详细报告已保存至 auto_fix_report.txt")
