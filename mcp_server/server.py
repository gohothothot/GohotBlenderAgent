"""
Blender MCP Server - 从 Registry 自动生成工具列表

与 Agent 模式共用 tools/registry，消除重复定义。
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
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(30.0)
        client.connect(("127.0.0.1", 9876))

        request = {"action": action, "params": params or {}}
        client.send(json.dumps(request).encode("utf-8"))

        chunks = []
        while True:
            try:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            except socket.timeout:
                break

        client.close()
        response = b"".join(chunks).decode("utf-8")
        return json.loads(response)
    except ConnectionRefusedError:
        return {"success": False, "error": "无法连接 Blender，请确保插件已启动"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_all_tool_defs() -> list[dict]:
    """从 registry 获取所有工具定义（延迟导入避免 bpy 依赖）"""
    try:
        from blender_mcp.tools.registry import get_registry
        registry = get_registry()
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in registry.get_all()
        ]
    except ImportError:
        return _get_fallback_tools()


def _get_fallback_tools() -> list[dict]:
    """回退：从旧 tool_definitions.py 获取"""
    try:
        from blender_mcp.tool_definitions import TOOLS
        return TOOLS
    except ImportError:
        return []


@server.list_tools()
async def list_tools():
    tool_defs = _get_all_tool_defs()
    return [
        Tool(
            name=f"blender_{t['name']}",
            description=t.get("description", ""),
            inputSchema=t.get("input_schema", {"type": "object", "properties": {}, "required": []}),
        )
        for t in tool_defs
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    action = name.removeprefix("blender_") if name.startswith("blender_") else name

    result = send_to_blender(action, arguments)

    if result.get("success"):
        data = result.get("data") or result.get("result")
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]
    else:
        return [TextContent(type="text", text=f"Error: {result.get('error')}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
