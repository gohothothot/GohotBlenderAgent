"""
Shader read planner.

把大节点图读取拆成“先定位再精读”的可复用策略，并给出粗略 token 预估。
"""

from .tool_policies import normalize_tool_args


def estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    # 粗估：中英混合场景下按 4 字符约 1 token
    return max(1, len(text) // 4)


def estimate_inspect_cost(arguments: dict) -> dict:
    limit = int(arguments.get("limit", 30) or 30)
    compact = bool(arguments.get("compact", True))
    include_values = bool(arguments.get("include_values", False))
    node_names = arguments.get("node_names") or []

    if node_names:
        estimated = 80 * len(node_names)
        level = "low" if estimated < 600 else "medium"
    else:
        per_node = 35 if compact else 120
        if include_values:
            per_node += 80
        estimated = per_node * limit
        level = "low" if estimated < 900 else ("medium" if estimated < 3000 else "high")

    return {
        "estimated_output_tokens": estimated,
        "risk_level": level,
    }


def build_search_query(raw_args: dict, normalized_args: dict) -> str:
    parts = []
    for key in ("query", "focus_query", "input_name", "node_type"):
        v = raw_args.get(key) or normalized_args.get(key)
        if v:
            parts.append(str(v))
    if not parts:
        parts = ["principled roughness emission"]
    return " ".join(parts)[:120]


def plan_shader_inspect(raw_args: dict, normalized_args: dict) -> dict:
    include_values_requested = bool(raw_args.get("include_values"))
    has_node_names = bool(raw_args.get("node_names"))
    material_name = normalized_args.get("material_name") or raw_args.get("material_name")

    plan = {
        "auto_search": False,
        "search_args": None,
        "reason": "direct_inspect",
        "cost": estimate_inspect_cost(normalized_args),
    }

    if not material_name:
        plan["reason"] = "missing_material_name"
        return plan

    # 用户要求精读但没给节点名时，先定位节点再精读
    if include_values_requested and not has_node_names:
        query = build_search_query(raw_args, normalized_args)
        search_args = normalize_tool_args("shader_search_index", {
            "material_name": material_name,
            "query": query,
            "top_k": 8,
        })
        plan["auto_search"] = True
        plan["search_args"] = search_args
        plan["reason"] = "include_values_without_node_names"

    return plan
