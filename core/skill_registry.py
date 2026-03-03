"""
Skill registry and retrieval for tool-subset planning.

Phase 1 goal:
- Load declarative skills from `skills/*.json`
- Retrieve top-k relevant skills by query/intent/domain
- Build a compact tool subset for execution
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple


@dataclass
class Skill:
    id: str
    name: str
    domain: str
    intents: List[str]
    tags: List[str]
    description: str
    tools: List[str]
    quality_hints: List[str]
    verify_tools: List[str]


_SKILLS_CACHE: List[Skill] | None = None


def _skills_dir() -> str:
    root = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(root, "skills")


def _load_skills() -> List[Skill]:
    global _SKILLS_CACHE
    if _SKILLS_CACHE is not None:
        return _SKILLS_CACHE

    result: List[Skill] = []
    sdir = _skills_dir()
    if not os.path.isdir(sdir):
        _SKILLS_CACHE = result
        return result

    for fn in os.listdir(sdir):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(sdir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue

        items = payload if isinstance(payload, list) else payload.get("skills", [])
        if not isinstance(items, list):
            continue

        for row in items:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("id", "")).strip()
            name = str(row.get("name", "")).strip()
            tools = [str(x).strip() for x in (row.get("tools") or []) if str(x).strip()]
            if not sid or not name or not tools:
                continue
            result.append(
                Skill(
                    id=sid,
                    name=name,
                    domain=str(row.get("domain", "general")).strip() or "general",
                    intents=[str(x).strip() for x in (row.get("intents") or []) if str(x).strip()],
                    tags=[str(x).strip() for x in (row.get("tags") or []) if str(x).strip()],
                    description=str(row.get("description", "")).strip(),
                    tools=tools,
                    quality_hints=[str(x).strip() for x in (row.get("quality_hints") or []) if str(x).strip()],
                    verify_tools=[str(x).strip() for x in (row.get("verify_tools") or []) if str(x).strip()],
                )
            )

    _SKILLS_CACHE = result
    return result


def _score_skill(skill: Skill, query: str, intent: str, domain: str) -> int:
    q = (query or "").lower()
    score = 0
    if domain and skill.domain == domain:
        score += 5
    if intent and intent in skill.intents:
        score += 4

    name = skill.name.lower()
    desc = skill.description.lower()
    tags = " ".join(skill.tags).lower()
    tools = " ".join(skill.tools).lower()

    tokens = [t for t in q.replace("\n", " ").split(" ") if t]
    for t in tokens:
        if t in name:
            score += 4
        if t in tags:
            score += 3
        if t in desc:
            score += 2
        if t in tools:
            score += 2
    return score


def search_skills(query: str, intent: str = "general", domain: str = "general", top_k: int = 8) -> List[Skill]:
    skills = _load_skills()
    if not skills:
        return []
    scored: List[Tuple[int, Skill]] = []
    for s in skills:
        sc = _score_skill(s, query, intent, domain)
        if sc > 0:
            scored.append((sc, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[: max(1, int(top_k))]]


def select_tools_for_request(
    tools: List[dict],
    query: str,
    intent: str = "general",
    domain: str = "general",
    top_k: int = 8,
    max_tools: int = 28,
) -> Tuple[List[dict], List[str]]:
    """
    Return (selected_tools, matched_skill_ids).

    Fallback policy:
    - if no skills matched, return original tools
    - if selected subset too small, backfill from original order
    """
    if not tools:
        return tools, []

    matched = search_skills(query=query, intent=intent, domain=domain, top_k=top_k)
    if not matched:
        return tools, []

    wanted: Set[str] = set()
    matched_ids: List[str] = []
    for s in matched:
        matched_ids.append(s.id)
        wanted.update(s.tools)
        wanted.update(s.verify_tools)

    subset = [t for t in tools if isinstance(t, dict) and t.get("name") in wanted]
    if not subset:
        return tools, matched_ids

    # backfill to avoid over-pruning
    if len(subset) < 8:
        existing = {t.get("name") for t in subset if isinstance(t, dict)}
        for t in tools:
            if not isinstance(t, dict):
                continue
            n = t.get("name")
            if n not in existing:
                subset.append(t)
                existing.add(n)
            if len(subset) >= min(len(tools), max_tools):
                break

    if len(subset) > max_tools:
        subset = subset[:max_tools]
    return subset, matched_ids


def build_skill_guidance(
    query: str,
    intent: str = "general",
    domain: str = "general",
    top_k: int = 5,
) -> Tuple[str, List[str]]:
    """
    Build prompt guidance from matched skills.
    Returns (guidance_text, matched_skill_ids).
    """
    matched = search_skills(query=query, intent=intent, domain=domain, top_k=top_k)
    if not matched:
        return "", []

    matched_ids = [s.id for s in matched]
    hint_lines: List[str] = []
    verify_tools: Set[str] = set()
    for s in matched:
        for h in s.quality_hints[:3]:
            hint_lines.append(f"- {h}")
        verify_tools.update(s.verify_tools)

    parts: List[str] = []
    parts.append("[Skill检索命中]")
    parts.append("命中技能: " + ", ".join(matched_ids[:6]))
    if hint_lines:
        parts.append("质量提示:")
        parts.extend(hint_lines[:8])
    if verify_tools:
        parts.append("完成后必须至少调用一个验证工具: " + ", ".join(sorted(verify_tools)[:6]))

    return "\n".join(parts), matched_ids

