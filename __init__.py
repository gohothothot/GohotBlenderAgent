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
    "version": (2, 0),
    "blender": (5, 0, 0),
    "description": "AI 驱动的 Blender 助手 - 支持对话式操作和 Meshy AI 3D生成",
    "category": "Development",
}

import bpy
import socket
import threading
import json

# ========== MCP Bridge 服务器（保留原功能）==========


class MCPBridgeServer:
    """Socket 服务器，接收来自 MCP Server 的指令"""

    def __init__(self, host="127.0.0.1", port=9876):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.thread = None

    def start(self):
        """启动服务器"""
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
        """停止服务器"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        print("[MCP Bridge] 服务器已停止")

    def _listen_loop(self):
        """监听循环"""
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
        """处理客户端请求"""
        try:
            data = client.recv(4096).decode("utf-8")
            if data:
                request = json.loads(data)
                result = self._execute_in_main_thread(request)
                client.send(json.dumps(result).encode("utf-8"))
        except Exception as e:
            error_response = {"success": False, "error": str(e)}
            client.send(json.dumps(error_response).encode("utf-8"))
        finally:
            client.close()

    def _execute_in_main_thread(self, request):
        """在 Blender 主线程执行操作"""
        action = request.get("action")
        params = request.get("params", {})

        import queue

        result_queue = queue.Queue()

        def do_action():
            try:
                # 使用 tools 模块执行
                from . import tools

                result = tools.execute_tool(action, params)
                result_queue.put(result)
            except Exception as e:
                result_queue.put({"success": False, "error": str(e)})
            return None

        bpy.app.timers.register(do_action)

        try:
            result = result_queue.get(timeout=5.0)
            # 转换格式以兼容旧 MCP
            if result.get("success"):
                return {"success": True, "data": result.get("result")}
            else:
                return {"success": False, "error": result.get("error")}
        except:
            return {"success": False, "error": "操作超时"}


# 全局服务器实例
_mcp_server = None


# ========== MCP 相关 Operators ==========


class MCP_OT_StartServer(bpy.types.Operator):
    """启动 MCP Bridge 服务器"""

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
    """停止 MCP Bridge 服务器"""

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


# ========== 主面板（整合 Agent 和 MCP）==========


class BLENDER_AGENT_PT_MainPanel(bpy.types.Panel):
    bl_label = "Gohot Blender Agent"
    bl_idname = "BLENDER_AGENT_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI"

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="🤖 AI 助手", icon="OUTLINER_OB_LIGHT")

        try:
            prefs = context.preferences.addons[__package__].preferences
            
            if not prefs.api_key:
                box.label(text="⚠️ 请先配置 API Key", icon="ERROR")
                box.operator("agent.open_settings", text="打开设置", icon="PREFERENCES")
            else:
                box.operator("agent.open_chat", text="打开对话窗口", icon="CONSOLE")

                state = context.scene.blender_agent
                box.prop(state, "input_text", text="")
                row = box.row(align=True)
                row.operator("agent.send_message", text="发送", icon="PLAY")
                row.operator("agent.clear_history", text="", icon="TRASH")

                if state.is_processing:
                    box.label(text="⏳ 处理中...", icon="SORTTIME")
                    
                box.operator("agent.open_settings", text="设置", icon="PREFERENCES")
        except Exception:
            box.label(text="⚠️ 插件初始化中...", icon="ERROR")

        layout.separator()

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
        except:
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


# ========== 注册 ==========

# 基础类（不依赖其他模块）
base_classes = [
    MCP_OT_StartServer,
    MCP_OT_StopServer,
    BLENDER_AGENT_PT_MainPanel,
]


def register():
    # 注册基础类
    for cls in base_classes:
        bpy.utils.register_class(cls)

    # 注册 Chat UI 模块
    try:
        from . import chat_ui

        chat_ui.register()
    except Exception as e:
        print(f"[Blender Agent] Chat UI 注册失败: {e}")


def unregister():
    # 停止 MCP 服务器
    global _mcp_server
    if _mcp_server:
        _mcp_server.stop()

    # 注销 Chat UI 模块
    try:
        from . import chat_ui

        chat_ui.unregister()
    except Exception as e:
        print(f"[Blender Agent] Chat UI 注销失败: {e}")

    # 注销基础类
    for cls in reversed(base_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
