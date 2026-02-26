"""
工具层 — 统一入口

从 registry 暴露工具注册表和执行函数。
同时提供向后兼容的 TOOLS / execute_tool 接口。
"""

from .registry import ToolRegistry, get_registry


def execute_tool(tool_name: str, arguments: dict) -> dict:
    """向后兼容：委托给 tool_definitions.execute_tool"""
    from .. import tool_definitions
    return tool_definitions.execute_tool(tool_name, arguments)


def get_tools_list() -> list:
    """向后兼容：返回 TOOLS 列表（延迟加载）"""
    try:
        from .. import tool_definitions
        return tool_definitions.TOOLS
    except (ImportError, AttributeError):
        return []


# 向后兼容：模块级 TOOLS 属性（通过 __getattr__ 延迟加载）
_TOOLS_CACHE = None


def __getattr__(name):
    global _TOOLS_CACHE
    if name == "TOOLS":
        if _TOOLS_CACHE is None:
            _TOOLS_CACHE = get_tools_list()
        return _TOOLS_CACHE
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ToolRegistry", "get_registry", "execute_tool", "get_tools_list"]
