"""
MemoryStore (Agent 2.0 / Step 1)

- SQLite + WAL
- episodic_memory / semantic_memory / procedural_memory
- basic CRUD
- embedding backend with fallback
- semantic search: search_similar(query, top_k=5)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable


DEFAULT_DB_PATH = os.getenv("MEMORY_DB_PATH", "cache/memory/agent_memory.db")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBED_DIM = 384


def _now_ts() -> float:
    return float(time.time())


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _to_blob(vec: list[float]) -> bytes:
    # JSON bytes is simple, portable, and sufficient for SQLite BLOB storage.
    return json.dumps(vec, ensure_ascii=False).encode("utf-8")


def _from_blob(blob: bytes | None) -> list[float]:
    if not blob:
        return []
    try:
        arr = json.loads(blob.decode("utf-8"))
        if isinstance(arr, list):
            return [float(x) for x in arr]
    except Exception:
        pass
    return []


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        av = float(a[i])
        bv = float(b[i])
        dot += av * bv
        na += av * av
        nb += bv * bv
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _tokenize_ngrams(text: str, n: int = 3) -> list[str]:
    lowered = (text or "").strip().lower()
    if not lowered:
        return []
    compact = "".join(ch for ch in lowered if not ch.isspace())
    if len(compact) < n:
        return [compact] if compact else []
    return [compact[i : i + n] for i in range(len(compact) - n + 1)]


@dataclass
class _EmbeddingBackend:
    dim: int = EMBED_DIM
    model_name: str = EMBEDDING_MODEL_NAME
    _model: Any = None
    _ready: bool = False
    _fallback_only: bool = False

    def __post_init__(self):
        self._init_model()

    def _init_model(self):
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self._ready = True
        except Exception:
            self._model = None
            self._ready = True
            self._fallback_only = True

    def encode(self, text: str) -> list[float]:
        txt = (text or "").strip()
        if not txt:
            return [0.0] * self.dim

        if self._model is not None:
            try:
                vec = self._model.encode(txt)
                out = [float(x) for x in list(vec)]
                if len(out) < self.dim:
                    out.extend([0.0] * (self.dim - len(out)))
                return out[: self.dim]
            except Exception:
                pass

        # Fallback: n-gram hashing pseudo-vector
        v = [0.0] * self.dim
        grams = _tokenize_ngrams(txt, n=3)
        if not grams:
            return v
        for g in grams:
            h = hashlib.sha256(g.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if (h[4] & 1) else -1.0
            v[idx] += sign
        norm = math.sqrt(sum(x * x for x in v))
        if norm > 1e-12:
            v = [x / norm for x in v]
        return v


class MemoryStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._embedder = _EmbeddingBackend()
        self._ensure_db()

    # ---------- init ----------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodic_memory (
                  id TEXT PRIMARY KEY,
                  session_id TEXT,
                  timestamp REAL,
                  user_input TEXT,
                  normalized_input TEXT,
                  tool_calls TEXT,
                  result TEXT,
                  success INTEGER,
                  importance REAL DEFAULT 0.5,
                  embedding BLOB
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_memory (
                  id TEXT PRIMARY KEY,
                  content TEXT,
                  category TEXT,
                  abstraction_level INTEGER DEFAULT 2,
                  importance REAL DEFAULT 0.5,
                  access_count INTEGER DEFAULT 0,
                  embedding BLOB
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS procedural_memory (
                  id TEXT PRIMARY KEY,
                  task_pattern TEXT,
                  strategy TEXT,
                  priority REAL,
                  success_rate REAL DEFAULT 0.5,
                  usage_count INTEGER DEFAULT 0,
                  embedding BLOB
                );
                """
            )
            conn.commit()

    # ---------- CREATE ----------

    def add_episodic(
        self,
        session_id: str,
        user_input: str,
        normalized_input: str,
        tool_calls: list[dict] | dict | None,
        result: str,
        success: bool,
        importance: float = 0.5,
        memory_id: str | None = None,
    ) -> str:
        mid = memory_id or _new_id("epi")
        text_for_embed = f"{user_input}\n{normalized_input}\n{result}"
        emb = _to_blob(self._embedder.encode(text_for_embed))
        payload = json.dumps(tool_calls or [], ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO episodic_memory
                (id, session_id, timestamp, user_input, normalized_input, tool_calls, result, success, importance, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    session_id,
                    _now_ts(),
                    user_input,
                    normalized_input,
                    payload,
                    result,
                    1 if success else 0,
                    float(importance),
                    emb,
                ),
            )
            conn.commit()
        return mid

    def add_semantic(
        self,
        content: str,
        category: str,
        abstraction_level: int = 2,
        importance: float = 0.5,
        access_count: int = 0,
        memory_id: str | None = None,
    ) -> str:
        mid = memory_id or _new_id("sem")
        emb = _to_blob(self._embedder.encode(content))
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_memory
                (id, content, category, abstraction_level, importance, access_count, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    content,
                    category,
                    int(abstraction_level),
                    float(importance),
                    int(access_count),
                    emb,
                ),
            )
            conn.commit()
        return mid

    def add_procedural(
        self,
        task_pattern: str,
        strategy: str,
        priority: float = 0.5,
        success_rate: float = 0.5,
        usage_count: int = 0,
        memory_id: str | None = None,
    ) -> str:
        mid = memory_id or _new_id("pro")
        emb = _to_blob(self._embedder.encode(f"{task_pattern}\n{strategy}"))
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO procedural_memory
                (id, task_pattern, strategy, priority, success_rate, usage_count, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    task_pattern,
                    strategy,
                    float(priority),
                    float(success_rate),
                    int(usage_count),
                    emb,
                ),
            )
            conn.commit()
        return mid

    # ---------- READ ----------

    def get_by_id(self, table: str, memory_id: str) -> dict[str, Any] | None:
        self._assert_table(table)
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (memory_id,)).fetchone()
        return dict(row) if row else None

    def list_recent(self, table: str, limit: int = 20) -> list[dict[str, Any]]:
        self._assert_table(table)
        safe_limit = max(1, min(int(limit), 200))
        order_col = "timestamp" if table == "episodic_memory" else "rowid"
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY {order_col} DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- UPDATE ----------

    def update_fields(self, table: str, memory_id: str, fields: dict[str, Any]) -> bool:
        self._assert_table(table)
        if not fields:
            return False
        cols = []
        vals: list[Any] = []
        for k, v in fields.items():
            cols.append(f"{k} = ?")
            vals.append(v)
        vals.append(memory_id)
        sql = f"UPDATE {table} SET {', '.join(cols)} WHERE id = ?"
        with self._lock, self._connect() as conn:
            cur = conn.execute(sql, tuple(vals))
            conn.commit()
            return cur.rowcount > 0

    def bump_access_count(self, table: str, memory_id: str, delta: int = 1) -> bool:
        self._assert_table(table)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                f"UPDATE {table} SET access_count = COALESCE(access_count, 0) + ? WHERE id = ?",
                (int(delta), memory_id),
            )
            conn.commit()
            return cur.rowcount > 0

    # ---------- DELETE ----------

    def delete(self, table: str, memory_id: str) -> bool:
        self._assert_table(table)
        with self._lock, self._connect() as conn:
            cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    # ---------- SEARCH ----------

    def search_similar(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        qv = self._embedder.encode(q)
        scored: list[dict[str, Any]] = []

        scored.extend(self._scan_table_for_similarity("episodic_memory", qv))
        scored.extend(self._scan_table_for_similarity("semantic_memory", qv))
        scored.extend(self._scan_table_for_similarity("procedural_memory", qv))

        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[: max(1, int(top_k))]
        return top

    def _scan_table_for_similarity(self, table: str, qv: list[float]) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()

        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            v = _from_blob(d.get("embedding"))
            score = _cosine(qv, v)
            if score <= 0.0:
                continue
            content = self._preview_for_table(table, d)
            out.append(
                {
                    "table": table,
                    "id": d.get("id"),
                    "score": round(float(score), 6),
                    "content": content,
                    "raw": d,
                }
            )
        return out

    @staticmethod
    def _preview_for_table(table: str, row: dict[str, Any]) -> str:
        if table == "episodic_memory":
            return (row.get("normalized_input") or row.get("user_input") or "")[:240]
        if table == "semantic_memory":
            return (row.get("content") or "")[:240]
        if table == "procedural_memory":
            task = row.get("task_pattern") or ""
            strategy = row.get("strategy") or ""
            return f"{task} | {strategy}"[:240]
        return ""

    @staticmethod
    def _assert_table(table: str):
        allowed = {"episodic_memory", "semantic_memory", "procedural_memory"}
        if table not in allowed:
            raise ValueError(f"unsupported table: {table}")


_GLOBAL_MEMORY_STORE: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _GLOBAL_MEMORY_STORE
    if _GLOBAL_MEMORY_STORE is None:
        _GLOBAL_MEMORY_STORE = MemoryStore()
    return _GLOBAL_MEMORY_STORE

