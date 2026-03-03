"""
Reflection Module (Agent 2.0 / Step 4)

- Light Sleep: every N turns (async/threaded expected by caller)
- Deep Sleep: forced before compression
- Rule reflection: signal tags from tool-call chain
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any

from .store import MemoryStore, get_memory_store
from .reward_engine import RewardEngine


LIGHT_SLEEP_INTERVAL = int(os.getenv("LIGHT_SLEEP_INTERVAL", "5"))
MODEL_SUMMARIZER = os.getenv("MODEL_SUMMARIZER", "").strip()


def _safe_json_extract(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None
    l = raw.find("{")
    r = raw.rfind("}")
    if l < 0 or r <= l:
        return None
    try:
        obj = json.loads(raw[l : r + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _call_llm_summary(llm: Any, system_prompt: str, user_prompt: str) -> str:
    if llm is None:
        return ""
    if hasattr(llm, "chat"):
        chat_fn = getattr(llm, "chat")
        try:
            resp = chat_fn(
                messages=[{"role": "user", "content": user_prompt}],
                system=system_prompt,
                model=MODEL_SUMMARIZER or None,
                tools=None,
            )
        except TypeError:
            resp = chat_fn(messages=[{"role": "user", "content": user_prompt}], system=system_prompt)
        txt = getattr(resp, "text", None)
        return txt if isinstance(txt, str) else str(resp)
    return ""


def extract_signal_tags(tool_calls: list[dict[str, Any]]) -> list[str]:
    tags = set()
    retries = 0
    for c in tool_calls or []:
        name = str(c.get("tool") or c.get("name") or "").lower()
        result = c.get("result") or {}
        ok = bool(result.get("success", True))
        if ("modifier" in name) or ("bevel" in name) or ("subdivision" in name):
            tags.add("modifier_related")
        if ("material" in name) or ("shader" in name):
            tags.add("material_related")
        if ("render" in name) or ("cycles" in name) or ("eevee" in name):
            tags.add("render_related")
        if not ok:
            retries += 1
            tags.add("error_correction")
    if retries >= 2:
        tags.add("retry_heavy")
    return sorted(tags)


@dataclass
class ReflectionModule:
    store: MemoryStore
    reward: RewardEngine
    light_sleep_interval: int = LIGHT_SLEEP_INTERVAL
    _turn_counter: int = 0
    _task_counter: int = 0

    @classmethod
    def create(cls, store: MemoryStore | None = None) -> "ReflectionModule":
        s = store or get_memory_store()
        return cls(store=s, reward=RewardEngine(s))

    def on_turn_completed_async(
        self,
        session_id: str,
        recent_messages: list[dict[str, Any]],
        llm: Any = None,
    ):
        self._turn_counter += 1
        if self.light_sleep_interval <= 0:
            return
        if (self._turn_counter % self.light_sleep_interval) != 0:
            return

        # asynchronous light sleep
        t = threading.Thread(
            target=self.light_sleep,
            args=(session_id, recent_messages, llm),
            daemon=True,
        )
        t.start()

    def light_sleep(
        self,
        session_id: str,
        recent_messages: list[dict[str, Any]],
        llm: Any = None,
    ) -> dict[str, Any]:
        """
        summarize recent conversation and write episodic + semantic memories.
        output budget ~1500 tokens (prompt instruction level).
        """
        convo = self._flatten_messages(recent_messages, char_limit=8000)
        system = (
            "你是记忆整理模块。请从最近对话提取："
            "1) 可复用规则（semantic），2) 关键事件（episodic）。"
            "仅返回 JSON："
            '{"episodic":"...","semantic_rules":["..."],"category":"workflow|pitfall|knowledge|preference|general"}'
        )
        user = (
            "请在 1500 tokens 以内完成总结。\n"
            f"session_id={session_id}\n\n"
            f"recent_messages:\n{convo}"
        )
        raw = _call_llm_summary(llm, system, user) if llm else ""
        obj = _safe_json_extract(raw) or {}

        episodic = str(obj.get("episodic", "")).strip() or convo[:500]
        semantic_rules = obj.get("semantic_rules", [])
        if not isinstance(semantic_rules, list):
            semantic_rules = []
        category = str(obj.get("category", "general")).strip() or "general"

        epi_id = self.store.add_episodic(
            session_id=session_id,
            user_input="",
            normalized_input=episodic[:800],
            tool_calls=[],
            result=episodic[:1200],
            success=True,
            importance=0.6,
        )
        sem_ids = []
        for rule in semantic_rules[:8]:
            txt = str(rule).strip()
            if not txt:
                continue
            sid = self.store.add_semantic(
                content=txt,
                category=category,
                abstraction_level=2,
                importance=0.6,
            )
            sem_ids.append(sid)
        return {"ok": True, "episodic_id": epi_id, "semantic_ids": sem_ids}

    def deep_sleep(
        self,
        session_id: str,
        full_context_messages: list[dict[str, Any]],
        task_pattern: str = "",
        llm: Any = None,
    ) -> dict[str, Any]:
        """
        deep reflection before compression, target ~3000 token reasoning output.
        writes episodic + semantic + procedural.
        """
        full_text = self._flatten_messages(full_context_messages, char_limit=24000)
        system = (
            "你是深度反思模块。请从完整上下文提取："
            "1) 高价值事件总结；2) 可复用规则；3) 可执行策略模板。"
            "仅返回 JSON："
            '{"episodic":"...","semantic_rules":["..."],"procedural_strategy":"...","category":"workflow|pitfall|knowledge|general"}'
        )
        user = (
            "请在 3000 tokens 以内完成深度整理。\n"
            f"session_id={session_id}\n"
            f"task_pattern={task_pattern}\n\n"
            f"full_context:\n{full_text}"
        )
        raw = _call_llm_summary(llm, system, user) if llm else ""
        obj = _safe_json_extract(raw) or {}

        episodic = str(obj.get("episodic", "")).strip() or full_text[:1200]
        semantic_rules = obj.get("semantic_rules", [])
        if not isinstance(semantic_rules, list):
            semantic_rules = []
        procedural_strategy = str(obj.get("procedural_strategy", "")).strip() or "Prefer tool-first execution with validation checkpoints."
        category = str(obj.get("category", "general")).strip() or "general"

        epi_id = self.store.add_episodic(
            session_id=session_id,
            user_input="",
            normalized_input=episodic[:1000],
            tool_calls=[],
            result=episodic[:2000],
            success=True,
            importance=0.7,
        )
        sem_ids = []
        for rule in semantic_rules[:12]:
            txt = str(rule).strip()
            if not txt:
                continue
            sem_ids.append(
                self.store.add_semantic(
                    content=txt,
                    category=category,
                    abstraction_level=2,
                    importance=0.7,
                )
            )
        pro_id = self.store.add_procedural(
            task_pattern=task_pattern or "general_task",
            strategy=procedural_strategy,
            priority=0.7,
            success_rate=0.5,
            usage_count=0,
        )
        return {"ok": True, "episodic_id": epi_id, "semantic_ids": sem_ids, "procedural_id": pro_id}

    def reflect_task_outcome(
        self,
        session_id: str,
        user_input: str,
        normalized_input: str,
        tool_calls: list[dict[str, Any]],
        result_text: str,
        success: bool,
        corrected_after_error: bool = False,
    ) -> dict[str, Any]:
        """
        zero-cost reflection per task:
        - extract signal tags
        - store episodic memory
        - update reward/importance
        - update procedural success_rate by signal tags
        """
        tags = extract_signal_tags(tool_calls)
        epi_id = self.store.add_episodic(
            session_id=session_id,
            user_input=user_input,
            normalized_input=normalized_input,
            tool_calls=tool_calls,
            result=result_text,
            success=success,
            importance=0.55,
        )
        reward_info = self.reward.apply_to_memory(
            "episodic_memory",
            epi_id,
            success=success,
            corrected_after_error=corrected_after_error,
        )
        proc_info = self.reward.reinforce_procedural_by_signal(tags, success=success)
        return {"ok": True, "episodic_id": epi_id, "signal_tags": tags, "reward": reward_info, "procedural": proc_info}

    @staticmethod
    def _flatten_messages(messages: list[dict[str, Any]], char_limit: int = 12000) -> str:
        lines = []
        for m in messages or []:
            role = str(m.get("role", "user"))
            content = m.get("content", "")
            if isinstance(content, list):
                text = json.dumps(content, ensure_ascii=False)
            else:
                text = str(content)
            lines.append(f"[{role}] {text}")
            if sum(len(x) for x in lines) > char_limit:
                break
        out = "\n".join(lines)
        return out[:char_limit]

