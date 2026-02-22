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


def end_session(final_result: str = ""):
    global _current_session
    if _current_session is None:
        return

    _current_session["ended_at"] = datetime.now().isoformat()
    _current_session["final_result"] = final_result

    _ensure_log_dir()
    filename = f"session_{_current_session['session_id']}.json"
    filepath = os.path.join(_LOG_DIR, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(_current_session, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ActionLog] 保存日志失败: {e}")

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
