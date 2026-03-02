"""
Meshy AI — isolated UI operators and pipeline logic.

This module handles ALL Meshy-related UI interaction:
  - Text-to-3D via chat input  (_send_meshy_pipeline)
  - Image-to-3D via file upload (AGENT_OT_MeshyImageTo3DUpload)

It depends ONLY on:
  - ui.state (_get_state, _add_message)
  - tool_definitions.execute_tool  (lazy import)
  - standard lib (re, json, os, base64, mimetypes)

Agent LLM is NEVER touched here — callbacks are injected from chat_ui.
"""

import re
import os
import json
import base64
import mimetypes

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from .state import _get_state, _add_message, is_processing, set_processing

# ---------- callback slots (injected by chat_ui at register time) ----------
_on_tool_call = None
_on_error = None
_on_permission_request = None


def init_callbacks(on_tool_call, on_error, on_permission_request):
    global _on_tool_call, _on_error, _on_permission_request
    _on_tool_call = on_tool_call
    _on_error = on_error
    _on_permission_request = on_permission_request


# ---------- helpers ----------

def _extract_first_url(text: str) -> str:
    m = re.search(r"https?://[^\s)>\]\"']+", text or "", flags=re.IGNORECASE)
    return m.group(0) if m else ""


def _parse_meshy_request(user_msg: str):
    msg = (user_msg or "").strip()
    lowered = msg.lower()
    if not msg:
        return None, None

    generation_markers = ("生成", "创建模型", "文生", "图生", "create model", "generate", "to 3d")
    image_markers = ("图生", "图片", "参考图", "image", "photo", "根据这张图")
    agent_edit_markers = ("材质", "节点", "shader", "场景", "scene", "mcp", "修改器", "驱动", "driver")

    # 图生优先：有图生意图但未给 URL，引导使用上传入口
    url = _extract_first_url(msg)
    if (any(k in lowered for k in image_markers)) and (not url):
        return None, '检测到图生3D意图，但未提供图片URL。请用"图生3D（导入图片）"按钮上传本地图片。'
    if url and any(k in lowered for k in image_markers):
        return ("meshy_image_to_3d", {"image_url": url}), None

    # Meshy 模式默认把自然语言当作文生3D请求，仅在明显是 Agent/MCP 编辑请求时拦截。
    if (not any(k in lowered for k in generation_markers)) and any(k in lowered for k in agent_edit_markers):
        return None, "当前是 Meshy 模式，仅支持模型生成请求（文生/图生）。该请求请切到 Agent 模式。"

    prompt = msg.replace(url, "").strip() if url else msg
    if not prompt:
        prompt = "a realistic 3d model"
    return ("meshy_text_to_3d", {"prompt": prompt, "refine": True}), None


# ---------- Meshy chat pipeline ----------

def _send_meshy_pipeline(user_msg: str) -> bool:
    from .. import tool_definitions

    state = _get_state()
    parsed, reject = _parse_meshy_request(user_msg)
    if parsed is None:
        set_processing(False, channel="meshy")
        state.last_exec_status = "error"
        _add_message("system", f"❌ Meshy 模式: {reject}", channel="meshy")
        return False

    tool_name, arguments = parsed
    set_processing(True, channel="meshy")
    state.last_exec_mode = "meshy"
    state.last_route_hint = "Meshy生成"
    if _on_tool_call:
        _on_tool_call(tool_name, arguments)
    result = tool_definitions.execute_tool(tool_name, arguments)

    if result.get("success") and result.get("result") == "NEEDS_PERMISSION_CONFIRMATION":
        if _on_permission_request:
            _on_permission_request(
                result.get("tool_name") or tool_name,
                result.get("arguments") or arguments,
                result.get("risk", "high"),
                result.get("reason", "需要确认"),
                "meshy",
            )
        return True

    if result.get("success"):
        msg = result.get("result")
        if not isinstance(msg, str):
            msg = json.dumps(msg, ensure_ascii=False)
        _add_message("assistant", msg, channel="meshy")
        state.last_exec_status = "ok"
    else:
        err = result.get("error", "Meshy 调用失败")
        _add_message("system", f"❌ Meshy 模式错误: {err}", channel="meshy")
        state.last_exec_status = "error"

    set_processing(False, channel="meshy")
    return bool(result.get("success"))


# ---------- Image upload operator ----------

class AGENT_OT_MeshyImageTo3DUpload(Operator):
    bl_idname = "agent.meshy_image_to_3d_upload"
    bl_label = "图生3D（导入图片）"
    bl_description = "选择本地图片并直接调用 Meshy 图生3D"

    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        state = _get_state()
        if is_processing(channel="meshy"):
            self.report({"WARNING"}, "Agent 正在处理中，请稍后")
            return {"CANCELLED"}

        if not self.filepath or not os.path.isfile(self.filepath):
            self.report({"ERROR"}, "请选择有效图片文件")
            return {"CANCELLED"}

        try:
            with open(self.filepath, "rb") as f:
                raw = f.read()
            if not raw:
                self.report({"ERROR"}, "图片文件为空")
                return {"CANCELLED"}

            mime, _ = mimetypes.guess_type(self.filepath)
            if not mime or not mime.startswith("image/"):
                ext = os.path.splitext(self.filepath)[1].lower()
                mime = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                    ".bmp": "image/bmp",
                }.get(ext, "image/png")

            b64 = base64.b64encode(raw).decode("ascii")
            data_uri = f"data:{mime};base64,{b64}"

            _add_message("user", f"🖼️ 图生3D上传图片: {os.path.basename(self.filepath)}", channel="meshy")
            set_processing(True, channel="meshy")
            state.last_exec_status = "processing"
            state.last_exec_mode = "meshy"
            state.continuation_notice_shown = False
            if _on_tool_call:
                _on_tool_call("meshy_image_to_3d", {"image_url": f"data-uri://local-upload ({len(raw)} bytes)"})

            from .. import tool_definitions
            result = tool_definitions.execute_tool(
                "meshy_image_to_3d",
                {"image_url": data_uri},
            )

            if result.get("success"):
                msg = result.get("result")
                if not isinstance(msg, str):
                    msg = json.dumps(msg, ensure_ascii=False)
                _add_message("assistant", msg, channel="meshy")
                state.last_exec_status = "ok"
                self.report({"INFO"}, "已创建 Meshy 图生3D 任务")
            else:
                err = result.get("error", "调用 Meshy 图生3D 失败")
                if _on_error:
                    _on_error(f"Meshy 图生3D失败: {err}")
                self.report({"ERROR"}, str(err)[:120])
        except Exception as e:
            if _on_error:
                _on_error(f"图生3D上传失败: {e}")
            self.report({"ERROR"}, f"上传失败: {e}")
            return {"CANCELLED"}
        finally:
            set_processing(False, channel="meshy")

        return {"FINISHED"}


MESHY_CLASSES = [AGENT_OT_MeshyImageTo3DUpload]
