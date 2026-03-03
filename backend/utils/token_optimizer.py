"""
Token Optimizer (Agent 2.0 / Step 3)

- TokenBudget thresholds
- Cursor-style round compaction
- Compression strategies: AGGRESSIVE / BALANCED / CONSERVATIVE
- Force Deep Sleep callback before compression
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class TokenBudget:
    max_tokens: int = 128000
    warning_threshold: float = 0.7
    compression_threshold: float = 0.8
    emergency_threshold: float = 0.9
    keep_recent_messages: int = 4


class CompressionStrategy:
    AGGRESSIVE = "AGGRESSIVE"
    BALANCED = "BALANCED"
    CONSERVATIVE = "CONSERVATIVE"


def strip_think_tags(text: str) -> str:
    raw = text or ""
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE)
    return raw.strip()


def _estimate_chars(messages: list[dict[str, Any]]) -> int:
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


def _split_rounds(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    rounds: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "user" and current:
            rounds.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        rounds.append(current)
    return rounds


def _truncate_middle(text: str, head: int, tail: int) -> str:
    raw = text or ""
    if len(raw) <= (head + tail + 12):
        return raw
    return f"{raw[:head]}\n...[TRUNCATED]...\n{raw[-tail:]}"


def _compress_tool_like_content(content: str, strategy: str) -> str:
    if strategy == CompressionStrategy.AGGRESSIVE:
        return _truncate_middle(content, head=320, tail=180)
    if strategy == CompressionStrategy.CONSERVATIVE:
        return _truncate_middle(content, head=1200, tail=700)
    return _truncate_middle(content, head=700, tail=400)


def _looks_tool_result(msg: dict[str, Any]) -> bool:
    role = str(msg.get("role", "")).lower()
    if role in ("tool",):
        return True
    content = msg.get("content")
    if isinstance(content, str) and ("tool" in content.lower() and "result" in content.lower()):
        return True
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("tool_use", "tool_result"):
                return True
    return False


def _build_old_rounds_summary(old_rounds: list[list[dict[str, Any]]], strategy: str) -> str:
    lines = ["[历史轮次压缩摘要]"]
    keep_assistant = strategy == CompressionStrategy.CONSERVATIVE
    for i, rnd in enumerate(old_rounds, start=1):
        user_text = ""
        assistant_text = ""
        tool_count = 0
        for msg in rnd:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user" and not user_text:
                user_text = strip_think_tags(str(content))[:200]
            elif role == "assistant" and keep_assistant and not assistant_text:
                assistant_text = strip_think_tags(str(content))[:160]
            if _looks_tool_result(msg):
                tool_count += 1
        lines.append(f"- Round {i}: user={user_text or '(empty)'}; tools={tool_count}")
        if assistant_text:
            lines.append(f"  assistant={assistant_text}")
    return "\n".join(lines)


class TokenOptimizer:
    def __init__(
        self,
        budget: TokenBudget | None = None,
        deep_sleep_callback: Callable[[dict[str, Any]], Any] | None = None,
    ):
        self.budget = budget or TokenBudget()
        self.deep_sleep_callback = deep_sleep_callback

    def optimize_messages(
        self,
        messages: list[dict[str, Any]],
        strategy: str = CompressionStrategy.BALANCED,
        deep_sleep_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(messages, list):
            return {
                "messages": [],
                "meta": {"error": "messages must be list"},
                "deep_sleep_triggered": False,
            }

        chars = _estimate_chars(messages)
        max_chars = max(1000, int(self.budget.max_tokens * 4))
        usage = chars / max_chars
        meta = {
            "chars_before": chars,
            "max_chars": max_chars,
            "usage_ratio": round(usage, 4),
            "strategy": strategy,
            "compressed": False,
        }

        if usage < self.budget.compression_threshold:
            meta["warning"] = usage >= self.budget.warning_threshold
            return {"messages": messages, "meta": meta, "deep_sleep_triggered": False}

        # Compression required -> must trigger Deep Sleep first.
        deep_sleep_triggered = False
        if self.deep_sleep_callback:
            try:
                payload = deep_sleep_payload or {}
                payload.setdefault("reason", "pre_compression")
                payload.setdefault("usage_ratio", usage)
                self.deep_sleep_callback(payload)
                deep_sleep_triggered = True
            except Exception:
                deep_sleep_triggered = False

        rounds = _split_rounds(messages)
        if len(rounds) <= 1:
            out = messages
        else:
            keep_tail = max(1, int(self.budget.keep_recent_messages))
            old_rounds = rounds[:-keep_tail] if len(rounds) > keep_tail else []
            tail_rounds = rounds[-keep_tail:] if len(rounds) > keep_tail else rounds

            compacted_old: list[dict[str, Any]] = []
            if old_rounds:
                summary = _build_old_rounds_summary(old_rounds, strategy=strategy)
                compacted_old.append({"role": "system", "content": summary})

                # Cursor风格：旧轮次中 tool 结果保留首尾截断
                for rnd in old_rounds:
                    for msg in rnd:
                        role = msg.get("role")
                        if role == "user":
                            compacted_old.append({"role": "user", "content": strip_think_tags(str(msg.get("content", "")))[:220]})
                        elif role == "assistant" and strategy == CompressionStrategy.CONSERVATIVE:
                            compacted_old.append({"role": "assistant", "content": strip_think_tags(str(msg.get("content", "")))[:180]})
                        elif _looks_tool_result(msg):
                            content = str(msg.get("content", ""))
                            compacted_old.append(
                                {
                                    "role": "tool",
                                    "content": _compress_tool_like_content(content, strategy=strategy),
                                }
                            )

            out: list[dict[str, Any]] = []
            out.extend(compacted_old)
            for rnd in tail_rounds:
                out.extend(rnd)

        # Emergency hard trim to target <= 70%
        target_chars = int(max_chars * 0.7)
        out_chars = _estimate_chars(out)
        if out_chars > target_chars:
            # secondary pass: keep only summary + last N messages
            n = max(8, self.budget.keep_recent_messages * 2)
            summary_msg = None
            if out and out[0].get("role") == "system" and "压缩摘要" in str(out[0].get("content", "")):
                summary_msg = out[0]
            tail = out[-n:]
            out = ([summary_msg] if summary_msg else []) + tail
            out_chars = _estimate_chars(out)

        meta.update(
            {
                "compressed": True,
                "chars_after": out_chars,
                "target_chars": target_chars,
                "warning": (out_chars / max_chars) >= self.budget.warning_threshold,
                "emergency": (out_chars / max_chars) >= self.budget.emergency_threshold,
            }
        )
        return {"messages": out, "meta": meta, "deep_sleep_triggered": deep_sleep_triggered}

