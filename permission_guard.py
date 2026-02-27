"""
Tool permission gate for Blender Agent.
"""

import hashlib
import json
import time


_ONE_TIME_APPROVALS = {}
_APPROVAL_TTL_SEC = 600

_DESTRUCTIVE_TOOLS = {
    "delete_object",
    "shader_clear_nodes",
    "shader_delete_material",
    "shader_delete_node",
    "scene_remove_modifier",
}

_FILE_WRITE_TOOLS = {
    "file_write",
}

_NETWORK_TOOLS = {
    "web_search",
    "web_fetch",
    "web_search_blender",
    "web_analyze_reference",
    "meshy_text_to_3d",
    "meshy_image_to_3d",
}

_CRITICAL_TOOLS = {
    "execute_python",
}


def _get_addon_prefs():
    try:
        import bpy
        addon = bpy.context.preferences.addons.get(__package__)
        if addon:
            return addon.preferences
    except Exception:
        pass
    return None


def _normalize_args(arguments: dict) -> dict:
    args = dict(arguments or {})
    args.pop("__permission_approved", None)
    return args


def _fingerprint(tool_name: str, arguments: dict) -> str:
    payload = {
        "tool": tool_name,
        "args": _normalize_args(arguments),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def approve_tool_once(tool_name: str, arguments: dict):
    key = _fingerprint(tool_name, arguments)
    _ONE_TIME_APPROVALS[key] = time.time() + _APPROVAL_TTL_SEC


def _consume_if_approved(tool_name: str, arguments: dict) -> bool:
    now = time.time()
    expired = [k for k, exp in _ONE_TIME_APPROVALS.items() if exp <= now]
    for k in expired:
        _ONE_TIME_APPROVALS.pop(k, None)

    key = _fingerprint(tool_name, arguments)
    exp = _ONE_TIME_APPROVALS.get(key)
    if exp and exp > now:
        _ONE_TIME_APPROVALS.pop(key, None)
        return True
    return False


def evaluate_tool_permission(tool_name: str, arguments: dict) -> dict:
    """
    Return:
      {
        "allowed": bool,
        "requires_confirmation": bool,
        "risk": "low|medium|high|critical",
        "reason": str
      }
    """
    if _consume_if_approved(tool_name, arguments):
        return {"allowed": True, "requires_confirmation": False, "risk": "low", "reason": "已通过一次性授权"}

    prefs = _get_addon_prefs()
    permission_level = getattr(prefs, "ai_permission_level", "high") if prefs else "high"
    confirm_high_risk = bool(getattr(prefs, "confirm_high_risk_tools", True)) if prefs else True
    allow_destructive = bool(getattr(prefs, "allow_destructive_tools", True)) if prefs else True
    allow_file_write = bool(getattr(prefs, "allow_file_write_tools", True)) if prefs else True
    allow_network = bool(getattr(prefs, "allow_network_tools", True)) if prefs else True

    risk = "low"
    if tool_name in _CRITICAL_TOOLS:
        risk = "critical"
    elif tool_name in _DESTRUCTIVE_TOOLS:
        risk = "high"
    elif tool_name in _FILE_WRITE_TOOLS or tool_name in _NETWORK_TOOLS:
        risk = "medium"

    if tool_name in _CRITICAL_TOOLS:
        return {"allowed": False, "requires_confirmation": False, "risk": risk, "reason": "execute_python 已全局禁用"}

    if (tool_name in _DESTRUCTIVE_TOOLS) and (not allow_destructive):
        return {"allowed": False, "requires_confirmation": False, "risk": risk, "reason": "当前设置禁止破坏性工具"}
    if (tool_name in _FILE_WRITE_TOOLS) and (not allow_file_write):
        return {"allowed": False, "requires_confirmation": False, "risk": risk, "reason": "当前设置禁止文件写入工具"}
    if (tool_name in _NETWORK_TOOLS) and (not allow_network):
        return {"allowed": False, "requires_confirmation": False, "risk": risk, "reason": "当前设置禁止外部网络/Meshy工具"}

    # 级别策略：默认高权限，但高风险可确认
    if permission_level == "high":
        need_confirm = confirm_high_risk and (risk in ("high", "critical"))
    elif permission_level == "balanced":
        need_confirm = risk in ("medium", "high", "critical")
    else:  # conservative
        if risk in ("high", "critical"):
            return {"allowed": False, "requires_confirmation": False, "risk": risk, "reason": "当前为保守模式，已拦截高风险工具"}
        need_confirm = risk == "medium"

    if need_confirm:
        return {
            "allowed": True,
            "requires_confirmation": True,
            "risk": risk,
            "reason": f"工具 {tool_name} 属于 {risk} 风险操作，需要用户确认后执行",
        }

    return {"allowed": True, "requires_confirmation": False, "risk": risk, "reason": "已放行"}
