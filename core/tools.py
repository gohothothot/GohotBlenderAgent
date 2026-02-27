"""
工具注册表 + 调度器 — 单文件，无导入链
所有工具定义和执行逻辑集中在这里。
工具实现委托给 mcp_tools/ 下的各模块。
[DEVLOG]
- 2026-02-26: 初始版本。延迟加载 tool_definitions.py，内联工具兆底。
  TOOL_GROUPS + INTENT_GROUPS 实现意图→工具子集筛选。
  general 意图限制 ~30 个工具，避免 payload 过大。
"""


def _log(msg: str):
    print(f"[Tools] {msg}")


# ========== 工具分组（用于按意图筛选） ==========

TOOL_GROUPS = {
    "basic": [
        "list_objects", "create_primitive", "delete_object",
        "transform_object", "get_object_info", "get_scene_info",
    ],
    "material": [
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
        "shader_search_index",
        "shader_get_node_sockets", "shader_list_available_nodes",
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
    "render": ["setup_render", "render_image"],
    "meshy": ["meshy_text_to_3d", "meshy_image_to_3d"],
    "search": [
        "web_search", "web_fetch", "web_search_blender",
        "web_analyze_reference", "kb_search", "kb_save",
    ],
    "file": ["file_read", "file_write", "file_list", "file_read_project"],
    "meta": [
        "get_action_log", "get_todo_list", "complete_todo", "analyze_scene",
    ],
}

# 意图 → 工具组
INTENT_GROUPS = {
    "create":      ["basic", "material", "scene", "shader", "search"],
    "modify":      ["basic", "material", "shader", "scene", "search"],
    "delete":      ["basic", "scene"],
    "shader":      ["material", "shader", "search"],
    "toon":        ["material", "toon", "shader"],
    "animation":   ["animation", "shader", "basic"],
    "render":      ["render", "scene"],
    "generate_3d": ["meshy", "basic", "material"],
    "search":      ["search", "meta"],
    "query":       ["basic", "material", "scene", "meta"],
    # general = 常用工具子集（约30个，避免 payload 过大导致 API 500）
    "general":     ["basic", "material", "scene", "shader", "search", "meta", "file"],
}


def get_tools_for_intent(intent: str) -> list:
    """根据意图获取工具定义子集"""
    groups = INTENT_GROUPS.get(intent, INTENT_GROUPS["general"])
    names = set()
    for g in groups:
        names.update(TOOL_GROUPS.get(g, []))
    return [t for t in get_all_tools() if t["name"] in names]


# ========== 工具定义缓存 ==========

_TOOLS_CACHE = None


def get_all_tools() -> list:
    """获取所有工具定义（延迟加载，缓存）"""
    global _TOOLS_CACHE
    if _TOOLS_CACHE is not None:
        return _TOOLS_CACHE

    try:
        from .. import tool_definitions
        _TOOLS_CACHE = tool_definitions.TOOLS
        _log(f"Loaded {len(_TOOLS_CACHE)} tools from tool_definitions")
    except Exception as e:
        _log(f"tool_definitions import failed: {e}, building inline")
        _TOOLS_CACHE = _build_inline_tools()
        _log(f"Built {len(_TOOLS_CACHE)} inline tools")

    return _TOOLS_CACHE


def get_tool_summaries(tools: list = None) -> str:
    """获取工具摘要（给 Planner 用，节省 tokens）"""
    tools = tools or get_all_tools()
    return "\n".join(f"- {t['name']}: {t.get('description', '')[:80]}" for t in tools)


# ========== 工具执行 ==========

def execute_tool(tool_name: str, arguments: dict) -> dict:
    """
    执行工具 — 单一入口点
    
    优先使用 tool_definitions.execute_tool（旧的可靠调度器），
    如果失败则尝试 mcp_tools 模块。
    """
    try:
        from .. import tool_definitions
        return tool_definitions.execute_tool(tool_name, arguments)
    except ImportError:
        return _execute_via_mcp_tools(tool_name, arguments)
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def _execute_via_mcp_tools(tool_name: str, arguments: dict) -> dict:
    """通过 mcp_tools 模块执行（备用路径）"""
    try:
        from ..mcp_tools import execute
        return execute(tool_name, arguments)
    except Exception as e:
        return {"success": False, "result": None, "error": f"工具执行失败: {e}"}


def truncate_result(result_str: str, max_chars: int = 50000) -> str:
    """截断过长的工具结果（默认 50000 字符，基本不截断）"""
    if len(result_str) <= max_chars:
        return result_str
    return result_str[:max_chars] + f"\n...[截断，原始 {len(result_str)} 字符]"


# ========== 内联工具定义（终极回退） ==========

def _build_inline_tools() -> list:
    """如果 tool_definitions.py 无法导入，提供最小工具集"""
    return [
        {"name": "list_objects", "description": "列出场景中所有物体", "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"name": "create_primitive", "description": "创建基础几何体", "input_schema": {"type": "object", "properties": {"primitive_type": {"type": "string", "enum": ["cube", "sphere", "cylinder", "plane", "cone", "torus", "monkey"]}}, "required": ["primitive_type"]}},
        {"name": "delete_object", "description": "删除物体", "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
        {"name": "get_scene_info", "description": "获取场景信息", "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"name": "get_object_info", "description": "获取物体详细信息", "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
        {"name": "transform_object", "description": "变换物体", "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "location": {"type": "array"}, "rotation": {"type": "array"}, "scale": {"type": "array"}}, "required": ["name"]}},
        {"name": "set_material", "description": "设置材质颜色", "input_schema": {"type": "object", "properties": {"object_name": {"type": "string"}, "color": {"type": "array"}}, "required": ["object_name", "color"]}},
    ]
