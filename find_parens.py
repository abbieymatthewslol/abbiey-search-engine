depth = 0
in_str = None
issues = []

with open('app.py', 'r', encoding='utf-8') as f:
    for lineno, line in enumerate(f, 1):
        stripped = line.rstrip()
        i = 0
        while i < len(stripped):
            c = stripped[i]
            if in_str:
                if c == '\\':
                    i += 2
                    continue
                if isinstance(in_str, str) and stripped[i:i+len(in_str)] == in_str:
                    in_str = None
                    i += len(in_str) if isinstance(in_str, str) else 1
                    continue
            else:
                triple_dq = stripped[i:i+3] == '"""'
                triple_sq = stripped[i:i+3] == "'''"
                if triple_dq:
                    in_str = '"""'
                    i += 3
                    continue
                elif triple_sq:
                    in_str = "'''"
                    i += 3
                    continue
                elif c == '"':
                    in_str = '"'
                elif c == "'":
                    in_str = "'"
                elif c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                elif c == '#':
                    break
            i += 1
        # depth should be 0 at end of logical statement lines
        # flag lines where depth is non-zero AND the line is not a continuation
        if depth > 0 and not stripped.endswith(('\\', ',', '(', '[', '{')):
            if stripped.strip() and not stripped.strip().startswith('#'):
                issues.append((lineno, depth, stripped[:100]))
            if len(issues) > 20:
                break

for ln, d, txt in issues:
    print(f'Line {ln} depth={d}: {txt}')
