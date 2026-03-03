"""
Blender Agent - AI 驱动的 Blender 助手

功能：
1. Agent 模式：在 Blender 内直接与 AI 对话，AI 可以操作场景
2. MCP 模式：作为 MCP Server 供外部 AI 客户端调用（保留原功能）

安装：
1. 将整个文件夹复制到 Blender 的 addons 目录
2. 在 Blender 中启用插件
3. 修改 config.py 中的 API 配置
"""

bl_info = {
    "name": "Gohot Blender Agent",
    "author": "Gohot",
    "version": (2, 1),
    "blender": (5, 0, 0),
    "description": "AI 驱动的 Blender 助手 - 支持对话式操作和 Meshy AI 3D生成",
    "category": "Development",
}

import bpy
import threading
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


MCP_WHITELIST_TOOLS = {
    "scene.get_summary",
    "object.create_cube",
    "object.create_plane",
    "object.create_uv_sphere",
    "object.set_transform",
    "object.add_modifier_bevel",
    "object.add_subdivision_modifier",
    "material.create_principled",
    "material.set_base_color",
    "render.set_engine_cycles",
    "render.set_resolution",
    "render.render_still",
}


class MCPBridgeServer:
    def __init__(self, host="127.0.0.1", port=9876):
        self.host = host
        self.port = port
        self.httpd = None
        self.running = False
        self.thread = None

    def start(self):
        parent = self

        class _Handler(BaseHTTPRequestHandler):
            def _reply(self, code: int, payload: dict):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                if self.path == "/health":
                    self._reply(200, {"ok": True, "data": {"status": "running"}})
                    return
                self._reply(404, {"ok": False, "error": f"unknown path: {self.path}"})

            def do_POST(self):  # noqa: N802
                if self.path != "/tool":
                    self._reply(404, {"ok": False, "error": f"unknown path: {self.path}"})
                    return
                try:
                    content_len = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(content_len) if content_len > 0 else b"{}"
                    req = json.loads(raw.decode("utf-8"))
                    result = parent._execute_in_main_thread(req)
                    code = 200 if result.get("ok", result.get("success")) else 400
                    self._reply(code, result)
                except Exception as e:
                    self._reply(500, {"ok": False, "error": str(e), "logs": ["server_exception"]})

            def log_message(self, format, *args):
                return

        self.httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self.running = True

        self.thread = threading.Thread(target=self._serve_forever)
        self.thread.daemon = True
        self.thread.start()
        print(f"[MCP Bridge] HTTP 服务器启动在 http://{self.host}:{self.port}")

    def stop(self):
        self.running = False
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None
        print("[MCP Bridge] 服务器已停止")

    def _serve_forever(self):
        try:
            if self.httpd:
                self.httpd.serve_forever(poll_interval=0.5)
        except Exception as e:
            if self.running:
                print(f"[MCP Bridge] 错误: {e}")

    def _execute_in_main_thread(self, request):
        action = request.get("tool") or request.get("action")
        params = request.get("args") or request.get("params") or {}
        if not action:
            return {"ok": False, "success": False, "error": "缺少字段 tool/action", "logs": ["missing_tool"]}
        if action not in MCP_WHITELIST_TOOLS:
            return {
                "ok": False,
                "success": False,
                "error": f"工具未在白名单中: {action}",
                "logs": ["tool_not_whitelisted"],
            }

        import queue

        result_queue = queue.Queue()

        def do_action():
            try:
                from . import tool_definitions
                result = tool_definitions.execute_tool(action, params)
                result_queue.put(result)
            except Exception as e:
                result_queue.put({"success": False, "error": str(e)})
            return None

        bpy.app.timers.register(do_action)

        try:
            result = result_queue.get(timeout=30.0)
            if result.get("success"):
                return {
                    "ok": True,
                    "success": True,
                    "data": result.get("result"),
                    "error": None,
                    "logs": [f"tool={action}"],
                }
            else:
                return {
                    "ok": False,
                    "success": False,
                    "data": None,
                    "error": result.get("error"),
                    "logs": [f"tool={action}"],
                }
        except Exception:
            return {"ok": False, "success": False, "data": None, "error": "操作超时", "logs": [f"tool={action}", "timeout"]}


_mcp_server = None
_chat_ui_error = ""


class MCP_OT_StartServer(bpy.types.Operator):
    bl_idname = "mcp.start_server"
    bl_label = "启动 MCP 服务器"

    def execute(self, context):
        global _mcp_server
        if _mcp_server is None or not _mcp_server.running:
            _mcp_server = MCPBridgeServer()
            _mcp_server.start()
            self.report({"INFO"}, "MCP 服务器已启动")
        else:
            self.report({"WARNING"}, "服务器已在运行")
        return {"FINISHED"}


class MCP_OT_StopServer(bpy.types.Operator):
    bl_idname = "mcp.stop_server"
    bl_label = "停止 MCP 服务器"

    def execute(self, context):
        global _mcp_server
        if _mcp_server and _mcp_server.running:
            _mcp_server.stop()
            _mcp_server = None
            self.report({"INFO"}, "MCP 服务器已停止")
        else:
            self.report({"WARNING"}, "服务器未运行")
        return {"FINISHED"}


class BLENDER_AGENT_PT_ServicePanel(bpy.types.Panel):
    bl_label = "🔌 MCP & 服务"
    bl_idname = "BLENDER_AGENT_PT_service"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Agent"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        if _chat_ui_error:
            err_box = layout.box()
            err_box.label(text="⚠️ Chat UI 加载失败:", icon="ERROR")
            for line in _chat_ui_error.split("\n")[:5]:
                err_box.label(text=line[:120])

        box = layout.box()
        box.label(text="🎨 Meshy AI 3D生成", icon="MESH_MONKEY")
        try:
            prefs = context.preferences.addons[__package__].preferences
            if not prefs.meshy_api_key:
                box.label(text="⚠️ 请配置 Meshy API Key", icon="INFO")
                box.operator("agent.open_settings", text="打开设置", icon="PREFERENCES")
            else:
                box.label(text="✓ Meshy 已配置", icon="CHECKMARK")
                box.label(text="通过对话使用文生3D/图生3D")
        except Exception:
            pass

        layout.separator()

        box = layout.box()
        box.label(text="🔌 MCP Bridge", icon="LINKED")
        global _mcp_server
        if _mcp_server and _mcp_server.running:
            box.label(text="状态: 运行中 ✓", icon="CHECKMARK")
            box.operator("mcp.stop_server", icon="PAUSE")
        else:
            box.label(text="状态: 已停止", icon="X")
            box.operator("mcp.start_server", icon="PLAY")
        box.label(text="端口: 9876")


base_classes = [
    MCP_OT_StartServer,
    MCP_OT_StopServer,
    BLENDER_AGENT_PT_ServicePanel,
]


def register():
    global _chat_ui_error
    for cls in base_classes:
        bpy.utils.register_class(cls)

    try:
        from . import chat_ui
        chat_ui.register()
    except Exception as e:
        import traceback
        _chat_ui_error = traceback.format_exc()
        print(f"[Blender Agent] Chat UI 注册失败:\n{_chat_ui_error}")


def unregister():
    global _mcp_server
    if _mcp_server:
        _mcp_server.stop()

    try:
        from . import chat_ui
        chat_ui.unregister()
    except Exception as e:
        print(f"[Blender Agent] Chat UI 注销失败: {e}")

    for cls in reversed(base_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
