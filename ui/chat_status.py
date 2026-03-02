"""
Chat status helpers extracted from chat_ui.py.
"""


def infer_route_hint_from_tool(tool_name: str) -> str:
    if tool_name.startswith("meshy_"):
        return "Meshy生成"
    if tool_name.startswith("shader_"):
        return "材质编辑"
    if tool_name.startswith("scene_"):
        return "场景编辑"
    return "常规MCP"
