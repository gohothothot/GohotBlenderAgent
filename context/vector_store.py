"""
Lightweight local vector store (no external dependencies).

用途：
- 本地持久化文本向量索引
- 提供基础语义检索能力（基于 token 权重 + 余弦相似度）
"""

import json
import math
import os
import re
from collections import Counter


def _tokenize(text: str) -> list:
    if not text:
        return []
    # 英文/数字词 + 常见 CJK 连续块
    tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text.lower())
    result = []
    for tok in tokens:
        if len(tok) <= 1:
            continue
        # 对中文长词做 2-gram，提升召回
        if re.match(r"^[\u4e00-\u9fff]+$", tok) and len(tok) > 2:
            result.extend(tok[i:i + 2] for i in range(len(tok) - 1))
        result.append(tok)
    return result


def _to_unit(vec: dict) -> dict:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm <= 1e-12:
        return vec
    return {k: v / norm for k, v in vec.items()}


def _dot(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class SimpleVectorStore:
    def __init__(self, storage_path: str = None):
        if storage_path:
            self._path = storage_path
        else:
            root = os.path.dirname(os.path.dirname(__file__))
            self._path = os.path.join(root, "logs", "vector_store.json")
        self._docs = {}       # doc_id -> {text, metadata}
        self._vectors = {}    # doc_id -> sparse vector
        self._df = Counter()  # term -> doc frequency
        self._dirty = False
        self._load()

    def upsert(self, doc_id: str, text: str, metadata: dict = None):
        if not doc_id:
            return
        metadata = metadata or {}
        old_vec = self._vectors.get(doc_id)
        if old_vec:
            for term in old_vec.keys():
                self._df[term] -= 1
                if self._df[term] <= 0:
                    self._df.pop(term, None)

        self._docs[doc_id] = {"text": text or "", "metadata": metadata}
        tf = Counter(_tokenize(text or ""))
        vec = {k: float(v) for k, v in tf.items()}
        self._vectors[doc_id] = vec
        for term in vec.keys():
            self._df[term] += 1
        self._dirty = True

    def delete_prefix(self, prefix: str):
        to_delete = [doc_id for doc_id in self._docs.keys() if doc_id.startswith(prefix)]
        for doc_id in to_delete:
            vec = self._vectors.pop(doc_id, {})
            for term in vec.keys():
                self._df[term] -= 1
                if self._df[term] <= 0:
                    self._df.pop(term, None)
            self._docs.pop(doc_id, None)
            self._dirty = True

    def search(self, query: str, top_k: int = 10, metadata_filter: dict = None) -> list:
        if not query.strip():
            return []
        if not self._docs:
            return []

        tf_q = Counter(_tokenize(query))
        if not tf_q:
            return []

        n_docs = max(len(self._docs), 1)
        q_vec = {}
        for term, tf in tf_q.items():
            df = self._df.get(term, 0)
            idf = math.log((n_docs + 1) / (df + 1)) + 1.0
            q_vec[term] = float(tf) * idf
        q_vec = _to_unit(q_vec)

        scored = []
        top_k = max(1, min(int(top_k or 10), 50))
        for doc_id, vec_tf in self._vectors.items():
            doc = self._docs.get(doc_id, {})
            metadata = doc.get("metadata", {})
            if metadata_filter:
                mismatch = False
                for k, v in metadata_filter.items():
                    if metadata.get(k) != v:
                        mismatch = True
                        break
                if mismatch:
                    continue

            vec = {}
            for term, tf in vec_tf.items():
                df = self._df.get(term, 0)
                idf = math.log((n_docs + 1) / (df + 1)) + 1.0
                vec[term] = tf * idf
            vec = _to_unit(vec)
            score = _dot(q_vec, vec)
            if score <= 0:
                continue

            scored.append({
                "doc_id": doc_id,
                "score": round(score, 6),
                "text": doc.get("text", ""),
                "metadata": metadata,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def save(self):
        if not self._dirty:
            return
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        payload = {
            "docs": self._docs,
            "vectors": self._vectors,
            "df": dict(self._df),
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        self._dirty = False

    def _load(self):
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            self._docs = payload.get("docs", {})
            self._vectors = payload.get("vectors", {})
            self._df = Counter(payload.get("df", {}))
            self._dirty = False
        except Exception:
            self._docs = {}
            self._vectors = {}
            self._df = Counter()
            self._dirty = False


_VECTOR_STORE = SimpleVectorStore()


def get_vector_store() -> SimpleVectorStore:
    return _VECTOR_STORE
