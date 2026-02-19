"""
Blender MCP Server - 让外部 AI 客户端控制 Blender

与 Agent 模式共用 tools 模块，保持功能一致
"""

import asyncio
import socket
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("blender-mcp")


def send_to_blender(action: str, params: dict = None) -> dict:
    """发送指令到 Blender 插件"""
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(10.0)
        client.connect(("127.0.0.1", 9876))

        request = {"action": action, "params": params or {}}
        client.send(json.dumps(request).encode("utf-8"))

        response = client.recv(4096).decode("utf-8")
        client.close()

        return json.loads(response)
    except ConnectionRefusedError:
        return {"success": False, "error": "无法连接 Blender，请确保插件已启动"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@server.list_tools()
async def list_tools():
    """返回所有可用工具，与 Agent 模式保持一致"""
    return [
        Tool(
            name="blender_list_objects",
            description="列出 Blender 场景中的所有物体",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="blender_create_primitive",
            description="创建基础几何体（cube/sphere/cylinder/plane/cone/torus/monkey）",
            inputSchema={
                "type": "object",
                "properties": {
                    "primitive_type": {
                        "type": "string",
                        "enum": [
                            "cube",
                            "sphere",
                            "cylinder",
                            "plane",
                            "cone",
                            "torus",
                            "monkey",
                        ],
                        "description": "几何体类型",
                    },
                    "location": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "位置 [x, y, z]",
                    },
                    "scale": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "缩放 [x, y, z]",
                    },
                },
                "required": ["primitive_type"],
            },
        ),
        Tool(
            name="blender_delete_object",
            description="删除指定物体",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "物体名称"}},
                "required": ["name"],
            },
        ),
        Tool(
            name="blender_transform_object",
            description="变换物体（移动、旋转、缩放）",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "物体名称"},
                    "location": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "位置 [x, y, z]",
                    },
                    "rotation": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "旋转角度（度）[x, y, z]",
                    },
                    "scale": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "缩放 [x, y, z]",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="blender_set_material",
            description="设置物体材质颜色",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_name": {"type": "string", "description": "物体名称"},
                    "color": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "RGBA 颜色 [r, g, b, a]，范围 0-1",
                    },
                    "material_name": {
                        "type": "string",
                        "description": "材质名称（可选）",
                    },
                },
                "required": ["object_name", "color"],
            },
        ),
        Tool(
            name="blender_set_metallic_roughness",
            description="设置材质金属度和粗糙度",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_name": {"type": "string", "description": "物体名称"},
                    "metallic": {"type": "number", "description": "金属度 0-1"},
                    "roughness": {"type": "number", "description": "粗糙度 0-1"},
                },
                "required": ["object_name"],
            },
        ),
        Tool(
            name="blender_get_object_info",
            description="获取物体详细信息",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "物体名称"}},
                "required": ["name"],
            },
        ),
        Tool(
            name="blender_execute_python",
            description="执行自定义 Python/bpy 代码（用于复杂操作）",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python 代码"},
                    "description": {"type": "string", "description": "代码功能描述"},
                },
                "required": ["code", "description"],
            },
        ),
    ]


TOOL_ACTION_MAP = {
    "blender_list_objects": "list_objects",
    "blender_create_primitive": "create_primitive",
    "blender_delete_object": "delete_object",
    "blender_transform_object": "transform_object",
    "blender_set_material": "set_material",
    "blender_set_metallic_roughness": "set_metallic_roughness",
    "blender_get_object_info": "get_object_info",
    "blender_execute_python": "execute_python",
}


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """执行工具调用"""
    action = TOOL_ACTION_MAP.get(name)
    if not action:
        return [TextContent(type="text", text=f"✗ 未知工具: {name}")]

    result = send_to_blender(action, arguments)

    if result.get("success"):
        data = result.get("data") or result.get("result")
        return [
            TextContent(type="text", text=f"✓ {json.dumps(data, ensure_ascii=False)}")
        ]
    else:
        return [TextContent(type="text", text=f"✗ 错误: {result.get('error')}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
