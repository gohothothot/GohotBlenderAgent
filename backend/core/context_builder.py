"""
Context Builder (Agent 2.0 / Step 3)

Context order:
[1] System Prompt + core memory + rules + persona
[2] History messages (old images -> [Image Placeholder], strip <think>)
[3] RAG injection (<=1200 chars)
[4] Long-term memory activation
[5] Plan context
[6] Dynamic tail reminder
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ..utils.token_optimizer import (
    CompressionStrategy,
    TokenBudget,
    TokenOptimizer,
    strip_think_tags,
)


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _sanitize_message_for_history(msg: dict[str, Any], old_message: bool) -> dict[str, Any]:
    role = msg.get("role", "user")
    content = msg.get("content", "")
    if isinstance(content, str):
        txt = strip_think_tags(content)
        return {"role": role, "content": txt}

    if isinstance(content, list):
        if old_message:
            # Old image blocks are replaced with placeholders.
            parts = []
            for block in content:
                if isinstance(block, dict) and str(block.get("type", "")).lower().startswith("image"):
                    parts.append("[Image Placeholder]")
                elif isinstance(block, dict):
                    t = block.get("text", "")
                    if t:
                        parts.append(strip_think_tags(_safe_str(t)))
                else:
                    parts.append(strip_think_tags(_safe_str(block)))
            return {"role": role, "content": "\n".join(p for p in parts if p).strip()}
        return {"role": role, "content": _safe_str(content)}

    return {"role": role, "content": strip_think_tags(_safe_str(content))}


@dataclass
class ContextBuildInput:
    system_prompt: str
    history_messages: list[dict[str, Any]] = field(default_factory=list)
    rag_context: str = ""
    long_term_memories: list[dict[str, Any]] = field(default_factory=list)
    plan_context: dict[str, Any] | None = None
    normalized_instruction: str = ""
    scene_summary: str = ""
    token_warning: str = ""
    core_memories: list[str] = field(default_factory=list)
    user_rules: list[str] = field(default_factory=list)
    persona: str = ""
    dynamic_notes: list[str] = field(default_factory=list)


class ContextBuilder:
    def __init__(
        self,
        budget: TokenBudget | None = None,
        deep_sleep_callback: Callable[[dict[str, Any]], Any] | None = None,
    ):
        self.optimizer = TokenOptimizer(
            budget=budget or TokenBudget(),
            deep_sleep_callback=deep_sleep_callback,
        )

    def build(
        self,
        ctx: ContextBuildInput,
        strategy: str = CompressionStrategy.BALANCED,
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []

        # [1] System Prompt（稳定前缀）
        sys_parts = [ctx.system_prompt.strip()]
        if ctx.core_memories:
            sys_parts.append("[Core Memories]\n" + "\n".join(f"- {strip_think_tags(_safe_str(x))}" for x in ctx.core_memories if _safe_str(x).strip()))
        if ctx.user_rules:
            sys_parts.append("[User Rules]\n" + "\n".join(f"- {strip_think_tags(_safe_str(x))}" for x in ctx.user_rules if _safe_str(x).strip()))
        if ctx.persona.strip():
            sys_parts.append("[Persona]\n" + ctx.persona.strip())
        messages.append({"role": "system", "content": "\n\n".join(p for p in sys_parts if p)})

        # [2] 历史消息（旧图替换，剥离 think）
        history = ctx.history_messages or []
        old_cut = max(0, len(history) - self.optimizer.budget.keep_recent_messages)
        for idx, msg in enumerate(history):
            messages.append(_sanitize_message_for_history(msg, old_message=(idx < old_cut)))

        # [3] RAG 注入
        rag_text = (ctx.rag_context or "").strip()
        if rag_text:
            rag_text = rag_text[:1200]
            messages.append({"role": "system", "content": "[RAG Context]\n" + rag_text})

        # [4] 长期记忆激活
        if ctx.long_term_memories:
            lines = []
            for m in ctx.long_term_memories[:8]:
                table = _safe_str(m.get("table"))
                content = _safe_str(m.get("content"))
                score = _safe_str(m.get("score"))
                lines.append(f"- ({table}, score={score}) {content}")
            if lines:
                messages.append({"role": "system", "content": "[Activated Long-term Memories]\n" + "\n".join(lines)})

        # [5] Plan 上下文
        if ctx.plan_context:
            try:
                payload = json.dumps(ctx.plan_context, ensure_ascii=False)
            except Exception:
                payload = _safe_str(ctx.plan_context)
            messages.append({"role": "system", "content": "[Plan Context]\n" + payload[:3000]})

        # [6] 末尾动态提醒（动态内容放最后）
        tail_lines = []
        if ctx.normalized_instruction.strip():
            tail_lines.append(f"normalized_instruction: {ctx.normalized_instruction.strip()}")
        if ctx.scene_summary.strip():
            tail_lines.append(f"scene_summary: {ctx.scene_summary.strip()}")
        if ctx.token_warning.strip():
            tail_lines.append(f"token_warning: {ctx.token_warning.strip()}")
        for note in ctx.dynamic_notes[:6]:
            note = _safe_str(note).strip()
            if note:
                tail_lines.append(note)
        if tail_lines:
            messages.append({"role": "system", "content": "[Dynamic Tail Reminder]\n" + "\n".join(f"- {x}" for x in tail_lines)})

        optimized = self.optimizer.optimize_messages(
            messages=messages,
            strategy=strategy,
            deep_sleep_payload={
                "module": "ContextBuilder",
                "reason": "pre_compression",
                "history_len": len(history),
            },
        )
        return {
            "messages": optimized.get("messages", messages),
            "meta": optimized.get("meta", {}),
            "deep_sleep_triggered": bool(optimized.get("deep_sleep_triggered", False)),
        }

