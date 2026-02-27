"""
Safety guards for tool-first execution.
"""

import re


_PY_PATTERNS = [
    r"```python",
    r"\bimport\s+bpy\b",
    r"\bbpy\.ops\.",
    r"\bbpy\.data\.",
    r"\bdef\s+\w+\(",
    r"\bclass\s+\w+\s*[:\(]",
]

_SCRIPTY_PATTERNS = [
    r"```",
    r"\b[a-zA-Z_]\w*\s*\([^)]*\)",  # 函数调用样式：foo(...)
    r"^\s*-\s*[A-Za-z_]\w*\s*\([^)]*\)\s*$",  # 列表里的调用样式
]


def looks_like_python_script(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    for p in _PY_PATTERNS:
        if re.search(p, lowered):
            return True
    return False


def looks_like_script_output(text: str) -> bool:
    if not text:
        return False
    if looks_like_python_script(text):
        return True
    for p in _SCRIPTY_PATTERNS:
        if re.search(p, text, flags=re.MULTILINE):
            return True
    return False
