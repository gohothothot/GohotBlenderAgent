"""
Runtime Core - shared runtime primitives for agent engines.

Unifies:
- Blender main-thread execution
- non-blocking UI callbacks
- structured action logging
- round-level history compaction
"""

import json
from typing import Any, Dict, List


class RuntimeCoreMixin:
    """Shared runtime helpers used by multiple agent engines."""

    def _runtime_execute_in_main_thread(self, func, *args) -> dict:
        try:
            import bpy
            import queue

            result_queue = queue.Queue()

            def do_execute():
                try:
                    result = func(*args)
                    result_queue.put(result)
                except Exception as e:
                    result_queue.put({"success": False, "result": None, "error": str(e)})
                return None

            bpy.app.timers.register(do_execute)
            try:
                return result_queue.get(timeout=30.0)
            except Exception:
                return {"success": False, "result": None, "error": "操作超时（30秒）"}
        except Exception:
            return func(*args)

    def _runtime_fire_callback(self, callback, *args):
        if not callback:
            return
        try:
            import bpy

            def do_callback():
                try:
                    callback(*args)
                except Exception:
                    pass
                return None

            bpy.app.timers.register(do_callback)
        except Exception:
            try:
                callback(*args)
            except Exception:
                pass

    def _runtime_log_action(self, action_type: str, *args):
        try:
            from .. import action_log
            if action_type == "start":
                action_log.start_session(args[0])
                action_log.log_agent_message("user", args[0])
            elif action_type == "message":
                action_log.log_agent_message("assistant", args[0])
            elif action_type == "tool":
                action_log.log_tool_call(args[0], args[1], args[2])
            elif action_type == "error":
                action_log.log_error("agent", args[0])
                action_log.end_session(f"错误: {args[0][:200]}")
            elif action_type == "end":
                action_log.end_session(args[0] if args else "")
            elif action_type == "metric":
                payload = args[0] if args else {}
                metric_name = payload.get("name", "unknown_metric")
                action_log.log_metric(metric_name, payload)
        except Exception:
            pass

    def _runtime_history_chars(self, messages: List[Dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total += len(json.dumps(block, ensure_ascii=False))
                    else:
                        total += len(str(block))
            elif content is not None:
                total += len(str(content))
        return total

    def _runtime_compact_history_if_needed(
        self,
        history: List[Dict[str, Any]],
        char_budget: int,
        keep_tail_rounds: int = 2,
    ) -> List[Dict[str, Any]]:
        if self._runtime_history_chars(history) <= char_budget:
            return history
        return self._runtime_compact_history(history, keep_tail_rounds=keep_tail_rounds)

    def _runtime_compact_history(
        self,
        history: List[Dict[str, Any]],
        keep_tail_rounds: int = 2,
    ) -> List[Dict[str, Any]]:
        rounds = self._split_rounds(history)
        if len(rounds) <= keep_tail_rounds:
            return history

        old_rounds = rounds[:-keep_tail_rounds]
        tail_rounds = rounds[-keep_tail_rounds:]

        summary_lines = ["[历史压缩摘要] 仅保留较早轮次的语义骨架："]
        for idx, r in enumerate(old_rounds, start=1):
            user_text = ""
            assistant_text = ""
            tool_events = 0
            for msg in r:
                role = msg.get("role")
                content = msg.get("content")
                if role == "user" and not user_text:
                    user_text = self._snippet(content, 140)
                elif role == "assistant" and not assistant_text:
                    assistant_text = self._snippet(content, 140)
                elif role in ("tool",):
                    tool_events += 1
                elif isinstance(content, list):
                    # anthropic tool_result blocks can be wrapped in user content arrays
                    for block in content:
                        if isinstance(block, dict) and block.get("type") in ("tool_use", "tool_result"):
                            tool_events += 1
            summary_lines.append(f"- Round {idx} user: {user_text or '(空)'}")
            if assistant_text:
                summary_lines.append(f"  assistant: {assistant_text}")
            if tool_events:
                summary_lines.append(f"  tools: {tool_events} events")

        compacted = [{"role": "system", "content": "\n".join(summary_lines)}]
        for r in tail_rounds:
            compacted.extend(r)
        return compacted

    def _split_rounds(self, history: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        rounds: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        for msg in history:
            if msg.get("role") == "user" and current:
                rounds.append(current)
                current = [msg]
            else:
                current.append(msg)
        if current:
            rounds.append(current)
        return rounds

    def _snippet(self, content: Any, limit: int) -> str:
        if isinstance(content, str):
            return content.replace("\n", " ")[:limit]
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    t = item.get("text")
                    if t:
                        parts.append(str(t))
                elif item is not None:
                    parts.append(str(item))
            return " ".join(parts)[:limit]
        if content is None:
            return ""
        return str(content)[:limit]
