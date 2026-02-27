"""
Action Log - Agent 操作日志系统

记录每次 Agent 的工具调用、结果、决策过程到结构化 JSON 日志。
用户可以根据日志评估 Agent 的操作效果并指导后续调整。
"""

import json
import os
from datetime import datetime
from typing import Any, Optional

_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
_METRICS_FILE = os.path.join(_LOG_DIR, "metrics.jsonl")
_current_session = None


def _ensure_log_dir():
    os.makedirs(_LOG_DIR, exist_ok=True)


def start_session(user_message: str) -> str:
    global _current_session
    _ensure_log_dir()

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    _current_session = {
        "session_id": session_id,
        "started_at": datetime.now().isoformat(),
        "user_request": user_message,
        "actions": [],
        "final_result": None,
    }
    return session_id


def log_tool_call(tool_name: str, arguments: dict, result: dict):
    if _current_session is None:
        return
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "tool_call",
        "tool": tool_name,
        "arguments": _safe_serialize(arguments),
        "success": result.get("success", False),
        "result_summary": _summarize_result(result),
    }
    if not result.get("success"):
        entry["error"] = str(result.get("error", ""))[:1000]

    _current_session["actions"].append(entry)


def log_agent_message(role: str, content: str):
    if _current_session is None:
        return

    _current_session["actions"].append({
        "timestamp": datetime.now().isoformat(),
        "type": "message",
        "role": role,
        "content": content[:2000],
    })


def log_web_search(query: str, results_count: int):
    if _current_session is None:
        return

    _current_session["actions"].append({
        "timestamp": datetime.now().isoformat(),
        "type": "web_search",
        "query": query,
        "results_count": results_count,
    })


def log_kb_lookup(query: str, found: bool, source: str = ""):
    if _current_session is None:
        return

    _current_session["actions"].append({
        "timestamp": datetime.now().isoformat(),
        "type": "kb_lookup",
        "query": query,
        "found": found,
        "source": source,
    })


def log_error(error_type: str, error_message: str):
    """记录错误到当前 session 日志"""
    if _current_session is None:
        return

    _current_session["actions"].append({
        "timestamp": datetime.now().isoformat(),
        "type": "error",
        "error_type": error_type,
        "message": error_message[:2000],
    })


def log_metric(metric_name: str, payload: dict):
    """记录结构化指标，用于性能/质量分析"""
    if _current_session is None:
        return
    event = {
        "timestamp": datetime.now().isoformat(),
        "type": "metric",
        "metric_name": metric_name,
        "payload": _safe_serialize(payload or {}),
    }
    _current_session["actions"].append(event)
    _append_metrics_line({
        "kind": "metric_event",
        "session_id": _current_session.get("session_id"),
        "user_request": (_current_session.get("user_request", "") or "")[:120],
        **event,
    })


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def build_performance_summary(session: dict) -> dict:
    """从会话 actions 中聚合性能指标摘要"""
    actions = session.get("actions", []) if isinstance(session, dict) else []
    metrics = [a for a in actions if isinstance(a, dict) and a.get("type") == "metric"]

    prewarm = [m for m in metrics if m.get("metric_name") == "shader_prewarm"]
    attach = [m for m in metrics if m.get("metric_name") == "shader_context_attach"]
    plans = [m for m in metrics if m.get("metric_name") == "shader_read_plan"]
    search_results = [m for m in metrics if m.get("metric_name") == "shader_search_index_result"]

    prewarm_elapsed = []
    prewarm_success = 0
    for m in prewarm:
        p = m.get("payload", {}) or {}
        if p.get("success"):
            prewarm_success += 1
        if isinstance(p.get("elapsed_ms"), (int, float)):
            prewarm_elapsed.append(float(p.get("elapsed_ms")))

    attach_prewarm = 0
    attach_inline = 0
    for m in attach:
        p = m.get("payload", {}) or {}
        src = p.get("source")
        if src == "prewarm_cache":
            attach_prewarm += 1
        elif src == "inline_build":
            attach_inline += 1

    plan_reason_count = {}
    estimated_tokens = []
    for m in plans:
        p = m.get("payload", {}) or {}
        reason = p.get("reason", "unknown")
        plan_reason_count[reason] = plan_reason_count.get(reason, 0) + 1
        cost = p.get("cost", {}) or {}
        if isinstance(cost.get("estimated_output_tokens"), (int, float)):
            estimated_tokens.append(float(cost.get("estimated_output_tokens")))

    search_success = 0
    search_candidates = []
    for m in search_results:
        p = m.get("payload", {}) or {}
        if p.get("success"):
            search_success += 1
        if isinstance(p.get("candidate_count"), (int, float)):
            search_candidates.append(float(p.get("candidate_count")))

    attach_total = len(attach)
    prewarm_hit_rate = round(attach_prewarm / attach_total, 4) if attach_total else 0.0
    search_total = len(search_results)
    search_success_rate = round(search_success / search_total, 4) if search_total else 0.0

    return {
        "metric_events": len(metrics),
        "shader_prewarm": {
            "total": len(prewarm),
            "success": prewarm_success,
            "avg_elapsed_ms": _avg(prewarm_elapsed),
        },
        "shader_context_attach": {
            "total": attach_total,
            "prewarm_cache": attach_prewarm,
            "inline_build": attach_inline,
            "prewarm_hit_rate": prewarm_hit_rate,
        },
        "shader_read_plan": {
            "total": len(plans),
            "reason_count": plan_reason_count,
            "avg_estimated_output_tokens": _avg(estimated_tokens),
        },
        "shader_search_index_result": {
            "total": search_total,
            "success_rate": search_success_rate,
            "avg_candidate_count": _avg(search_candidates),
        },
    }


