"""
Result Parser - 工具结果智能摘要

替代原来的粗暴截断，按工具类型提取关键信息。
"""

import json


def summarize_tool_result(tool_name: str, result: dict, max_chars: int = 300) -> str:
    if not result.get("success"):
        error = result.get("error", "未知错误")
        return f"FAIL: {str(error)[:max_chars]}"

    data = result.get("result", "")

    if tool_name in _SUMMARIZERS:
        return _SUMMARIZERS[tool_name](data, max_chars)

    return _default_summary(data, max_chars)


def _default_summary(data, max_chars: int) -> str:
    if isinstance(data, str):
        return data[:max_chars]
    if isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False)[:max_chars]
    if isinstance(data, list):
        preview = json.dumps(data[:3], ensure_ascii=False)[:max_chars]
        if len(data) > 3:
            preview += f" ...({len(data)} items)"
        return preview
    return str(data)[:max_chars]


def _summarize_scene_info(data, max_chars: int) -> str:
    if not isinstance(data, dict):
        return _default_summary(data, max_chars)
    obj_count = data.get("objects_count", 0)
    objects = data.get("objects", [])
    obj_names = [o.get("name", "?") for o in objects[:10]]
    engine = data.get("render", {}).get("engine", "?")
    return f"场景: {obj_count}个物体 [{', '.join(obj_names)}], 引擎={engine}"[:max_chars]


def _summarize_inspect_nodes(data, max_chars: int) -> str:
    if not isinstance(data, dict):
        return _default_summary(data, max_chars)
    nodes = data.get("nodes", [])
    links = data.get("links", [])
    node_types = [n.get("type", "?") for n in nodes]
    return f"{len(nodes)}个节点, {len(links)}个连接. 类型: {', '.join(node_types)}"[:max_chars]


def _summarize_list(data, max_chars: int) -> str:
    if isinstance(data, list):
        names = [item.get("name", str(item)) if isinstance(item, dict) else str(item) for item in data[:10]]
        result = f"{len(data)} items: [{', '.join(names)}]"
        return result[:max_chars]
    return _default_summary(data, max_chars)


_SUMMARIZERS = {
    "get_scene_info": _summarize_scene_info,
    "shader_inspect_nodes": _summarize_inspect_nodes,
    "list_objects": _summarize_list,
    "shader_list_materials": _summarize_list,
    "scene_list_all_materials": _summarize_list,
    "shader_list_available_nodes": lambda d, m: f"节点类型列表已获取 ({len(d) if isinstance(d, dict) else '?'} 类别)",
}
