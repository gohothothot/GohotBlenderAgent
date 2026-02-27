"""
Tool argument normalization policies.

将高体量工具的参数收敛到安全默认值，减少上下文膨胀风险。
"""


def normalize_tool_args(tool_name: str, arguments: dict) -> dict:
    args = dict(arguments or {})

    if tool_name == "shader_get_material_summary":
        args.setdefault("detail_level", "basic")
        args.setdefault("include_node_index", True)
        args.setdefault("node_index_limit", 60)
        try:
            args["node_index_limit"] = max(20, min(int(args["node_index_limit"]), 200))
        except Exception:
            args["node_index_limit"] = 60

    elif tool_name == "shader_inspect_nodes":
        args.setdefault("compact", True)
        args.setdefault("include_links", True)
        args.setdefault("include_values", False)
        args.setdefault("limit", 30)
        args.setdefault("offset", 0)
        try:
            args["limit"] = max(1, min(int(args["limit"]), 80))
        except Exception:
            args["limit"] = 30
        try:
            args["offset"] = max(0, int(args["offset"]))
        except Exception:
            args["offset"] = 0

        # 未指定节点名时，强制保持紧凑模式，避免大图全量值回传
        if not args.get("node_names"):
            args["compact"] = True
            if args.get("include_values"):
                args["include_values"] = False

    elif tool_name == "shader_search_index":
        args.setdefault("top_k", 10)
        try:
            args["top_k"] = max(1, min(int(args["top_k"]), 30))
        except Exception:
            args["top_k"] = 10

    return args
