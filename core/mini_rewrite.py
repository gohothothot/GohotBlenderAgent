"""
Mini rewrite layer:
user natural language -> normalized instruction + extracted terms + task_type.

If LLM is unavailable, fallback to rule-based extraction.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List


def _rule_task_type(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ("材质", "shader", "roughness", "metallic", "ior", "节点")):
        return "shader"
    if any(k in t for k in ("渲染", "render", "cycles", "eevee", "分辨率")):
        return "render"
    if any(k in t for k in ("修改器", "bevel", "array", "subdivision", "modifier")):
        return "modifier"
    if any(k in t for k in ("相机", "灯光", "场景", "world")):
        return "scene"
    if any(k in t for k in ("导出", "fbx", "gltf", "glb")):
        return "export"
    return "general"


def _extract_terms_rule(text: str) -> List[str]:
    if not text:
        return []
    kws = re.findall(r"[A-Za-z_][A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text)
    seen = set()
    out = []
    for k in kws:
        lk = k.lower()
        if lk in seen:
            continue
        seen.add(lk)
        out.append(k)
        if len(out) >= 12:
            break
    return out


def mini_rewrite(user_message: str, llm=None) -> Dict:
    """
    Return:
    {
      "normalized_instruction": str,
      "extracted_terms": [...],
      "task_type": str,
      "notes": [...]
    }
    """
    fallback = {
        "normalized_instruction": (user_message or "").strip(),
        "extracted_terms": _extract_terms_rule(user_message),
        "task_type": _rule_task_type(user_message),
        "notes": [],
    }
    if llm is None:
        return fallback

    prompt = (
        "你是 Blender 指令改写器（mini）。"
        "将用户口语改写为可执行、参数尽量完整的标准化指令，提取关键术语，并判定 task_type。"
        "仅输出 JSON："
        "{\"normalized_instruction\":\"...\",\"extracted_terms\":[\"...\"],\"task_type\":\"shader|scene|modifier|render|export|general\",\"notes\":[\"...\"]}"
    )
    try:
        resp = llm.chat(
            messages=[{"role": "user", "content": user_message}],
            system=prompt,
            tools=None,
        )
        text = (resp.text or "").strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return fallback
        obj = json.loads(m.group(0))
        normalized = str(obj.get("normalized_instruction", "")).strip() or fallback["normalized_instruction"]
        terms = obj.get("extracted_terms", [])
        if not isinstance(terms, list):
            terms = fallback["extracted_terms"]
        task_type = str(obj.get("task_type", "")).strip() or fallback["task_type"]
        notes = obj.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        return {
            "normalized_instruction": normalized,
            "extracted_terms": [str(x) for x in terms][:16],
            "task_type": task_type,
            "notes": [str(x) for x in notes][:8],
        }
    except Exception:
        return fallback

