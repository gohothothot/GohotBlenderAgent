"""
Capability/Doc index for RAG grounding.

目标：
- 在 Planner 前提供“可执行能力”检索层（skill -> tool chain）。
- 支持按 task_type + terms 粗排，返回可直接用于计划约束的能力片段。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any


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


def _default_capabilities() -> list[dict[str, Any]]:
    return [
        {
            "skill_id": "controller.copy_location_basic",
            "domain": "animation",
            "task_types": ["animation", "rigging", "layout"],
            "terms": ["controller", "empty", "copy location", "constraint", "跟随", "约束"],
            "tool_chain": [
                "controller_create_empty",
                "controller_add_copy_location",
                "get_object_info",
            ],
            "quality_gate": ["目标与被约束对象都存在", "influence 建议 <= 1.0"],
            "fail_patterns": ["物体不存在", "约束目标为空"],
        },
        {
            "skill_id": "controller.track_to_camera",
            "domain": "animation",
            "task_types": ["animation", "camera", "layout"],
            "terms": ["track to", "朝向", "看向", "相机跟随"],
            "tool_chain": [
                "controller_add_track_to",
                "get_object_info",
            ],
            "quality_gate": ["检查 track_axis/up_axis 配置", "避免目标与对象重合"],
            "fail_patterns": ["track_axis", "up_axis", "目标不存在"],
        },
        {
            "skill_id": "controller.copy_rotation_scale",
            "domain": "animation",
            "task_types": ["animation", "rigging"],
            "terms": ["copy rotation", "copy scale", "旋转约束", "缩放约束"],
            "tool_chain": [
                "controller_add_copy_rotation",
                "controller_add_copy_scale",
                "get_object_info",
            ],
            "quality_gate": ["影响值分阶段提升（0.3/0.6/1.0）"],
            "fail_patterns": ["owner_name", "target_name"],
        },
        {
            "skill_id": "gn.bootstrap",
            "domain": "modeling",
            "task_types": ["modeling", "geometry_nodes"],
            "terms": ["geometry nodes", "几何节点", "node group", "程序化建模"],
            "tool_chain": [
                "gn_create_modifier",
                "gn_get_summary",
            ],
            "quality_gate": ["必须存在 Geometry 输入输出", "先检查 node_count 再继续扩图"],
            "fail_patterns": ["未找到 Geometry Nodes 修改器"],
        },
        {
            "skill_id": "gn.chain_add_and_link",
            "domain": "modeling",
            "task_types": ["modeling", "geometry_nodes"],
            "terms": ["add node", "link nodes", "连接节点", "节点链路"],
            "tool_chain": [
                "gn_add_node",
                "gn_link_nodes",
                "gn_get_summary",
            ],
            "quality_gate": ["优先验证 socket 名称是否存在", "每次只连一条关键主链"],
            "fail_patterns": ["插槽不存在", "节点不存在"],
        },
        {
            "skill_id": "gn.param_expose_and_tune",
            "domain": "modeling",
            "task_types": ["modeling", "geometry_nodes"],
            "terms": ["group input", "暴露参数", "set input default", "参数化"],
            "tool_chain": [
                "gn_expose_group_input",
                "gn_set_input_default",
                "gn_get_summary",
            ],
            "quality_gate": ["参数命名语义化", "默认值在可控范围内"],
            "fail_patterns": ["输入不存在", "default_value"],
        },
        {
            "skill_id": "controller.child_of_refine",
            "domain": "animation",
            "task_types": ["animation", "rigging", "layout"],
            "terms": ["child of", "层级约束", "influence", "remove constraint"],
            "tool_chain": [
                "controller_add_child_of",
                "controller_set_constraint_influence",
                "controller_remove_constraint",
                "get_object_info",
            ],
            "quality_gate": ["先低 influence 验证后再提高", "失败时可移除约束快速回滚"],
            "fail_patterns": ["未找到约束", "owner_name", "target_name"],
        },
        {
            "skill_id": "object.base_ops",
            "domain": "modeling",
            "task_types": ["modeling", "layout"],
            "terms": ["rename object", "select active", "linked duplicate", "实例化"],
            "tool_chain": [
                "object_rename",
                "object_select_set_active",
                "object_duplicate_linked",
                "get_scene_info",
            ],
            "quality_gate": ["重命名后立即校验对象存在", "关联复制共享数据块需确认符合预期"],
            "fail_patterns": ["物体不存在", "new_name 不能为空"],
        },
        {
            "skill_id": "gn.maintenance",
            "domain": "modeling",
            "task_types": ["modeling", "geometry_nodes"],
            "terms": ["remove node", "layout nodes", "find node type", "维护"],
            "tool_chain": [
                "gn_find_node_by_type",
                "gn_remove_node",
                "gn_auto_layout_nodes",
                "gn_get_summary",
            ],
            "quality_gate": ["删除节点前先查找类型", "大改图后执行自动布局"],
            "fail_patterns": ["节点不存在", "未找到 Geometry Nodes 修改器"],
        },
        {
            "skill_id": "animation.timeline_control",
            "domain": "animation",
            "task_types": ["animation", "layout"],
            "terms": ["timeline", "frame range", "fps", "current frame", "时间轴"],
            "tool_chain": [
                "scene_set_frame_range",
                "scene_set_current_frame",
                "get_scene_info",
            ],
            "quality_gate": ["关键帧前统一 frame range/fps", "写关键帧前设置当前帧"],
            "fail_patterns": ["frame_end 不能小于 frame_start"],
        },
        {
            "skill_id": "modifier.apply_pipeline",
            "domain": "modeling",
            "task_types": ["modeling", "lookdev"],
            "terms": ["apply modifier", "bevel", "subsurf", "应用修改器"],
            "tool_chain": [
                "scene_add_modifier",
                "scene_set_modifier_param",
                "scene_apply_modifier",
                "get_object_info",
            ],
            "quality_gate": ["apply 前确认对象类型", "推荐先复制对象保留可回滚版本"],
            "fail_patterns": ["修改器不存在", "对象类型不支持应用修改器"],
        },
        {
            "skill_id": "file.save_export_bundle",
            "domain": "pipeline",
            "task_types": ["render", "export", "delivery"],
            "terms": ["save blend", "export fbx", "export gltf", "导出"],
            "tool_chain": [
                "scene_save_blend",
                "scene_export_fbx",
                "scene_export_gltf",
                "file_list",
            ],
            "quality_gate": ["导出前先保存源文件", "导出路径不存在时自动创建目录"],
            "fail_patterns": ["filepath 不能为空", "无效 export_format"],
        },
    ]


@dataclass
class SkillCapabilityStore:
    path: str
    capabilities: list[dict[str, Any]]

    @classmethod
    def create(cls, path: str | None = None) -> "SkillCapabilityStore":
        p = path or os.path.join(os.path.dirname(__file__), "seed_capabilities.json")
        if not os.path.exists(p):
            _save_json(p, {"capabilities": _default_capabilities()})
        obj = _load_json(p, {"capabilities": []})
        caps = obj.get("capabilities", [])
        if not isinstance(caps, list):
            caps = []
        return cls(path=p, capabilities=caps)

    def retrieve(self, task_type: str, terms: list[str], top_k: int = 6) -> list[dict[str, Any]]:
        tt = _norm(task_type)
        q_terms = [_norm(t) for t in (terms or []) if _norm(t)]
        scored: list[tuple[float, dict[str, Any]]] = []
        for cap in self.capabilities:
            score = 0.0
            for ctt in (cap.get("task_types") or []):
                cttn = _norm(str(ctt))
                if not tt or not cttn:
                    continue
                if tt == cttn:
                    score += 3.0
                elif tt in cttn or cttn in tt:
                    score += 1.2
            hay = " ".join(
                [
                    str(cap.get("skill_id", "")),
                    str(cap.get("domain", "")),
                    " ".join([str(x) for x in (cap.get("terms") or [])]),
                    " ".join([str(x) for x in (cap.get("tool_chain") or [])]),
                ]
            ).lower()
            for q in q_terms:
                if q and q in hay:
                    score += 1.0
            if score > 0:
                scored.append((score, cap))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[: max(1, int(top_k))]]


@dataclass
class BlenderDocIndex:
    """
    轻量文档索引：提取 bpy API / 节点名，供未来 ingest 用。
    """
    api_symbols: list[str]
    node_symbols: list[str]

    @classmethod
    def from_text(cls, text: str) -> "BlenderDocIndex":
        t = text or ""
        api_hits = re.findall(r"(bpy\.[A-Za-z0-9_\.]+)", t)
        node_hits = re.findall(r"(GeometryNode[A-Za-z0-9_]+|ShaderNode[A-Za-z0-9_]+|FunctionNode[A-Za-z0-9_]+)", t)
        return cls(api_symbols=sorted(set(api_hits)), node_symbols=sorted(set(node_hits)))

    @classmethod
    def from_file(cls, path: str) -> "BlenderDocIndex":
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return cls.from_text(f.read())
        except Exception:
            return cls(api_symbols=[], node_symbols=[])

