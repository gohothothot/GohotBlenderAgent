"""
Parse pseudo tool-calls from plain text, e.g.:
shader_clear_nodes(new_mat="Water")
"""

import ast
import json
import re


_CALL_LINE_RE = re.compile(r"^\s*([A-Za-z_]\w*)\((.*)\)\s*$")


def _literal_from_ast(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_literal_from_ast(e) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return [_literal_from_ast(e) for e in node.elts]
    if isinstance(node, ast.Dict):
        return {
            _literal_from_ast(k): _literal_from_ast(v)
            for k, v in zip(node.keys, node.values)
        }
    if isinstance(node, ast.Name):
        lname = node.id.lower()
        if lname == "true":
            return True
        if lname == "false":
            return False
        if lname == "none":
            return None
    raise ValueError("unsupported ast value")


def _parse_kwargs(args_text: str) -> dict:
    if not args_text.strip():
        return {}
    expr = ast.parse(f"f({args_text})", mode="eval")
    call = expr.body
    if not isinstance(call, ast.Call):
        raise ValueError("not a call")
    if call.args:
        raise ValueError("positional args unsupported")
    result = {}
    for kw in call.keywords:
        if kw.arg is None:
            raise ValueError("**kwargs unsupported")
        result[kw.arg] = _literal_from_ast(kw.value)
    return result


def extract_pseudo_tool_calls(text: str, available_tool_names: set) -> list:
    calls = []
    if not text:
        return calls
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue

        # 1) JSON 伪调用格式：
        # {"shader_create_material": {"name":"Water"}}
        # {"shader_get_material_summary": {"material_name":"Water"}}
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and len(obj) == 1:
                name = next(iter(obj.keys()))
                if name in available_tool_names:
                    args = obj.get(name)
                    if isinstance(args, dict):
                        calls.append({"name": name, "arguments": args})
                        continue
                    if args is None:
                        calls.append({"name": name, "arguments": {}})
                        continue
        except Exception:
            pass

        # 2) 函数调用格式：
        # shader_clear_nodes(new_mat="Water")
        m = _CALL_LINE_RE.match(raw_line)
        if not m:
            continue
        name, args_text = m.group(1), m.group(2)
        if name not in available_tool_names:
            continue
        try:
            args = _parse_kwargs(args_text)
            calls.append({"name": name, "arguments": args})
        except Exception:
            continue
    return calls
