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
import socket
import threading
import json


class MCPBridgeServer:
    def __init__(self, host="127.0.0.1", port=9876):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.thread = None

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        self.server_socket.settimeout(1.0)
        self.running = True

        self.thread = threading.Thread(target=self._listen_loop)
        self.thread.daemon = True
        self.thread.start()
        print(f"[MCP Bridge] 服务器启动在 {self.host}:{self.port}")

    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        print("[MCP Bridge] 服务器已停止")

    def _listen_loop(self):
        while self.running:
            try:
                client, addr = self.server_socket.accept()
                print(f"[MCP Bridge] 客户端连接: {addr}")
                self._handle_client(client)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[MCP Bridge] 错误: {e}")

    def _handle_client(self, client):
        try:
            chunks = []
            while True:
                try:
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if len(chunk) < 65536:
                        break
                except socket.timeout:
                    break
            data = b"".join(chunks).decode("utf-8")
            if data:
                request = json.loads(data)
                result = self._execute_in_main_thread(request)
                response = json.dumps(result).encode("utf-8")
                client.sendall(response)
        except Exception as e:
            error_response = {"success": False, "error": str(e)}
            client.sendall(json.dumps(error_response).encode("utf-8"))
        finally:
            client.close()

    def _execute_in_main_thread(self, request):
        action = request.get("action")
        params = request.get("params", {})

        import queue

        result_queue = queue.Queue()

        def do_action():
            try:
                from . import tools
                result = tools.execute_tool(action, params)
                result_queue.put(result)
            except Exception as e:
                result_queue.put({"success": False, "error": str(e)})
            return None

        bpy.app.timers.register(do_action)

        try:
            result = result_queue.get(timeout=30.0)
            if result.get("success"):
                return {"success": True, "data": result.get("result")}
            else:
                return {"success": False, "error": result.get("error")}
        except Exception:
            return {"success": False, "error": "操作超时"}


_mcp_server = None


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
    for cls in base_classes:
        bpy.utils.register_class(cls)

    try:
        from . import chat_ui
        chat_ui.register()
    except Exception as e:
        print(f"[Blender Agent] Chat UI 注册失败: {e}")


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
