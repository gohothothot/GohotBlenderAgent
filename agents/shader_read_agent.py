"""
ShaderReadAgent - 着色器读取代理

职责：
- 在执行前构建紧凑的材质上下文
- 优先走 summary -> search_index -> inspect(node_names) 流程
- 减少大节点图直接全量读取导致的 token 膨胀
"""

import re


def _log(msg: str):
    print(f"[ShaderReadAgent] {msg}")


class ShaderReadAgent:
    def __init__(self, run_tool_callable):
        self._run_tool = run_tool_callable

    def build_context(self, user_message: str, max_candidates: int = 5) -> dict:
        """
        返回:
        {
          "success": bool,
          "material_name": str|None,
          "context_text": str,
          "metrics": {...},
        }
        """
        metrics = {
            "materials_count": 0,
            "selected_material": None,
            "search_candidates": 0,
            "used_inspect": False,
        }

        mat = self._select_material(user_message)
        if not mat:
            return {
                "success": False,
                "material_name": None,
                "context_text": "",
                "metrics": metrics,
            }
        metrics["selected_material"] = mat

        summary_res = self._run_tool("shader_get_material_summary", {
            "material_name": mat,
            "detail_level": "basic",
            "include_node_index": True,
            "node_index_limit": 60,
        })
        if not summary_res.get("success"):
            _log(f"summary failed: {summary_res.get('error')}")
            return {
                "success": False,
                "material_name": mat,
                "context_text": "",
                "metrics": metrics,
            }
        summary = summary_res.get("result") or {}

        query = user_message.strip()[:120] if user_message else "principled roughness emission"
        search_res = self._run_tool("shader_search_index", {
            "material_name": mat,
            "query": query,
            "top_k": max(3, min(int(max_candidates or 5), 8)),
        })
        candidates = []
        if search_res.get("success"):
            candidates = (search_res.get("result") or {}).get("candidates", []) or []
        metrics["search_candidates"] = len(candidates)

        inspect_preview = {}
        node_names = [c.get("node_name") for c in candidates if isinstance(c, dict) and c.get("node_name")]
        if node_names:
            inspect_res = self._run_tool("shader_inspect_nodes", {
                "material_name": mat,
                "node_names": node_names[:max_candidates],
                "include_values": True,
                "include_links": True,
                "compact": False,
                "limit": max_candidates,
                "offset": 0,
            })
            if inspect_res.get("success"):
                inspect_preview = inspect_res.get("result") or {}
                metrics["used_inspect"] = True

        context_text = self._format_context(mat, summary, candidates, inspect_preview)
        return {
            "success": True,
            "material_name": mat,
            "context_text": context_text,
            "metrics": metrics,
        }

    def _select_material(self, user_message: str) -> str:
        mats_res = self._run_tool("shader_list_materials", {})
        if not mats_res.get("success"):
            return ""
        mats = mats_res.get("result") or []
        if not isinstance(mats, list) or not mats:
            return ""

        mat_names = [m.get("name", "") for m in mats if isinstance(m, dict) and m.get("name")]
        if not mat_names:
            return ""

        lowered = (user_message or "").lower()
        # 明确提到材质名时优先匹配
        for name in mat_names:
            if name.lower() in lowered:
                return name

        # 简单引号提取作为候选名
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", user_message or "")
        for q in quoted:
            for name in mat_names:
                if q.lower() == name.lower():
                    return name

        return mat_names[0]

    @staticmethod
    def _format_context(material_name: str, summary: dict, candidates: list, inspect_preview: dict) -> str:
        lines = [f"[Shader Context] material={material_name}"]
        if summary:
            lines.append(
                f"- summary: nodes={summary.get('node_count', '?')}, links={summary.get('link_count', '?')}, "
                f"types={len(summary.get('node_types_used', {}) or {})}"
            )
            key_params = (summary.get("key_parameters") or {}).get("Principled BSDF", {})
            if key_params:
                keys = list(key_params.keys())[:8]
                lines.append(f"- principled_keys: {', '.join(keys)}")

        if candidates:
            top = candidates[:8]
            candidate_text = ", ".join(
                f"{c.get('node_name', '')}({c.get('node_type', '')})" for c in top if isinstance(c, dict)
            )
            lines.append(f"- search_hits: {candidate_text}")

        nodes = inspect_preview.get("nodes") if isinstance(inspect_preview, dict) else []
        if isinstance(nodes, list) and nodes:
            lines.append(f"- inspect_nodes: {len(nodes)} focused nodes with values")

        return "\n".join(lines)
