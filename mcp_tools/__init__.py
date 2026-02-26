"""
MCP 工具实现模块

每个文件实现一组相关工具。
统一通过 execute() 函数调度。
"""


def execute(tool_name: str, arguments: dict) -> dict:
    """统一工具调度入口（备用路径，主路径走 tool_definitions.execute_tool）"""
    try:
        if tool_name.startswith("file_"):
            from . import filesystem
            return filesystem.execute(tool_name, arguments)
        # 其他工具模块可以在这里添加
        return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}
