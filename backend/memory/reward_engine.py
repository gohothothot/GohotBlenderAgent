"""
Reward Engine (Agent 2.0 / Step 4)

Rules:
- success: importance += 0.1
- failure: importance -= 0.05
- error corrected success: importance += 0.2
- importance > 0.9 => semantic L1 upgrade
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .store import MemoryStore


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


@dataclass
class RewardDelta:
    importance_delta: float = 0.0
    note: str = ""


class RewardEngine:
    def __init__(self, store: MemoryStore):
        self.store = store

    def score_outcome(
        self,
        success: bool,
        corrected_after_error: bool = False,
    ) -> RewardDelta:
        if corrected_after_error:
            return RewardDelta(importance_delta=0.2, note="error_corrected")
        if success:
            return RewardDelta(importance_delta=0.1, note="success")
        return RewardDelta(importance_delta=-0.05, note="failure")

    def apply_to_memory(
        self,
        table: str,
        memory_id: str,
        success: bool,
        corrected_after_error: bool = False,
    ) -> dict[str, Any]:
        row = self.store.get_by_id(table, memory_id)
        if not row:
            return {"ok": False, "error": f"memory not found: {table}/{memory_id}"}

        delta = self.score_outcome(success=success, corrected_after_error=corrected_after_error)
        old_imp = float(row.get("importance", 0.5))
        new_imp = _clamp(old_imp + delta.importance_delta)
        updated = self.store.update_fields(table, memory_id, {"importance": new_imp})

        result = {
            "ok": bool(updated),
            "table": table,
            "memory_id": memory_id,
            "old_importance": old_imp,
            "new_importance": new_imp,
            "delta": delta.importance_delta,
            "note": delta.note,
            "upgraded_to_l1": False,
        }

        # semantic L1 upgrade
        if table == "semantic_memory" and new_imp > 0.9:
            self.store.update_fields(table, memory_id, {"abstraction_level": 1})
            result["upgraded_to_l1"] = True
        return result

    def reinforce_procedural_by_signal(
        self,
        signal_tags: list[str],
        success: bool,
    ) -> dict[str, Any]:
        """
        根据规则反思信号更新 procedural 记忆 success_rate。
        Strategy: task_pattern 包含 tag 即算命中。
        """
        tags = [str(x).strip().lower() for x in (signal_tags or []) if str(x).strip()]
        if not tags:
            return {"ok": True, "updated": 0}

        rows = self.store.list_recent("procedural_memory", limit=500)
        updated = 0
        for r in rows:
            task_pattern = str(r.get("task_pattern", "")).lower()
            if not any(tag in task_pattern for tag in tags):
                continue
            sid = str(r.get("id"))
            old_sr = float(r.get("success_rate", 0.5))
            new_sr = _clamp(old_sr + (0.05 if success else -0.03))
            self.store.update_fields(
                "procedural_memory",
                sid,
                {"success_rate": new_sr, "usage_count": int(r.get("usage_count", 0)) + 1},
            )
            updated += 1
        return {"ok": True, "updated": updated, "tags": tags}

