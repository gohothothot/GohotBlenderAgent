"""
Lightweight graph indexer for shader/material introspection.

目标：
- 在不引入外部依赖的情况下，缓存节点索引
- 支持快速分页检索与关键词过滤
- 为后续向量检索接口预留结构
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from .vector_store import get_vector_store


@dataclass
class MaterialIndex:
    material_name: str
    updated_at: str
    total_nodes: int = 0
    total_links: int = 0
    node_type_top: list = field(default_factory=list)
    nodes: list = field(default_factory=list)  # [{"name","type","label"}...]


class GraphIndexer:
    def __init__(self):
        self._materials: dict[str, MaterialIndex] = {}

    def upsert_from_inspect(self, material_name: str, payload: dict):
        now = datetime.now(timezone.utc).isoformat()
        graph_summary = payload.get("graph_summary", {}) if isinstance(payload, dict) else {}
        nodes = payload.get("nodes", []) if isinstance(payload, dict) else []

        existing = self._materials.get(material_name)
        if existing:
            idx = existing
            idx.updated_at = now
        else:
            idx = MaterialIndex(material_name=material_name, updated_at=now)
            self._materials[material_name] = idx

        idx.total_nodes = int(graph_summary.get("total_nodes", idx.total_nodes or 0))
        idx.total_links = int(graph_summary.get("total_links", idx.total_links or 0))
        idx.node_type_top = list(graph_summary.get("node_type_top", idx.node_type_top or []))

        if nodes:
            # 仅保留索引字段，避免缓存膨胀
            merged = {n.get("name"): n for n in idx.nodes if isinstance(n, dict) and n.get("name")}
            for n in nodes:
                if not isinstance(n, dict):
                    continue
                name = n.get("name")
                if not name:
                    continue
                merged[name] = {
                    "name": name,
                    "type": n.get("type", ""),
                    "label": n.get("label", ""),
                }
            idx.nodes = list(merged.values())
        self._sync_material_vectors(idx)

    def upsert_from_summary(self, material_name: str, payload: dict):
        now = datetime.now(timezone.utc).isoformat()
        existing = self._materials.get(material_name)
        if existing:
            idx = existing
            idx.updated_at = now
        else:
            idx = MaterialIndex(material_name=material_name, updated_at=now)
            self._materials[material_name] = idx

        idx.total_nodes = int(payload.get("node_count", idx.total_nodes or 0))
        idx.total_links = int(payload.get("link_count", idx.total_links or 0))
        nt = payload.get("node_types_used", {})
        if isinstance(nt, dict):
            idx.node_type_top = [{"type": k, "count": v} for k, v in sorted(nt.items(), key=lambda x: x[1], reverse=True)[:12]]
        node_index = payload.get("node_index")
        if isinstance(node_index, list):
            idx.nodes = [
                {"name": n.get("name", ""), "type": n.get("type", ""), "label": n.get("label", "")}
                for n in node_index if isinstance(n, dict) and n.get("name")
            ]
        self._sync_material_vectors(idx)

    def query_nodes(self, material_name: str, keyword: str = "", node_type: str = "", limit: int = 20, offset: int = 0) -> dict:
        idx = self._materials.get(material_name)
        if not idx:
            return {"material_name": material_name, "total": 0, "items": [], "has_more": False, "updated_at": None}

        items = idx.nodes
        if keyword:
            kw = keyword.lower()
            items = [n for n in items if kw in n.get("name", "").lower() or kw in n.get("label", "").lower()]
        if node_type:
            tp = node_type.lower()
            items = [n for n in items if tp in str(n.get("type", "")).lower()]

        safe_limit = max(1, min(int(limit or 20), 200))
        safe_offset = max(0, int(offset or 0))
        page = items[safe_offset:safe_offset + safe_limit]
        return {
            "material_name": material_name,
            "total": len(items),
            "offset": safe_offset,
            "limit": safe_limit,
            "items": page,
            "has_more": safe_offset + safe_limit < len(items),
            "updated_at": idx.updated_at,
        }

    def get_summary(self, material_name: str) -> dict:
        idx = self._materials.get(material_name)
        if not idx:
            return {"material_name": material_name, "exists": False}
        return {
            "material_name": material_name,
            "exists": True,
            "total_nodes": idx.total_nodes,
            "total_links": idx.total_links,
            "indexed_nodes": len(idx.nodes),
            "node_type_top": idx.node_type_top,
            "updated_at": idx.updated_at,
        }

    def semantic_search(self, material_name: str, query: str, top_k: int = 10) -> dict:
        store = get_vector_store()
        items = store.search(
            query=query,
            top_k=top_k,
            metadata_filter={"material_name": material_name},
        )
        return {
            "material_name": material_name,
            "query": query,
            "count": len(items),
            "items": items,
        }

    def _sync_material_vectors(self, idx: MaterialIndex):
        store = get_vector_store()
        prefix = f"material:{idx.material_name}:"
        store.delete_prefix(prefix)

        summary_text = (
            f"material {idx.material_name} "
            f"nodes {idx.total_nodes} links {idx.total_links} "
            f"types {' '.join(str(x.get('type', '')) for x in idx.node_type_top)}"
        )
        store.upsert(
            doc_id=f"{prefix}summary",
            text=summary_text,
            metadata={"kind": "summary", "material_name": idx.material_name},
        )

        for node in idx.nodes:
            name = node.get("name", "")
            if not name:
                continue
            text = f"node {name} type {node.get('type', '')} label {node.get('label', '')} material {idx.material_name}"
            store.upsert(
                doc_id=f"{prefix}node:{name}",
                text=text,
                metadata={
                    "kind": "node",
                    "material_name": idx.material_name,
                    "node_name": name,
                    "node_type": node.get("type", ""),
                    "node_label": node.get("label", ""),
                },
            )
        store.save()


_INDEXER = GraphIndexer()


def get_graph_indexer() -> GraphIndexer:
    return _INDEXER
