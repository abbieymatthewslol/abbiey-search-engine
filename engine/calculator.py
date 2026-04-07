from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any


_ALLOWED_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}

_ALLOWED_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_ALLOWED_FUNCS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log10,
    "ln": math.log,
    "abs": abs,
    "round": round,
}

_ALLOWED_NAMES = {
    "pi": math.pi,
    "e": math.e,
}


class SafeMathError(ValueError):
    pass


def looks_like_math(query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return False
    if re.search(r"[0-9]", q) is None:
        return False
    allowed = re.fullmatch(r"[0-9a-zA-Z\.\+\-\*\/\(\)\s,\^%]+", q)
    if allowed is None:
        return False
    return True


def normalize_expression(query: str) -> str:
    expr = query.strip()
    expr = expr.replace("÷", "/")
    expr = expr.replace("×", "*")
    expr = re.sub(r"(?<!\*)\^(?!\*)", "**", expr)
    expr = re.sub(r"(\d+(?:\.\d+)?)%", r"(\1/100)", expr)
    return expr


def evaluate_expression(query: str) -> float:
    expr = normalize_expression(query)
    try:
        node = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise SafeMathError("Invalid expression syntax.") from exc
    return float(_eval_node(node.body))


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise SafeMathError("Unsupported constant.")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        func = _ALLOWED_BINARY.get(op_type)
        if func is None:
            raise SafeMathError("Unsupported operator.")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return func(left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        func = _ALLOWED_UNARY.get(op_type)
        if func is None:
            raise SafeMathError("Unsupported unary operator.")
        return func(_eval_node(node.operand))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise SafeMathError("Unsupported function call.")
        func_name = node.func.id
        func = _ALLOWED_FUNCS.get(func_name)
        if func is None:
            raise SafeMathError("Unsupported function.")
        args = [_eval_node(arg) for arg in node.args]
        return func(*args)

    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        raise SafeMathError("Unsupported name.")

    raise SafeMathError(f"Unsupported expression node: {type(node).__name__}")


def format_number(value: float) -> str:
    if abs(value) >= 1e16:
        return f"{value:.6e}"
    return f"{value:,.10f}".rstrip("0").rstrip(".")