def format_performance_brief(summary: dict) -> str:
    if not summary:
        return "无性能摘要"
    prewarm = summary.get("shader_prewarm", {})
    attach = summary.get("shader_context_attach", {})
    search = summary.get("shader_search_index_result", {})
    plan = summary.get("shader_read_plan", {})
    return (
        f"metrics={summary.get('metric_events', 0)}; "
        f"prewarm={prewarm.get('success', 0)}/{prewarm.get('total', 0)} "
        f"(avg {prewarm.get('avg_elapsed_ms', 0)}ms); "
        f"hit_rate={round(attach.get('prewarm_hit_rate', 0) * 100, 1)}%; "
        f"search_ok={round(search.get('success_rate', 0) * 100, 1)}% "
        f"(avg candidates {search.get('avg_candidate_count', 0)}); "
        f"plan_avg_tokens={plan.get('avg_estimated_output_tokens', 0)}"
    )


def end_session(final_result: str = ""):
    global _current_session
    if _current_session is None:
        return

    _current_session["ended_at"] = datetime.now().isoformat()
    _current_session["final_result"] = final_result
    _current_session["performance_summary"] = build_performance_summary(_current_session)
    _current_session["performance_brief"] = format_performance_brief(
        _current_session["performance_summary"]
    )

    _ensure_log_dir()
    filename = f"session_{_current_session['session_id']}.json"
    filepath = os.path.join(_LOG_DIR, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(_current_session, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ActionLog] 保存日志失败: {e}")

    _append_metrics_line({
        "kind": "session_summary",
        "timestamp": datetime.now().isoformat(),
        "session_id": _current_session.get("session_id"),
        "user_request": (_current_session.get("user_request", "") or "")[:200],
        "final_result": (_current_session.get("final_result", "") or "")[:300],
        "performance_summary": _current_session.get("performance_summary", {}),
        "performance_brief": _current_session.get("performance_brief", ""),
    })

    _current_session = None
    return filepath


def get_recent_logs(count: int = 10) -> list:
    _ensure_log_dir()
    files = sorted(
        [f for f in os.listdir(_LOG_DIR) if f.startswith("session_") and f.endswith(".json")],
        reverse=True
    )[:count]

    logs = []
    for f in files:
        try:
            with open(os.path.join(_LOG_DIR, f), "r", encoding="utf-8") as fh:
                logs.append(json.load(fh))
        except Exception:
            pass
    return logs


def get_session_log(session_id: str) -> Optional[dict]:
    filepath = os.path.join(_LOG_DIR, f"session_{session_id}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def get_recent_metrics(count: int = 50) -> list:
    """读取最近的 metrics.jsonl 记录（最新优先）"""
    _ensure_log_dir()
    if not os.path.exists(_METRICS_FILE):
        return []
    try:
        with open(_METRICS_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        records = []
        for line in lines[-max(1, count):]:
            try:
                records.append(json.loads(line))
            except Exception:
                continue
        return list(reversed(records))
    except Exception:
        return []


def _safe_serialize(obj: Any) -> Any:
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def _summarize_result(result: dict) -> str:
    r = result.get("result", "")
    if isinstance(r, str):
        return r[:500]
    elif isinstance(r, dict):
        return json.dumps(r, ensure_ascii=False)[:500]
    elif isinstance(r, list):
        # 记录前几个元素的摘要，而不是只记录数量
        summary = json.dumps(r[:5], ensure_ascii=False)[:500]
        if len(r) > 5:
            summary += f" ...共{len(r)}项"
        return summary
    return str(r)[:500]


def _append_metrics_line(obj: dict):
    """写入 JSONL 指标流；失败不影响主流程"""
    try:
        _ensure_log_dir()
        with open(_METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(_safe_serialize(obj), ensure_ascii=False) + "\n")
    except Exception:
        pass
