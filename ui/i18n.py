"""
Lightweight i18n for Blender Agent (zh/en).
"""

import bpy


_ZH = {
    "settings_lang": "界面语言",
    "lang_auto": "跟随用户输入",
    "lang_zh": "中文",
    "lang_en": "English",
    "sys_error_prefix": "❌ 错误: {}",
    "sys_retry_mode": "♻️ 当前模式未触发工具调用，自动切换到 {0} 模式重试一次。",
    "sys_retry_toolset": "♻️ 检测到模型工具集漂移，自动切换到 {0} 模式重试一次。",
    "sys_permission_required": "🔐 需要权限确认：{0}（风险: {1}）\n{2}\n请点击“允许一次”或“拒绝”。",
}

_EN = {
    "settings_lang": "UI Language",
    "lang_auto": "Follow user input",
    "lang_zh": "Chinese",
    "lang_en": "English",
    "sys_error_prefix": "❌ Error: {}",
    "sys_retry_mode": "♻️ No tool calls in current mode, auto-switching to {0} mode and retrying once.",
    "sys_retry_toolset": "♻️ Detected wrong toolset usage, auto-switching to {0} mode and retrying once.",
    "sys_permission_required": "🔐 Permission required: {0} (risk: {1})\n{2}\nClick Allow Once or Reject.",
}


def _get_lang() -> str:
    try:
        addon = bpy.context.preferences.addons.get(__package__.split(".")[0])
        if addon and hasattr(addon.preferences, "ui_language"):
            lang = getattr(addon.preferences, "ui_language", "auto")
            if lang in ("zh", "en"):
                return lang
    except Exception:
        pass
    return "zh"


def tr(key: str, *args) -> str:
    lang = _get_lang()
    table = _EN if lang == "en" else _ZH
    text = table.get(key, key)
    if args:
        try:
            text = text.format(*args)
        except Exception:
            pass
    return text


def get_reply_language_hint(user_message: str = "") -> str:
    try:
        addon = bpy.context.preferences.addons.get(__package__.split(".")[0])
        lang_pref = getattr(addon.preferences, "ui_language", "auto") if addon else "auto"
    except Exception:
        lang_pref = "auto"

    if lang_pref == "zh":
        return "\n[语言约束] 你必须使用简体中文回复。"
    if lang_pref == "en":
        return "\n[Language Rule] You must reply in English."

    # auto: follow user input
    text = (user_message or "").strip()
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in text)
    if has_cjk:
        return "\n[语言约束] 你必须使用简体中文回复。"
    return "\n[Language Rule] Reply in English unless user asks Chinese explicitly."
