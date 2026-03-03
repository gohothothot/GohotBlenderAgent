"""
Dual-track RAG stores (Agent 2.0 / Step 2)

- GlossaryStore: terminology dictionary
- RecipeStore: task recipes
- auto_retrieve: combines both with char budget
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

try:
    from .doc_index import SkillCapabilityStore
except Exception:
    try:
        from backend.rag.doc_index import SkillCapabilityStore  # type: ignore
    except Exception:
        SkillCapabilityStore = None  # type: ignore


MAX_RAG_CHARS = int(os.getenv("MAX_RAG_CHARS", "1200"))


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _load_json(path: str, default: dict) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return obj if isinstance(obj, dict) else default
    except Exception:
        return default


def _save_json(path: str, payload: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _default_glossary_entries() -> list[dict[str, Any]]:
    # 30+ high-frequency Blender terms
    return [
        {"term": "Principled BSDF", "aliases": ["PBR", "principled shader"], "definition": "Blender 的物理渲染着色器，支持 Metallic/Roughness/Emission 等参数。", "constraints": ["只能在 Material Shader Editor 中使用", "不能直接用于 World Shader"], "blender_api": "bpy.types.ShaderNodeBsdfPrincipled"},
        {"term": "Emission", "aliases": ["Emissive", "发光"], "definition": "用于让材质自发光，常与 Emission Strength 配合。", "constraints": ["强度过高会导致过曝"], "blender_api": "bpy.types.ShaderNodeEmission"},
        {"term": "Roughness", "aliases": ["粗糙度"], "definition": "控制高光散射，值越低越镜面。", "constraints": ["推荐范围 0.0-1.0"], "blender_api": "bpy.types.ShaderNodeBsdfPrincipled.inputs['Roughness']"},
        {"term": "Metallic", "aliases": ["金属度"], "definition": "控制材质金属属性，通常 0 或 1。", "constraints": ["非金属材质不建议高值"], "blender_api": "bpy.types.ShaderNodeBsdfPrincipled.inputs['Metallic']"},
        {"term": "IOR", "aliases": ["折射率"], "definition": "控制折射行为，玻璃约 1.45，水约 1.333。", "constraints": ["仅在透射/折射场景明显"], "blender_api": "bpy.types.ShaderNodeBsdfPrincipled.inputs['IOR']"},
        {"term": "Normal Map", "aliases": ["法线贴图"], "definition": "用纹理模拟细节法线变化。", "constraints": ["颜色空间应设为 Non-Color"], "blender_api": "bpy.types.ShaderNodeNormalMap"},
        {"term": "UV Map", "aliases": ["UV"], "definition": "网格纹理坐标映射。", "constraints": ["贴图失真通常需要重新展开 UV"], "blender_api": "bpy.types.Mesh.uv_layers"},
        {"term": "Texture Coordinate", "aliases": ["纹理坐标节点"], "definition": "提供 Generated/UV/Object 等坐标输出。", "constraints": ["不同坐标源效果差异较大"], "blender_api": "bpy.types.ShaderNodeTexCoord"},
        {"term": "Mapping", "aliases": ["映射节点"], "definition": "用于平移/旋转/缩放纹理坐标。", "constraints": ["与 Texture Coordinate 节点配套使用"], "blender_api": "bpy.types.ShaderNodeMapping"},
        {"term": "ColorRamp", "aliases": ["色带"], "definition": "将输入值映射到颜色区间。", "constraints": ["卡通风格常用 CONSTANT 插值"], "blender_api": "bpy.types.ShaderNodeValToRGB"},
        {"term": "Bump", "aliases": ["凹凸"], "definition": "基于高度图模拟表面细节。", "constraints": ["强度过高会破坏观感"], "blender_api": "bpy.types.ShaderNodeBump"},
        {"term": "Displacement", "aliases": ["置换"], "definition": "真实改变几何表面位移。", "constraints": ["需要足够网格细分"], "blender_api": "bpy.types.ShaderNodeDisplacement"},
        {"term": "Bevel Modifier", "aliases": ["倒角修改器", "bevel"], "definition": "为边缘增加倒角，提升硬表面真实感。", "constraints": ["宽度要匹配模型尺度"], "blender_api": "bpy.types.BevelModifier"},
        {"term": "Subdivision Surface", "aliases": ["Subsurf", "细分曲面"], "definition": "细分并平滑网格。", "constraints": ["渲染级别过高会影响性能"], "blender_api": "bpy.types.SubsurfModifier"},
        {"term": "Array Modifier", "aliases": ["阵列修改器"], "definition": "复制对象形成规则阵列。", "constraints": ["注意相对偏移与数量"], "blender_api": "bpy.types.ArrayModifier"},
        {"term": "Mirror Modifier", "aliases": ["镜像修改器"], "definition": "按轴镜像几何。", "constraints": ["常需启用 Clipping 防止裂缝"], "blender_api": "bpy.types.MirrorModifier"},
        {"term": "Boolean Modifier", "aliases": ["布尔修改器"], "definition": "执行并/差/交布尔运算。", "constraints": ["网格拓扑不干净时易失败"], "blender_api": "bpy.types.BooleanModifier"},
        {"term": "Solidify Modifier", "aliases": ["实体化修改器"], "definition": "给薄壳网格增加厚度。", "constraints": ["法线方向影响内外厚度"], "blender_api": "bpy.types.SolidifyModifier"},
        {"term": "Decimate Modifier", "aliases": ["简化修改器"], "definition": "减少面数，优化性能。", "constraints": ["过度简化会损失形体"], "blender_api": "bpy.types.DecimateModifier"},
        {"term": "Shade Smooth", "aliases": ["平滑着色"], "definition": "平滑面法线显示。", "constraints": ["硬边需要配合 Auto Smooth"], "blender_api": "bpy.ops.object.shade_smooth"},
        {"term": "Cycles", "aliases": ["路径追踪"], "definition": "物理正确渲染引擎。", "constraints": ["质量高但速度较慢"], "blender_api": "bpy.context.scene.render.engine='CYCLES'"},
        {"term": "EEVEE", "aliases": ["实时渲染"], "definition": "实时渲染引擎，交互快。", "constraints": ["某些效果需额外开关"], "blender_api": "bpy.context.scene.render.engine='BLENDER_EEVEE'"},
        {"term": "Sample Count", "aliases": ["采样数"], "definition": "控制渲染噪点与时间。", "constraints": ["采样越高越慢"], "blender_api": "bpy.types.CyclesRenderSettings.samples"},
        {"term": "World Shader", "aliases": ["世界着色器"], "definition": "控制环境光与背景。", "constraints": ["与材质节点树分离"], "blender_api": "bpy.types.World.node_tree"},
        {"term": "HDRI", "aliases": ["环境贴图"], "definition": "用于环境光照与反射。", "constraints": ["注意强度与旋转"], "blender_api": "bpy.types.ShaderNodeTexEnvironment"},
        {"term": "Camera Focal Length", "aliases": ["焦距"], "definition": "控制视角透视效果。", "constraints": ["单位 mm"], "blender_api": "bpy.types.Camera.lens"},
        {"term": "DOF", "aliases": ["景深"], "definition": "模拟镜头景深。", "constraints": ["需设置对焦对象/距离"], "blender_api": "bpy.types.Camera.dof"},
        {"term": "FBX Export", "aliases": ["导出FBX"], "definition": "常见 DCC 交换格式导出。", "constraints": ["注意坐标轴和缩放"], "blender_api": "bpy.ops.export_scene.fbx"},
        {"term": "glTF Export", "aliases": ["导出glTF", "GLB"], "definition": "实时引擎常用格式。", "constraints": ["材质兼容性需验证"], "blender_api": "bpy.ops.export_scene.gltf"},
        {"term": "Object Mode", "aliases": ["对象模式"], "definition": "对象级编辑模式。", "constraints": ["许多操作仅在 Object Mode 可用"], "blender_api": "bpy.ops.object.mode_set(mode='OBJECT')"},
        {"term": "Edit Mode", "aliases": ["编辑模式"], "definition": "网格顶点边面编辑模式。", "constraints": ["部分对象运算前需切回 Object Mode"], "blender_api": "bpy.ops.object.mode_set(mode='EDIT')"},
        {"term": "Geometry Nodes", "aliases": ["几何节点"], "definition": "基于节点的程序化建模系统。", "constraints": ["依赖节点组输入输出定义"], "blender_api": "bpy.types.GeometryNodeTree"},
        {"term": "Compositor", "aliases": ["合成节点"], "definition": "后期图像合成流程。", "constraints": ["与材质节点是不同树"], "blender_api": "bpy.types.CompositorNodeTree"},
    ]


def _default_recipe_items() -> list[dict[str, Any]]:
    return [
        {
            "task": "create_basic_mesh",
            "description": "创建基础网格并设置位置尺度。",
            "preconditions": ["Object Mode"],
            "steps": ["object.create_cube(size_m, location)", "object.set_transform(name/object_name, location/rotation/scale)"],
            "common_errors": ["对象命名不确定导致后续步骤找不到对象"],
            "fix": "先 scene.get_summary 确认对象名称后再修改。",
            "task_type": "modeling",
        },
        {
            "task": "apply_modifier",
            "description": "安全地应用修改器（避免多用户数据块报错）。",
            "preconditions": ["对象必须在 Object Mode", "数据块不能有多个用户"],
            "steps": ["bpy.ops.object.mode_set(mode='OBJECT')", "bpy.ops.object.modifier_apply(modifier=name)"],
            "common_errors": ["RuntimeError: Cannot apply to a multi-user: ..."],
            "fix": "先调用 bpy.ops.object.make_single_user(object=True, obdata=True)。",
            "task_type": "modeling",
        },
        {
            "task": "bevel_hard_surface",
            "description": "硬表面模型的倒角流程。",
            "preconditions": ["目标对象存在"],
            "steps": ["object.add_modifier_bevel(object_name, width, segments)", "scene.get_summary 检查修改器生效"],
            "common_errors": ["width 过大导致模型破面"],
            "fix": "按模型尺度减少 width，或提高 segments 并分步验证。",
            "task_type": "modeling",
        },
        {
            "task": "subdivision_smooth",
            "description": "通过细分曲面提升平滑度。",
            "preconditions": ["目标对象存在"],
            "steps": ["object.add_subdivision_modifier(object_name, levels, render_levels)", "scene.get_summary 验证修改器堆栈"],
            "common_errors": ["levels 过高导致性能骤降"],
            "fix": "先用 levels=1~2 预览，再逐步提高。",
            "task_type": "modeling",
        },
        {
            "task": "assign_principled_material",
            "description": "创建并赋予 Principled 材质。",
            "preconditions": ["对象已创建并可选中"],
            "steps": ["material.create_principled(material_name, object_name)", "material.set_base_color(material_name/object_name, rgba)"],
            "common_errors": ["对象未绑定材质导致颜色设置无效"],
            "fix": "先 create_principled，再 set_base_color。",
            "task_type": "material",
        },
        {
            "task": "emission_lookdev",
            "description": "创建发光风格材质并进行亮度控制。",
            "preconditions": ["材质节点可编辑"],
            "steps": ["创建 Emission 节点", "设置颜色与 Strength", "与输出节点连接并验证"],
            "common_errors": ["强度过高导致严重过曝"],
            "fix": "逐级提升 Strength（如 2 -> 5 -> 10）并观察。",
            "task_type": "material",
        },
        {
            "task": "render_cycles_still",
            "description": "Cycles 静帧渲染标准流程。",
            "preconditions": ["场景对象与相机存在"],
            "steps": ["render.set_engine_cycles()", "render.set_resolution(width, height)", "render.render_still(path)"],
            "common_errors": ["输出路径不可写或为空"],
            "fix": "改用绝对路径并确保目录可写。",
            "task_type": "render",
        },
        {
            "task": "eevee_preview_render",
            "description": "EEVEE 快速预览渲染流程。",
            "preconditions": ["场景基础光照可用"],
            "steps": ["切换 EEVEE 引擎", "降低采样和分辨率进行预览", "确认效果后再高质量渲染"],
            "common_errors": ["透射/反射效果与预期不符"],
            "fix": "检查 EEVEE 相关渲染开关（SSR/Refraction）。",
            "task_type": "render",
        },
        {
            "task": "export_fbx_pipeline",
            "description": "导出 FBX 前的检查与导出流程。",
            "preconditions": ["对象尺度与朝向已统一"],
            "steps": ["应用变换", "检查法线/材质", "file.export_fbx(path)"],
            "common_errors": ["引擎中尺度不正确"],
            "fix": "导出前统一单位与 Apply Scale。",
            "task_type": "export",
        },
        {
            "task": "export_gltf_pipeline",
            "description": "导出 glTF/GLB 的兼容流程。",
            "preconditions": ["材质节点尽量使用兼容子集"],
            "steps": ["检查材质兼容", "file.export_gltf(path)", "目标引擎导入验证"],
            "common_errors": ["复杂节点在目标引擎表现异常"],
            "fix": "改用 Principled + 贴图烘焙路径。",
            "task_type": "export",
        },
    ]


@dataclass
class GlossaryStore:
    path: str
    entries: list[dict[str, Any]]

    @classmethod
    def create(cls, path: str | None = None) -> "GlossaryStore":
        p = path or os.path.join(os.path.dirname(__file__), "seed_glossary.json")
        if not os.path.exists(p):
            _save_json(p, {"entries": _default_glossary_entries()})
        obj = _load_json(p, {"entries": []})
        entries = obj.get("entries", [])
        if not isinstance(entries, list):
            entries = []
        return cls(path=p, entries=entries)

    def retrieve(self, extracted_terms: list[str], top_k: int = 8) -> list[dict[str, Any]]:
        if not extracted_terms:
            return []
        q_terms = [_norm(t) for t in extracted_terms if _norm(t)]
        if not q_terms:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for e in self.entries:
            term = _norm(str(e.get("term", "")))
            aliases = [_norm(x) for x in (e.get("aliases", []) or [])]
            hay = [term] + aliases
            score = 0.0
            for q in q_terms:
                if q == term or q in aliases:
                    score += 3.0
                elif any(q in h or h in q for h in hay if h):
                    score += 1.0
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[: max(1, int(top_k))]]


@dataclass
class RecipeStore:
    path: str
    recipes: list[dict[str, Any]]

    @classmethod
    def create(cls, path: str | None = None) -> "RecipeStore":
        p = path or os.path.join(os.path.dirname(__file__), "seed_recipes.json")
        if not os.path.exists(p):
            _save_json(p, {"recipes": _default_recipe_items()})
        obj = _load_json(p, {"recipes": []})
        recipes = obj.get("recipes", [])
        if not isinstance(recipes, list):
            recipes = []
        return cls(path=p, recipes=recipes)

    def retrieve(self, task_type: str, extracted_terms: list[str], top_k: int = 5) -> list[dict[str, Any]]:
        tt = _norm(task_type)
        q_terms = [_norm(t) for t in extracted_terms if _norm(t)]
        scored: list[tuple[float, dict[str, Any]]] = []
        for r in self.recipes:
            r_tt = _norm(str(r.get("task_type", "")))
            score = 0.0
            if tt and r_tt:
                if tt == r_tt:
                    score += 3.0
                elif tt in r_tt or r_tt in tt:
                    score += 1.5
            text = " ".join(
                [
                    str(r.get("task", "")),
                    str(r.get("description", "")),
                    " ".join(r.get("steps", []) or []),
                    " ".join(r.get("common_errors", []) or []),
                ]
            ).lower()
            for q in q_terms:
                if q and q in text:
                    score += 1.0
            if score > 0:
                scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[: max(1, int(top_k))]]


def _build_context_block(glossary_hits: list[dict], recipe_hits: list[dict], capability_hits: list[dict], max_chars: int) -> str:
    lines: list[str] = []
    if glossary_hits:
        lines.append("[Glossary]")
        for g in glossary_hits:
            lines.append(
                f"- {g.get('term','')}: {g.get('definition','')} | 约束: {', '.join(g.get('constraints', []) or [])}"
            )
    if recipe_hits:
        lines.append("[Recipes]")
        for r in recipe_hits:
            steps = " -> ".join((r.get("steps", []) or [])[:4])
            lines.append(
                f"- {r.get('task','')}: {r.get('description','')} | steps: {steps} | fix: {r.get('fix','')}"
            )
    if capability_hits:
        lines.append("[Capabilities]")
        for c in capability_hits:
            chain = " -> ".join((c.get("tool_chain", []) or [])[:6])
            gate = "; ".join((c.get("quality_gate", []) or [])[:2])
            lines.append(
                f"- {c.get('skill_id','')}: chain={chain} | gate={gate}"
            )
    block = "\n".join(lines).strip()
    if len(block) <= max_chars:
        return block
    return block[: max_chars - 24] + "\n...[RAG CONTEXT TRUNCATED]"


def auto_retrieve(
    normalized_instruction: str,
    extracted_terms: list[str],
    task_type: str,
    top_k_glossary: int = 8,
    top_k_recipe: int = 5,
    max_chars: int = MAX_RAG_CHARS,
) -> dict[str, Any]:
    glossary = GlossaryStore.create()
    recipes = RecipeStore.create()
    capabilities = SkillCapabilityStore.create() if SkillCapabilityStore else None

    terms = list(extracted_terms or [])
    if normalized_instruction:
        # basic backfill from normalized text tokens
        for t in normalized_instruction.split():
            t = t.strip(" ,;()[]")
            if len(t) >= 3 and t not in terms:
                terms.append(t)
            if len(terms) >= 20:
                break

    g_hits = glossary.retrieve(terms, top_k=top_k_glossary)
    r_hits = recipes.retrieve(task_type=task_type, extracted_terms=terms, top_k=top_k_recipe)
    c_hits = capabilities.retrieve(task_type=task_type, terms=terms, top_k=6) if capabilities else []
    context_text = _build_context_block(g_hits, r_hits, c_hits, max_chars=max_chars)
    return {
        "glossary_hits": g_hits,
        "recipe_hits": r_hits,
        "capability_hits": c_hits,
        "context_text": context_text,
        "meta": {
            "glossary_count": len(g_hits),
            "recipe_count": len(r_hits),
            "capability_count": len(c_hits),
            "max_chars": max_chars,
        },
    }

