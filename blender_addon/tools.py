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
    "controller_create_empty",
    "controller_add_copy_location",
    "controller_add_copy_rotation",
    "controller_add_copy_scale",
    "controller_add_track_to",
    "controller_add_custom_property",
    "controller_add_child_of",
    "controller_set_constraint_influence",
    "controller_remove_constraint",
    "object_rename",
    "object_select_set_active",
    "object_duplicate_linked",
    "scene_apply_modifier",
    "scene_set_frame_range",
    "scene_set_current_frame",
    "scene_save_blend",
    "scene_export_fbx",
    "scene_export_gltf",
    "gn_create_modifier",
    "gn_add_node",
    "gn_link_nodes",
    "gn_set_input_default",
    "gn_expose_group_input",
    "gn_get_summary",
    "gn_remove_node",
    "gn_auto_layout_nodes",
    "gn_find_node_by_type",
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
