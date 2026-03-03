"""
RAG retriever for glossary + recipes.
Uses local SimpleVectorStore for persistence and retrieval.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

from .vector_store import get_vector_store

_LOADED = False


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(__file__))


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def ensure_seed_indexed():
    global _LOADED
    if _LOADED:
        return

    store = get_vector_store()
    root = os.path.dirname(__file__)
    glossary_path = os.path.join(root, "seed_glossary.json")
    recipes_path = os.path.join(root, "seed_recipes.json")

    glossary = _load_json(glossary_path, {"entries": []}).get("entries", [])
    recipes = _load_json(recipes_path, {"recipes": []}).get("recipes", [])

    store.delete_prefix("rag_glossary_")
    store.delete_prefix("rag_recipe_")

    for i, e in enumerate(glossary):
        term = str(e.get("term", "")).strip()
        aliases = ", ".join(e.get("aliases", []) or [])
        definition = str(e.get("definition", "")).strip()
        constraints = "; ".join(e.get("constraints", []) or [])
        text = f"术语: {term}\n别名: {aliases}\n定义: {definition}\n约束: {constraints}"
        store.upsert(
            f"rag_glossary_{i}",
            text,
            {
                "kind": "glossary",
                "term": term,
            },
        )

    for i, r in enumerate(recipes):
        rid = str(r.get("id", f"recipe_{i}"))
        title = str(r.get("title", ""))
        task_type = str(r.get("task_type", "general"))
        steps = "\n".join(f"- {s}" for s in (r.get("steps") or []))
        errs = "; ".join(r.get("common_errors", []) or [])
        verify = "; ".join(r.get("verify", []) or [])
        text = f"配方: {title}\n任务类型: {task_type}\n步骤:\n{steps}\n常见错误: {errs}\n验证: {verify}"
        store.upsert(
            f"rag_recipe_{rid}",
            text,
            {
                "kind": "recipe",
                "task_type": task_type,
                "recipe_id": rid,
            },
        )

    store.save()
    _LOADED = True


def retrieve_context(
    normalized_instruction: str,
    extracted_terms: List[str] | None = None,
    task_type: str = "general",
    top_k_glossary: int = 4,
    top_k_recipe: int = 4,
) -> Dict:
    ensure_seed_indexed()
    store = get_vector_store()
    terms = extracted_terms or []
    query = (normalized_instruction or "").strip()
    if terms:
        query = query + "\n术语: " + ", ".join(terms[:8])

    g_hits = store.search(query, top_k=top_k_glossary, metadata_filter={"kind": "glossary"})
    r_hits = store.search(query, top_k=max(top_k_recipe, 6), metadata_filter={"kind": "recipe"})
    if task_type and task_type != "general":
        # prefer matching task_type recipes
        typed = [x for x in r_hits if x.get("metadata", {}).get("task_type") == task_type]
        if typed:
            r_hits = typed[:top_k_recipe]
        else:
            r_hits = r_hits[:top_k_recipe]
    else:
        r_hits = r_hits[:top_k_recipe]

    return {
        "glossary_hits": g_hits,
        "recipe_hits": r_hits,
    }


def build_rag_prompt_block(rag_result: Dict) -> Tuple[str, Dict]:
    g = rag_result.get("glossary_hits", []) or []
    r = rag_result.get("recipe_hits", []) or []
    lines: List[str] = []
    if g:
        lines.append("[RAG术语命中]")
        for item in g[:4]:
            lines.append("- " + (item.get("text", "")[:220]).replace("\n", " "))
    if r:
        lines.append("[RAG配方命中]")
        for item in r[:4]:
            lines.append("- " + (item.get("text", "")[:320]).replace("\n", " "))

    meta = {
        "glossary_count": len(g),
        "recipe_count": len(r),
    }
    return ("\n".join(lines) if lines else ""), meta

