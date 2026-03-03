"""
Mini Rewrite (Agent 2.0 / Step 2)

Natural language -> normalized instruction + extracted terms + task metadata.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any


MODEL_MINI = os.getenv("MODEL_MINI", "").strip()


def _safe_json_extract(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _extract_terms_rule(text: str, limit: int = 16) -> list[str]:
    if not text:
        return []

    blender_terms = [
        "UV Sphere",
        "Cube",
        "Plane",
        "Bevel",
        "Subdivision",
        "Array",
        "Boolean",
        "Principled BSDF",
        "Emission",
        "Roughness",
        "Metallic",
        "IOR",
        "Cycles",
        "EEVEE",
        "Shader Editor",
        "Geometry Nodes",
        "Modifier",
        "FBX",
        "glTF",
        "Normal Map",
    ]
    lowered = text.lower()
    out: list[str] = []
    seen = set()

    for term in blender_terms:
        if term.lower() in lowered and term.lower() not in seen:
            out.append(term)
            seen.add(term.lower())
            if len(out) >= limit:
                return out

    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text):
        lk = token.lower()
        if lk in seen:
            continue
        seen.add(lk)
        out.append(token)
        if len(out) >= limit:
            break
    return out


def _rule_task_type(text: str) -> str:
    t = (text or "").lower()
    tags = []
    if any(k in t for k in ("建模", "模型", "cube", "sphere", "plane", "modifier", "bevel", "subdivision")):
        tags.append("modeling")
    if any(k in t for k in ("材质", "shader", "principled", "roughness", "metallic", "ior", "emission", "节点")):
        tags.append("material")
    if any(k in t for k in ("渲染", "render", "cycles", "eevee", "分辨率", "采样")):
        tags.append("render")
    if any(k in t for k in ("导出", "fbx", "gltf", "glb")):
        tags.append("export")
    if any(k in t for k in ("动画", "animation", "关键帧", "driver")):
        tags.append("animation")
    if not tags:
        return "general"
    return "+".join(tags[:3])


def _rule_complexity(text: str) -> str:
    t = (text or "").strip()
    length = len(t)
    has_multi = any(sep in t for sep in ("，", ",", ";", "并且", "然后", "再", "最后", "同时"))
    if length > 180 or has_multi:
        return "medium"
    if length > 320:
        return "high"
    return "low"


def _call_llm_chat(llm: Any, user_text: str, system_text: str, model: str = "") -> str:
    if llm is None:
        return ""

    messages = [{"role": "user", "content": user_text}]
    if callable(llm):
        # Generic callable adapter: llm(messages, system, model=?)
        try:
            return str(llm(messages=messages, system=system_text, model=model) or "")
        except TypeError:
            return str(llm(messages=messages, system=system_text) or "")

    if hasattr(llm, "chat"):
        chat_fn = getattr(llm, "chat")
        try:
            resp = chat_fn(messages=messages, system=system_text, model=model, tools=None)
        except TypeError:
            try:
                resp = chat_fn(messages=messages, system=system_text, tools=None)
            except TypeError:
                resp = chat_fn(messages=messages, system=system_text)
        # Common response shapes
        text = getattr(resp, "text", None)
        if isinstance(text, str):
            return text
        if isinstance(resp, str):
            return resp
        return str(resp)

    return ""


@dataclass
class MiniRewriter:
    model_mini: str = MODEL_MINI

    def rewrite(self, user_input: str, llm: Any = None) -> dict[str, Any]:
        src = (user_input or "").strip()
        fallback = {
            "normalized_instruction": src,
            "extracted_terms": _extract_terms_rule(src),
            "task_type": _rule_task_type(src),
            "complexity": _rule_complexity(src),
        }
        if not src:
            return fallback

        if llm is None:
            return fallback

        system = (
            "你是 Blender Mini Rewrite 模块。"
            "将用户口语改写为 Blender 标准术语与可执行描述。"
            "必须只返回 JSON，不要输出额外解释。"
            "JSON schema: "
            '{"normalized_instruction":"string","extracted_terms":["string"],'
            '"task_type":"string","complexity":"low|medium|high"}'
        )
        user = (
            "请改写以下用户请求并提取术语。\n"
            "要求：\n"
            "- 术语尽量使用 Blender 官方命名；\n"
            "- 保留关键参数（单位、坐标、颜色、采样等）；\n"
            "- task_type 可组合，例如 modeling+material。\n\n"
            f"用户输入:\n{src}"
        )
        raw = _call_llm_chat(llm, user, system, model=self.model_mini or "")
        parsed = _safe_json_extract(raw)
        if not parsed:
            return fallback

        normalized = str(parsed.get("normalized_instruction", "")).strip() or fallback["normalized_instruction"]
        terms = parsed.get("extracted_terms", [])
        if not isinstance(terms, list):
            terms = fallback["extracted_terms"]
        terms_out = []
        seen = set()
        for it in terms:
            s = str(it).strip()
            if not s:
                continue
            ls = s.lower()
            if ls in seen:
                continue
            seen.add(ls)
            terms_out.append(s)
            if len(terms_out) >= 16:
                break
        if not terms_out:
            terms_out = fallback["extracted_terms"]

        task_type = str(parsed.get("task_type", "")).strip() or fallback["task_type"]
        complexity = str(parsed.get("complexity", "")).strip().lower()
        if complexity not in ("low", "medium", "high"):
            complexity = fallback["complexity"]

        return {
            "normalized_instruction": normalized,
            "extracted_terms": terms_out,
            "task_type": task_type,
            "complexity": complexity,
        }

