"""
Plan manager for Blender Agent.

Stores one active plan per lightweight session id.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, Optional


class PlanManager:
    def __init__(self):
        root = os.path.dirname(os.path.dirname(__file__))
        self._plan_dir = os.path.join(root, "cache", "plans")
        os.makedirs(self._plan_dir, exist_ok=True)

    def _plan_path(self, session_id: str) -> str:
        return os.path.join(self._plan_dir, f"plan_{session_id}.json")

    def create_plan(self, session_id: str, plan_data: dict) -> dict:
        steps = []
        for i, s in enumerate(plan_data.get("steps", []), start=1):
            steps.append({
                "id": s.get("id", f"step-{i}"),
                "title": s.get("title", ""),
                "description": s.get("description", ""),
                "tools": s.get("tools", []),
                "depends_on": s.get("depends_on", []),
                "status": "pending",
                "result_summary": None,
            })
        plan = {
            "plan_id": str(uuid.uuid4())[:8],
            "session_id": session_id,
            "title": plan_data.get("title", "Untitled Plan"),
            "overview": plan_data.get("overview", ""),
            "status": "draft",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "steps": steps,
            "architecture": plan_data.get("architecture", {}),
        }
        self._save(session_id, plan)
        return plan

    def update_step(self, session_id: str, step_id: str, status: str, result_summary: str = "") -> Optional[dict]:
        plan = self.load_plan(session_id)
        if not plan:
            return None
        for s in plan.get("steps", []):
            if s.get("id") == step_id:
                s["status"] = status
                if result_summary:
                    s["result_summary"] = result_summary
                break
        if all(s.get("status") in ("done", "error") for s in plan.get("steps", [])):
            plan["status"] = "completed"
        elif any(s.get("status") == "running" for s in plan.get("steps", [])):
            plan["status"] = "executing"
        self._save(session_id, plan)
        return plan

    def load_plan(self, session_id: str) -> Optional[dict]:
        path = self._plan_path(session_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save(self, session_id: str, plan: dict):
        path = self._plan_path(session_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)


_instance = None


def get_plan_manager() -> PlanManager:
    global _instance
    if _instance is None:
        _instance = PlanManager()
    return _instance
