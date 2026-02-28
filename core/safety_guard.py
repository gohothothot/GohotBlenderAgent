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

_FOREIGN_TOOLSET_MARKERS = [
    "bash_tool",
    "str_replace",
    "create_file",
    "present_files",
    "fetch_sports_data",
    "view",
]

_FINALIZE_HINTS = [
    "已完成", "完成", "执行完成", "处理完成", "最终结果", "总结",
    "已创建", "已设置", "已添加", "已修改", "已删除", "已应用", "已保存",
    "创建完成", "设置完成", "处理完毕", "完成了",
    "done", "completed", "finished", "final result", "summary",
]

_NON_FINAL_HINTS = [
    "搜索", "查找", "接下来", "下一步", "准备", "计划",
    "将要", "需要先", "先", "然后", "再",
    "search", "next", "plan", "will", "need to",
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


def references_foreign_toolset(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _FOREIGN_TOOLSET_MARKERS)


def looks_like_final_summary(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower().strip()
    if len(lowered) < 8:
        return False
    has_non_final = any(h in lowered for h in _NON_FINAL_HINTS)
    has_final = any(h in lowered for h in _FINALIZE_HINTS)
    # 低风险放宽：较长且不含明确“下一步”语义时，允许视为收尾
    if has_non_final and (not has_final):
        return False
    if has_final:
        return True
    return len(lowered) >= 30
