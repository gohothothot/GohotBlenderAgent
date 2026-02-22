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
        # Shader Tools
        Tool(
            name="blender_shader_create_material",
            description="创建新的材质，可选择是否使用节点系统",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "材质名称"},
                    "use_nodes": {"type": "boolean", "description": "是否使用节点系统（默认 True）"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="blender_shader_delete_material",
            description="删除指定的材质",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "材质名称"}},
                "required": ["name"],
            },
        ),
        Tool(
            name="blender_shader_list_materials",
            description="列出 Blender 中所有可用的材质",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="blender_shader_assign_material",
            description="将材质分配给物体，可指定材质槽索引",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "object_name": {"type": "string", "description": "物体名称"},
                    "slot_index": {"type": "integer", "description": "材质槽索引（可选，默认为 0）"},
                },
                "required": ["material_name", "object_name"],
            },
        ),
        Tool(
            name="blender_shader_inspect_nodes",
            description="查看材质的节点树结构",
            inputSchema={
                "type": "object",
                "properties": {"material_name": {"type": "string", "description": "材质名称"}},
                "required": ["material_name"],
            },
        ),
        Tool(
            name="blender_shader_add_node",
            description="向材质节点树添加新节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_type": {"type": "string", "description": "节点类型（如：ShaderNodeBsdfPrincipled, ShaderNodeTexImage 等）"},
                    "label": {"type": "string", "description": "节点标签（可选）"},
                    "location": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "节点位置 [x, y]（可选）",
                    },
                },
                "required": ["material_name", "node_type"],
            },
        ),
        Tool(
            name="blender_shader_delete_node",
            description="从材质节点树中删除指定节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "节点名称"},
                },
                "required": ["material_name", "node_name"],
            },
        ),
        Tool(
            name="blender_shader_set_node_input",
            description="设置节点的输入 socket 值",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "节点名称"},
                    "input_name": {"type": "string", "description": "输入 socket 名称"},
                    "value": {"description": "输入值（支持数字、数组、颜色等）"},
                },
                "required": ["material_name", "node_name", "input_name", "value"],
            },
        ),
        Tool(
            name="blender_shader_set_node_property",
            description="设置节点的属性值",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "节点名称"},
                    "property_name": {"type": "string", "description": "属性名称"},
                    "value": {"description": "属性值"},
                },
                "required": ["material_name", "node_name", "property_name", "value"],
            },
        ),
        Tool(
            name="blender_shader_link_nodes",
            description="连接两个节点的输出和输入 socket",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "from_node": {"type": "string", "description": "源节点名称"},
                    "from_output": {"type": "string", "description": "源节点输出 socket 名称"},
                    "to_node": {"type": "string", "description": "目标节点名称"},
                    "to_input": {"type": "string", "description": "目标节点输入 socket 名称"},
                },
                "required": ["material_name", "from_node", "from_output", "to_node", "to_input"],
            },
        ),
        Tool(
            name="blender_shader_unlink_nodes",
            description="断开两个节点之间的连接",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "from_node": {"type": "string", "description": "源节点名称"},
                    "from_output": {"type": "string", "description": "源节点输出 socket 名称"},
                    "to_node": {"type": "string", "description": "目标节点名称"},
                    "to_input": {"type": "string", "description": "目标节点输入 socket 名称"},
                },
                "required": ["material_name", "from_node", "from_output", "to_node", "to_input"],
            },
        ),
        Tool(
            name="blender_shader_colorramp_add_stop",
            description="向颜色渐变节点添加新的色标",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "颜色渐变节点名称"},
                    "position": {"type": "number", "description": "色标位置（0-1）"},
                    "color": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "RGBA 颜色 [r, g, b, a]，范围 0-1",
                    },
                },
                "required": ["material_name", "node_name", "position", "color"],
            },
        ),
        Tool(
            name="blender_shader_colorramp_remove_stop",
            description="从颜色渐变节点删除指定位置的色标",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "颜色渐变节点名称"},
                    "index": {"type": "integer", "description": "色标索引"},
                },
                "required": ["material_name", "node_name", "index"],
            },
        ),
        Tool(
            name="blender_shader_colorramp_set_interpolation",
            description="设置颜色渐变节点的插值方式",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "颜色渐变节点名称"},
                    "interpolation": {
                        "type": "string",
                        "enum": ["LINEAR", "CONSTANT", "NEAREST", "BARYCENTRIC", "SMOOTH", "EASE"],
                        "description": "插值方式：LINEAR（线性）、CONSTANT（恒定）、SMOOTH（平滑）等",
                    },
                },
                "required": ["material_name", "node_name", "interpolation"],
            },
        ),
        Tool(
            name="blender_shader_create_procedural_material",
            description="使用预设创建程序化材质",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "材质名称"},
                    "preset": {
                        "type": "string",
                        "enum": ["wood", "marble", "metal_scratched", "brick", "fabric", "glass", "gold", "rubber", "concrete", "plastic", "water", "ice", "lava", "crystal", "snow", "leather", "neon", "emissive"],
                        "description": "预设类型：wood(木纹), marble(大理石), metal_scratched(磨损金属), brick(砖块), fabric(布料), glass(玻璃), gold(黄金), rubber(橡胶), concrete(混凝土), plastic(塑料), water(水), ice(冰), lava(熔岩), crystal(水晶), snow(雪), leather(皮革), neon(霓虹), emissive(发光)",
                    },
                },
                "required": ["name", "preset"],
            },
        ),
        Tool(
            name="blender_shader_preview_material",
            description="预览材质效果（生成缩略图）",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "resolution": {"type": "integer", "description": "预览分辨率（默认 512）"},
                },
                "required": ["material_name"],
            },
        ),
        Tool(
            name="blender_shader_configure_eevee",
            description="为 EEVEE 配置透射材质的必要渲染设置。当透射材质显示为黑色时使用。",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                },
                "required": ["material_name"],
            },
        ),
        # TODO Tools
        Tool(
            name="blender_shader_create_toon_material",
            description="创建卡通/二次元渲染材质（NPR）。支持预设：toon_basic, toon_skin, toon_hair, toon_eye, toon_cloth, toon_metal",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "材质名称"},
                    "preset": {
                        "type": "string",
                        "enum": ["toon_basic", "toon_skin", "toon_hair", "toon_eye", "toon_cloth", "toon_metal"],
                        "description": "卡通预设类型",
                    },
                },
                "required": ["name", "preset"],
            },
        ),
        Tool(
            name="blender_shader_convert_to_toon",
            description="将现有PBR材质转换为卡通渲染风格，保留原有贴图。适用于MeshyAI生成的模型导入后转为二次元风格。",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "要转换的材质名称"},
                    "keep_textures": {"type": "boolean", "description": "是否保留原有贴图（默认true）"},
                },
                "required": ["material_name"],
            },
        ),
        Tool(
            name="blender_shader_list_available_nodes",
            description="列出所有可用的着色器节点类型，按类别分组",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="blender_shader_get_node_sockets",
            description="获取节点的所有输入输出 socket 详细信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string"},
                    "node_name": {"type": "string"},
                },
                "required": ["material_name", "node_name"],
            },
        ),
        Tool(
            name="blender_shader_batch_add_nodes",
            description="批量添加节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string"},
                    "nodes": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["material_name", "nodes"],
            },
        ),
        Tool(
            name="blender_shader_batch_link_nodes",
            description="批量连接节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string"},
                    "links": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["material_name", "links"],
            },
        ),
        Tool(
            name="blender_shader_clear_nodes",
            description="清除材质的所有节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string"},
                    "keep_output": {"type": "boolean"},
                },
                "required": ["material_name"],
            },
        ),
        Tool(
            name="blender_shader_get_material_summary",
            description="获取材质完整摘要",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string"},
                },
                "required": ["material_name"],
            },
        ),
        Tool(
            name="blender_anim_add_uv_scroll",
            description="为 Mapping 节点添加 UV 滚动动画",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "Mapping 节点名称"},
                    "speed_x": {"type": "number", "description": "X轴速度"},
                    "speed_y": {"type": "number", "description": "Y轴速度"},
                    "speed_z": {"type": "number", "description": "Z轴速度"},
                },
                "required": ["material_name", "node_name"],
            },
        ),
        Tool(
            name="blender_anim_add_uv_rotate",
            description="为 Mapping 节点添加 UV 旋转动画",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "Mapping 节点名称"},
                    "speed": {"type": "number", "description": "旋转速度（弧度/帧）"},
                    "axis": {"type": "string", "enum": ["X", "Y", "Z"], "description": "旋转轴"},
                },
                "required": ["material_name", "node_name"],
            },
        ),
        Tool(
            name="blender_anim_add_uv_scale",
            description="为 Mapping 节点添加 UV 缩放动画",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "Mapping 节点名称"},
                    "speed_x": {"type": "number", "description": "X轴缩放速度"},
                    "speed_y": {"type": "number", "description": "Y轴缩放速度"},
                    "speed_z": {"type": "number", "description": "Z轴缩放速度"},
                    "base_scale": {"type": "number", "description": "初始缩放值"},
                },
                "required": ["material_name", "node_name"],
            },
        ),
        Tool(
            name="blender_anim_add_value_driver",
            description="为任意节点输入添加 Driver 表达式动画",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "节点名称"},
                    "input_name": {"type": "string", "description": "输入名称"},
                    "expression": {"type": "string", "description": "Driver 表达式"},
                    "index": {"type": "integer", "description": "向量分量索引（-1=标量）"},
                },
                "required": ["material_name", "node_name", "input_name", "expression"],
            },
        ),
        Tool(
            name="blender_anim_add_keyframe",
            description="为节点输入在指定帧插入关键帧",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "节点名称"},
                    "input_name": {"type": "string", "description": "输入名称"},
                    "frame": {"type": "integer", "description": "帧号"},
                    "value": {"description": "值"},
                    "index": {"type": "integer", "description": "向量分量索引"},
                },
                "required": ["material_name", "node_name", "input_name", "frame", "value"],
            },
        ),
        Tool(
            name="blender_anim_remove_driver",
            description="移除节点输入上的 Driver 动画",
            inputSchema={
                "type": "object",
                "properties": {
                    "material_name": {"type": "string", "description": "材质名称"},
                    "node_name": {"type": "string", "description": "节点名称"},
                    "input_name": {"type": "string", "description": "输入名称"},
                    "index": {"type": "integer", "description": "向量分量索引"},
                },
                "required": ["material_name", "node_name", "input_name"],
            },
        ),
        Tool(
            name="blender_web_search",
            description="搜索网络获取参考资料（Blender教程、shader技巧等）",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "description": "最大结果数"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="blender_web_fetch",
            description="抓取指定网页的文本内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "网页 URL"},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="blender_web_search_blender",
            description="Blender 专题搜索",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                },
                "required": ["topic"],
            },
        ),
        Tool(
            name="blender_web_analyze_reference",
            description="分析参考链接，提取材质/着色器相关信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="blender_scene_add_light",
            description="添加灯光（POINT/SUN/SPOT/AREA）",
            inputSchema={
                "type": "object",
                "properties": {
                    "light_type": {"type": "string", "enum": ["POINT", "SUN", "SPOT", "AREA"]},
                    "location": {"type": "array", "items": {"type": "number"}},
                    "energy": {"type": "number"},
                    "color": {"type": "array", "items": {"type": "number"}},
                    "name": {"type": "string"},
                },
                "required": [],
            },
        ),
        Tool(
            name="blender_scene_modify_light",
            description="修改灯光参数",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "灯光名称"},
                    "energy": {"type": "number"},
                    "color": {"type": "array", "items": {"type": "number"}},
                    "spot_size": {"type": "number"},
                    "spot_blend": {"type": "number"},
                    "shadow_soft_size": {"type": "number"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="blender_scene_add_camera",
            description="添加相机",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {"type": "array", "items": {"type": "number"}},
                    "rotation": {"type": "array", "items": {"type": "number"}},
                    "lens": {"type": "number"},
                    "name": {"type": "string"},
                },
                "required": [],
            },
        ),
        Tool(
            name="blender_scene_set_active_camera",
            description="设置活动相机",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        ),
        Tool(
            name="blender_scene_add_modifier",
            description="添加修改器（SUBSURF/MIRROR/ARRAY/BEVEL/SOLIDIFY等）",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "modifier_type": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["object_name", "modifier_type"],
            },
        ),
        Tool(
            name="blender_scene_set_modifier_param",
            description="设置修改器参数",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "modifier_name": {"type": "string"},
                    "param_name": {"type": "string"},
                    "value": {"description": "参数值"},
                },
                "required": ["object_name", "modifier_name", "param_name", "value"],
            },
        ),
        Tool(
            name="blender_scene_remove_modifier",
            description="移除修改器",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "modifier_name": {"type": "string"},
                },
                "required": ["object_name", "modifier_name"],
            },
        ),
        Tool(
            name="blender_scene_manage_collection",
            description="管理集合（create/delete/move_object/list）",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "delete", "move_object", "list"]},
                    "collection_name": {"type": "string"},
                    "object_name": {"type": "string"},
                    "parent_name": {"type": "string"},
                },
                "required": ["action", "collection_name"],
            },
        ),
        Tool(
            name="blender_scene_set_world",
            description="设置世界环境（背景颜色或HDRI）",
            inputSchema={
                "type": "object",
                "properties": {
                    "color": {"type": "array", "items": {"type": "number"}},
                    "strength": {"type": "number"},
                    "use_hdri": {"type": "boolean"},
                    "hdri_path": {"type": "string"},
                },
                "required": [],
            },
        ),
        Tool(
            name="blender_scene_duplicate_object",
            description="复制物体",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "linked": {"type": "boolean"},
                    "new_name": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="blender_scene_parent_object",
            description="设置父子关系",
            inputSchema={
                "type": "object",
                "properties": {
                    "child_name": {"type": "string"},
                    "parent_name": {"type": "string"},
                },
                "required": ["child_name", "parent_name"],
            },
        ),
        Tool(
            name="blender_scene_set_visibility",
            description="设置物体可见性",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "visible": {"type": "boolean"},
                    "render_visible": {"type": "boolean"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="blender_scene_get_render_settings",
            description="获取当前渲染设置",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="blender_scene_set_render_settings",
            description="设置渲染参数",
            inputSchema={
                "type": "object",
                "properties": {
                    "engine": {"type": "string"},
                    "resolution": {"type": "array", "items": {"type": "number"}},
                    "samples": {"type": "integer"},
                    "use_ssr": {"type": "boolean"},
                    "use_ssr_refraction": {"type": "boolean"},
                    "film_transparent": {"type": "boolean"},
                    "view_transform": {"type": "string"},
                },
                "required": [],
            },
        ),
        Tool(
            name="blender_scene_get_object_materials",
            description="获取物体的所有材质详细信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                },
                "required": ["object_name"],
            },
        ),
        Tool(
            name="blender_scene_get_world_info",
            description="获取世界环境设置信息",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="blender_scene_list_all_materials",
            description="列出场景中所有材质及其使用情况",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="blender_kb_search",
            description="搜索本地知识库",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="blender_kb_save",
            description="保存知识到本地知识库",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "tags": {"type": "string"},
                },
                "required": ["name", "description"],
            },
        ),
        Tool(
            name="blender_get_action_log",
            description="获取最近的操作日志",
            inputSchema={
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": [],
            },
        ),
        # TODO Tools
        Tool(
            name="blender_get_todo_list",
            description="获取用户的 TODO 列表，包括用户任务和 Agent 任务",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="blender_complete_todo",
            description="标记指定的 TODO 项为已完成",
            inputSchema={
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "TODO 项的索引（从 0 开始）"},
                },
                "required": ["index"],
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
    # Shader Tools
    "blender_shader_create_material": "shader_create_material",
    "blender_shader_delete_material": "shader_delete_material",
    "blender_shader_list_materials": "shader_list_materials",
    "blender_shader_assign_material": "shader_assign_material",
    "blender_shader_inspect_nodes": "shader_inspect_nodes",
    "blender_shader_add_node": "shader_add_node",
    "blender_shader_delete_node": "shader_delete_node",
    "blender_shader_set_node_input": "shader_set_node_input",
    "blender_shader_set_node_property": "shader_set_node_property",
    "blender_shader_link_nodes": "shader_link_nodes",
    "blender_shader_unlink_nodes": "shader_unlink_nodes",
    "blender_shader_colorramp_add_stop": "shader_colorramp_add_stop",
    "blender_shader_colorramp_remove_stop": "shader_colorramp_remove_stop",
    "blender_shader_colorramp_set_interpolation": "shader_colorramp_set_interpolation",
    "blender_shader_create_procedural_material": "shader_create_procedural_material",
    "blender_shader_preview_material": "shader_preview_material",
    "blender_shader_configure_eevee": "shader_configure_eevee",
    # Toon/NPR Tools
    "blender_shader_create_toon_material": "shader_create_toon_material",
    "blender_shader_convert_to_toon": "shader_convert_to_toon",
    "blender_shader_list_available_nodes": "shader_list_available_nodes",
    "blender_shader_get_node_sockets": "shader_get_node_sockets",
    "blender_shader_batch_add_nodes": "shader_batch_add_nodes",
    "blender_shader_batch_link_nodes": "shader_batch_link_nodes",
    "blender_shader_clear_nodes": "shader_clear_nodes",
    "blender_shader_get_material_summary": "shader_get_material_summary",
    "blender_anim_add_uv_scroll": "anim_add_uv_scroll",
    "blender_anim_add_uv_rotate": "anim_add_uv_rotate",
    "blender_anim_add_uv_scale": "anim_add_uv_scale",
    "blender_anim_add_value_driver": "anim_add_value_driver",
    "blender_anim_add_keyframe": "anim_add_keyframe",
    "blender_anim_remove_driver": "anim_remove_driver",
    "blender_web_search": "web_search",
    "blender_web_fetch": "web_fetch",
    "blender_web_search_blender": "web_search_blender",
    "blender_web_analyze_reference": "web_analyze_reference",
    "blender_scene_add_light": "scene_add_light",
    "blender_scene_modify_light": "scene_modify_light",
    "blender_scene_add_camera": "scene_add_camera",
    "blender_scene_set_active_camera": "scene_set_active_camera",
    "blender_scene_add_modifier": "scene_add_modifier",
    "blender_scene_set_modifier_param": "scene_set_modifier_param",
    "blender_scene_remove_modifier": "scene_remove_modifier",
    "blender_scene_manage_collection": "scene_manage_collection",
    "blender_scene_set_world": "scene_set_world",
    "blender_scene_duplicate_object": "scene_duplicate_object",
    "blender_scene_parent_object": "scene_parent_object",
    "blender_scene_set_visibility": "scene_set_visibility",
    "blender_scene_get_render_settings": "scene_get_render_settings",
    "blender_scene_set_render_settings": "scene_set_render_settings",
    "blender_scene_get_object_materials": "scene_get_object_materials",
    "blender_scene_get_world_info": "scene_get_world_info",
    "blender_scene_list_all_materials": "scene_list_all_materials",
    "blender_kb_search": "kb_search",
    "blender_kb_save": "kb_save",
    "blender_get_action_log": "get_action_log",
    # TODO Tools
    "blender_get_todo_list": "get_todo_list",
    "blender_complete_todo": "complete_todo",
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
