"""
Blender Addon Whitelist Tools.

该模块提供受限工具执行入口，不允许任意 Python 执行。
"""

from __future__ import annotations

from typing import Any

try:
    from .. import tool_definitions
except Exception:  # pragma: no cover - 兼容直接运行/路径异常
    import tool_definitions  # type: ignore


WHITELIST_TOOLS = {
    "scene.get_summary",
    "object.create_cube",
    "object.create_plane",
    "object.create_uv_sphere",
    "object.set_transform",
    "object.add_modifier_bevel",
    "object.add_subdivision_modifier",
    "material.create_principled",
    "material.set_base_color",
    "render.set_engine_cycles",
    "render.set_resolution",
    "render.render_still",
}


def list_whitelist_tools() -> list[str]:
    return sorted(WHITELIST_TOOLS)


def execute_whitelisted_tool(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    if tool not in WHITELIST_TOOLS:
        return {
            "ok": False,
            "success": False,
            "data": None,
            "error": f"工具未在白名单中: {tool}",
            "logs": ["tool_not_whitelisted"],
        }

    result = tool_definitions.execute_tool(tool, args or {})
    success = bool(result.get("success"))
    return {
        "ok": success,
        "success": success,
        "data": result.get("result"),
        "error": result.get("error"),
        "logs": [f"tool={tool}"],
    }
