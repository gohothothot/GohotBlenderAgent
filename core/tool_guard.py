"""
Tool guard middleware.

Centralizes permission gating so tool execution paths share one policy.
"""

from typing import Optional

try:
    from ..permission_guard import evaluate_tool_permission
except Exception:  # pragma: no cover - test fallback when loaded standalone
    from permission_guard import evaluate_tool_permission


def precheck_tool_execution(tool_name: str, arguments: dict) -> Optional[dict]:
    """
    Return:
      - None: continue execution
      - dict: short-circuit result (blocked / confirmation required)
    """
    permission = evaluate_tool_permission(tool_name, arguments or {})
    if not permission.get("allowed", True):
        return {
            "success": False,
            "result": None,
            "error": f"权限拦截: {permission.get('reason', '未授权')}",
        }
    if permission.get("requires_confirmation"):
        return {
            "success": True,
            "result": "NEEDS_PERMISSION_CONFIRMATION",
            "tool_name": tool_name,
            "arguments": arguments or {},
            "risk": permission.get("risk", "high"),
            "reason": permission.get("reason", "需要确认"),
        }
    return None
