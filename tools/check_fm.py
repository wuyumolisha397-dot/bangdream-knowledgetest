import os, re, sys
sys.stdout.reconfigure(encoding='utf-8')

for root, dirs, files in os.walk('output'):
    for fname in files:
        if not fname.endswith('.md'):
            continue
        filepath = os.path.join(root, fname).replace('\\', '/')
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = f.read()
        if not raw.startswith('---'):
            continue
        parts = raw.split('---', 2)
        if len(parts) < 3:
            continue
        fm = parts[1]
        for i, line in enumerate(fm.split('\n')):
            if re.match(r'^\s*-\s*$', line):
                print(f"{filepath} L{i}: |{line}|")
