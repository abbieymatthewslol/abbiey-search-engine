import ast
import sys

FILENAME = "app.py"
opens_chars = "([{"
closes_chars = ")]}"
PAIRS = {")": "(", "]": "[", "}": "{"}
CLOSE_FOR = {"(": ")", "[": "]", "{": "}"}


def find_error(lines):
    src = "\n".join(lines)
    try:
        ast.parse(src)
        return None
    except SyntaxError as e:
        return e.lineno


def bracket_stack_up_to(lines, up_to_line_idx):
    """Return stack of (line_idx, bracket_char) for unclosed brackets in lines[:up_to_line_idx]."""
    stack = []
    in_str = None
    for i in range(up_to_line_idx):
        line = lines[i]
        j = 0
        while j < len(line):
            c = line[j]
            if in_str:
                if c == "\\":
                    j += 2
                    continue
                if line[j : j + len(in_str)] == in_str:
                    close_len = len(in_str)
                    in_str = None
                    j += close_len
                    continue
                j += 1
                continue
            # Not in string
            tq = None
            for q in ('"""', "'''"):
                if line[j : j + 3] == q:
                    tq = q
                    break
            if tq:
                in_str = tq
                j += 3
                continue
            if c in ('"', "'"):
                in_str = c
                j += 1
                continue
            if c == "#":
                break
            if c in opens_chars:
                stack.append((i, c))
            elif c in closes_chars:
                if stack and stack[-1][1] == PAIRS[c]:
                    stack.pop()
            j += 1
    return stack


def fix_one(lines, err_line):
    """Find the innermost unclosed bracket before err_line and insert the close char."""
    # err_line is 1-indexed; find bracket open up to err_line-1
    stack = bracket_stack_up_to(lines, err_line - 1)
    if not stack:
        return False

    open_line_idx, open_char = stack[-1]
    close_char = CLOSE_FOR[open_char]

    # Determine indentation from the opening line
    opening_line = lines[open_line_idx]
    indent = len(opening_line) - len(opening_line.lstrip())
    close_line = " " * indent + close_char

    # Insert after err_line - 2 (the line just before the error line, 0-indexed)
    # But first check: is there content on the same line as the opening bracket?
    # If the opening line has content AFTER the bracket, we need to find
    # the last line that's part of the expression (before err_line).
    # Heuristic: find the last non-blank line before err_line-1 that
    # ends with a continuation char (,) or is part of the expression.
    
    # Find the last "content" line before err_line
    insert_after_idx = err_line - 2  # 0-indexed (line before the error line)
    
    # Walk backwards to find actual last line of expression
    # (skip blank lines)
    while insert_after_idx > open_line_idx and not lines[insert_after_idx].strip():
        insert_after_idx -= 1

    print(
        f"  Inserting {close_char!r} after line {insert_after_idx + 1}"
        f" (opened at line {open_line_idx + 1}: {opening_line.strip()[:50]})"
    )

    lines[:] = lines[: insert_after_idx + 1] + [close_line] + lines[insert_after_idx + 1 :]
    return True


def main():
    with open(FILENAME, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    count = 0
    max_iters = 500
    for iteration in range(max_iters):
        err = find_error(lines)
        if err is None:
            print(f"SUCCESS: Fixed {count} errors, no more syntax errors!")
            break
        ctx = lines[err - 1].strip()[:60] if err <= len(lines) else "EOF"
        print(f"Iter {iteration + 1}: error at line {err}: {ctx}")
        ok = fix_one(lines, err)
        if not ok:
            print("  Could not auto-fix — stopping.")
            break
        count += 1
    else:
        print(f"Reached max iterations ({max_iters})")

    with open(FILENAME, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # Final check
    err = find_error(lines)
    if err is not None:
        print(f"REMAINING ERROR at line {err}: {lines[err-1].strip()[:80]}")
        sys.exit(1)
    else:
        print("File is syntactically valid.")


if __name__ == "__main__":
    main()
