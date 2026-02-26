"""
Tool Registry - 工具注册表

单一来源定义所有工具，支持分组、按需筛选。
消除 tools.py 和 mcp_server/server.py 的重复定义。
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ========== 工具分组定义 ==========

TOOL_GROUPS = {
    "basic": [
        "list_objects", "create_primitive", "delete_object",
        "transform_object", "get_object_info", "get_scene_info",
    ],
    "material_basic": [
        "set_material", "set_metallic_roughness",
        "shader_create_material", "shader_delete_material",
        "shader_list_materials", "shader_assign_material",
    ],
    "shader": [
        "shader_inspect_nodes", "shader_add_node", "shader_delete_node",
        "shader_set_node_input", "shader_set_node_property",
        "shader_link_nodes", "shader_unlink_nodes",
        "shader_colorramp_add_stop", "shader_colorramp_remove_stop",
        "shader_colorramp_set_interpolation",
        "shader_batch_add_nodes", "shader_batch_link_nodes",
        "shader_clear_nodes", "shader_get_material_summary",
        "shader_get_node_sockets", "shader_list_available_nodes",
    ],
    "shader_preset": [
        "shader_create_procedural_material",
        "shader_preview_material", "shader_configure_eevee",
    ],
    "toon": [
        "shader_create_toon_material", "shader_convert_to_toon",
    ],
    "scene": [
        "scene_add_light", "scene_modify_light",
        "scene_add_camera", "scene_set_active_camera",
        "scene_add_modifier", "scene_set_modifier_param", "scene_remove_modifier",
        "scene_manage_collection", "scene_set_world",
        "scene_duplicate_object", "scene_parent_object", "scene_set_visibility",
        "scene_get_render_settings", "scene_set_render_settings",
        "scene_get_object_materials", "scene_get_world_info",
        "scene_list_all_materials",
    ],
    "animation": [
        "anim_add_uv_scroll", "anim_add_uv_rotate", "anim_add_uv_scale",
        "anim_add_value_driver", "anim_add_keyframe", "anim_remove_driver",
    ],
    "render": [
        "setup_render", "render_image",
    ],
    "meshy": [
        "meshy_text_to_3d", "meshy_image_to_3d",
    ],
    "search": [
        "web_search", "web_fetch", "web_search_blender",
        "web_analyze_reference", "kb_search", "kb_save",
    ],
    "query": [
        "list_objects", "get_object_info", "get_scene_info",
        "shader_inspect_nodes", "shader_list_materials",
        "shader_get_material_summary", "shader_get_node_sockets",
        "shader_list_available_nodes",
        "scene_get_render_settings", "scene_get_object_materials",
        "scene_get_world_info", "scene_list_all_materials",
        "get_action_log", "get_todo_list",
    ],
    "meta": [
        "get_action_log", "get_todo_list", "complete_todo",
        "analyze_scene",
    ],
    "file": [
        "file_read", "file_write", "file_list", "file_read_project",
    ],
}

# 意图 → 需要的工具组映射
INTENT_TOOL_GROUPS = {
    "create": ["basic", "material_basic", "scene", "shader_preset", "search"],
    "modify": ["basic", "material_basic", "shader", "shader_preset", "scene", "search"],
    "delete": ["basic", "scene"],
    "shader_complex": ["material_basic", "shader", "shader_preset", "search", "query"],
    "toon": ["material_basic", "toon", "shader", "shader_preset"],
    "animation": ["animation", "shader", "basic"],
    "render": ["render", "scene", "query"],
    "generate_3d": ["meshy", "basic", "material_basic"],
    "search": ["search", "query"],
    "query": ["query", "basic", "meta"],
    # general 意图给所有工具组，确保 LLM 能处理任何请求
    "general": [
        "basic", "material_basic", "shader", "shader_preset",
        "toon", "scene", "animation", "render", "meshy",
        "search", "query", "meta", "file",
    ],
}


@dataclass
class ToolDef:
    """工具定义"""
    name: str
    description: str
    input_schema: dict
    groups: list = field(default_factory=list)

    def to_anthropic(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_mcp_name(self) -> str:
        return f"blender_{self.name}"

    def summary(self) -> str:
        """精简描述，用于 Planner（节省 tokens）"""
        return f"{self.name}: {self.description[:80]}"


class ToolRegistry:
    """工具注册表 — 单一来源"""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}
        self._executors: dict[str, Callable] = {}

    def register(self, name: str, description: str, input_schema: dict,
                 executor: Callable = None):
        """注册工具"""
        # 自动计算所属分组
        groups = []
        for group_name, tool_names in TOOL_GROUPS.items():
            if name in tool_names:
                groups.append(group_name)

        self._tools[name] = ToolDef(
            name=name,
            description=description,
            input_schema=input_schema,
            groups=groups,
        )
        if executor:
            self._executors[name] = executor

    def register_executor(self, name: str, executor: Callable):
        """单独注册执行器（工具定义和执行器可分开注册）"""
        self._executors[name] = executor

    def get(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def get_all(self) -> list[ToolDef]:
        return list(self._tools.values())

    def get_by_group(self, group: str) -> list[ToolDef]:
        """获取指定分组的工具"""
        names = TOOL_GROUPS.get(group, [])
        return [self._tools[n] for n in names if n in self._tools]

    def get_by_groups(self, groups: list) -> list[ToolDef]:
        """获取多个分组的工具（去重）"""
        seen = set()
        result = []
        for g in groups:
            for tool in self.get_by_group(g):
                if tool.name not in seen:
                    seen.add(tool.name)
                    result.append(tool)
        return result

    def get_for_intent(self, intent: str) -> list[ToolDef]:
        """根据意图获取相关工具子集"""
        groups = INTENT_TOOL_GROUPS.get(intent, INTENT_TOOL_GROUPS["general"])
        return self.get_by_groups(groups)

    def get_schemas(self, tools: list[ToolDef] = None) -> list[dict]:
        """获取工具 schema 列表（Anthropic 格式）"""
        tools = tools or self.get_all()
        return [t.to_anthropic() for t in tools]

    def get_summaries(self, tools: list[ToolDef] = None) -> str:
        """获取工具摘要（给 Planner 用，节省 tokens）"""
        tools = tools or self.get_all()
        return "\n".join(t.summary() for t in tools)

    def execute(self, name: str, arguments: dict) -> dict:
        """执行工具"""
        executor = self._executors.get(name)
        if not executor:
            return {"success": False, "result": None, "error": f"未知工具: {name}"}
        try:
            return executor(name, arguments)
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    @property
    def count(self) -> int:
        return len(self._tools)


# ========== 全局单例 ==========

_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """获取全局工具注册表（懒加载）"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_all_tools(_registry)
        if _registry.count == 0:
            print("[ToolRegistry] \u26a0\ufe0f WARNING: 注册表为空! 尝试直接导入...")
            # 紧急回退：直接尝试导入
            try:
                import importlib
                td = importlib.import_module("blender_mcp.tool_definitions")
                for tool_def in td.TOOLS:
                    _registry.register(
                        name=tool_def["name"],
                        description=tool_def.get("description", ""),
                        input_schema=tool_def.get("input_schema", {}),
                    )
                    _registry.register_executor(
                        tool_def["name"],
                        lambda n, a, _td=td: _td.execute_tool(n, a),
                    )
                print(f"[ToolRegistry] 回退成功: {_registry.count} 个工具")
            except Exception as e2:
                print(f"[ToolRegistry] 回退也失败: {e2}")
    return _registry


def _register_all_tools(reg: ToolRegistry):
    """从现有 tools.py 导入所有工具定义并注册"""
    try:
        # 延迟导入，避免循环依赖
        from .. import tool_definitions as old_tools
        for tool_def in old_tools.TOOLS:
            reg.register(
                name=tool_def["name"],
                description=tool_def.get("description", ""),
                input_schema=tool_def.get("input_schema", {}),
            )
        # 注册统一执行器
        reg.register_executor("__fallback__", _fallback_executor)
        # 为每个工具注册执行器（委托给旧的 execute_tool）
        for tool_def in old_tools.TOOLS:
            name = tool_def["name"]
            reg.register_executor(name, lambda n, a: old_tools.execute_tool(n, a))
        print(f"[ToolRegistry] 成功注册 {reg.count} 个工具")
    except Exception as e:
        print(f"[ToolRegistry] WARNING: 工具注册失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


def _fallback_executor(name: str, arguments: dict) -> dict:
    """回退执行器"""
    return {"success": False, "result": None, "error": f"工具未注册执行器: {name}"}
