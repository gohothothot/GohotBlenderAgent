"""
Knowledge Base - 本地 RAG 知识库

积累网络搜索结果和成功的 shader 配方，供 Agent 后续查询。
避免重复搜索，减少幻觉，提升材质创建质量。
"""

import json
import os
from datetime import datetime
from typing import Optional

_KB_DIR = os.path.join(os.path.dirname(__file__), "knowledge")
_KB_FILE = os.path.join(_KB_DIR, "knowledge_base.json")
_kb_cache = None


def _ensure_kb():
    global _kb_cache
    os.makedirs(_KB_DIR, exist_ok=True)
    if _kb_cache is None:
        if os.path.exists(_KB_FILE):
            try:
                with open(_KB_FILE, "r", encoding="utf-8") as f:
                    _kb_cache = json.load(f)
            except Exception:
                _kb_cache = {"entries": [], "version": 1}
        else:
            _kb_cache = {"entries": [], "version": 1}
    return _kb_cache


def _save_kb():
    if _kb_cache is None:
        return
    os.makedirs(_KB_DIR, exist_ok=True)
    try:
        with open(_KB_FILE, "w", encoding="utf-8") as f:
            json.dump(_kb_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[KB] 保存失败: {e}")


def save_search_result(query: str, results: list, category: str = "general"):
    kb = _ensure_kb()
    entry = {
        "type": "search",
        "query": query,
        "category": category,
        "content": results[:5] if isinstance(results, list) else str(results)[:2000],
        "created_at": datetime.now().isoformat(),
        "use_count": 0,
    }
    kb["entries"].append(entry)

    if len(kb["entries"]) > 500:
        kb["entries"] = kb["entries"][-500:]

    _save_kb()


def save_shader_recipe(name: str, description: str, node_setup: dict, tags: list = None):
    kb = _ensure_kb()
    entry = {
        "type": "shader_recipe",
        "name": name,
        "description": description,
        "node_setup": node_setup,
        "tags": tags or [],
        "created_at": datetime.now().isoformat(),
        "use_count": 0,
    }
    kb["entries"].append(entry)
    _save_kb()


def search_kb(query: str, max_results: int = 5) -> list:
    kb = _ensure_kb()
    query_lower = query.lower()
    keywords = query_lower.split()

    scored = []
    for entry in kb["entries"]:
        score = 0
        searchable = ""

        if entry["type"] == "search":
            searchable = f"{entry.get('query', '')} {entry.get('category', '')} {json.dumps(entry.get('content', ''))}"
        elif entry["type"] == "shader_recipe":
            searchable = f"{entry.get('name', '')} {entry.get('description', '')} {' '.join(entry.get('tags', []))}"

        searchable_lower = searchable.lower()
        for kw in keywords:
            if kw in searchable_lower:
                score += 1

        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, entry in scored[:max_results]:
        entry["use_count"] = entry.get("use_count", 0) + 1
        results.append(entry)

    if results:
        _save_kb()

    return results


def kb_search_tool(query: str) -> dict:
    try:
        results = search_kb(query)
        if not results:
            return {
                "success": True,
                "result": f"本地知识库中未找到 '{query}' 的相关内容。建议使用 web_search 搜索网络。",
                "error": None,
            }

        formatted = []
        for r in results:
            if r["type"] == "search":
                formatted.append(f"[搜索缓存] 查询: {r.get('query', '')}\n{json.dumps(r.get('content', ''), ensure_ascii=False)[:300]}")
            elif r["type"] == "shader_recipe":
                formatted.append(f"[Shader配方] {r.get('name', '')}: {r.get('description', '')}\n标签: {', '.join(r.get('tags', []))}")

        output = f"知识库搜索 '{query}' 的结果:\n\n" + "\n\n---\n\n".join(formatted)
        return {"success": True, "result": output, "error": None}

    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def kb_save_tool(name: str, description: str, tags: str = "") -> dict:
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        save_shader_recipe(name, description, {}, tag_list)
        return {
            "success": True,
            "result": f"已保存到知识库: {name}",
            "error": None,
        }
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def execute_kb_tool(tool_name: str, arguments: dict) -> dict:
    try:
        if tool_name == "kb_search":
            return kb_search_tool(**arguments)
        elif tool_name == "kb_save":
            return kb_save_tool(**arguments)
        return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}
