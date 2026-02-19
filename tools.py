"""
Blender Agent Tools - 工具定义

定义 Agent 可以调用的所有工具
使用 Claude 的 Tool Use 格式
"""

import bpy
import json
from typing import Any

# ========== 工具定义 ==========
# Claude Tool Use 格式：每个工具有 name, description, input_schema

TOOLS = [
    # ----- 基础操作 -----
    {
        "name": "list_objects",
        "description": "列出场景中所有物体的名称和类型",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "create_primitive",
        "description": "创建基础几何体（立方体、球体、圆柱体、平面、圆锥等）",
        "input_schema": {
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
                    "description": "位置 [x, y, z]，默认 [0, 0, 0]",
                },
                "scale": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "缩放 [x, y, z]，默认 [1, 1, 1]",
                },
            },
            "required": ["primitive_type"],
        },
    },
    {
        "name": "delete_object",
        "description": "删除指定名称的物体",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "要删除的物体名称"}
            },
            "required": ["name"],
        },
    },
    {
        "name": "transform_object",
        "description": "变换物体（移动、旋转、缩放）",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "物体名称"},
                "location": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "新位置 [x, y, z]",
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
    },
    # ----- 材质和纹理 -----
    {
        "name": "set_material",
        "description": "为物体设置材质颜色",
        "input_schema": {
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
                    "description": "材质名称（可选，默认自动生成）",
                },
            },
            "required": ["object_name", "color"],
        },
    },
    {
        "name": "set_metallic_roughness",
        "description": "设置材质的金属度和粗糙度",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "物体名称"},
                "metallic": {"type": "number", "description": "金属度 0-1"},
                "roughness": {"type": "number", "description": "粗糙度 0-1"},
            },
            "required": ["object_name"],
        },
    },
    # ----- Python 代码执行（最强大）-----
    {
        "name": "execute_python",
        "description": "执行自定义 Python/bpy 代码。用于复杂操作，如建模、动画等。代码可以访问 bpy 模块。注意：代码会在用户确认后执行。",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的 Python 代码"},
                "description": {
                    "type": "string",
                    "description": "代码功能的简短描述（给用户看）",
                },
            },
            "required": ["code", "description"],
        },
    },
    # ----- 场景信息 -----
    {
        "name": "get_object_info",
        "description": "获取物体的详细信息（位置、旋转、缩放、材质等）",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "物体名称"}},
            "required": ["name"],
        },
    },
    {
        "name": "meshy_text_to_3d",
        "description": "使用 Meshy AI 从文本描述生成 3D 模型。生成完成后会自动导入到场景中。这是一个异步操作，需要等待几分钟。",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "描述要生成的 3D 模型，例如：a cute cartoon cat",
                },
                "refine": {
                    "type": "boolean",
                    "description": "是否进行精细化处理生成纹理，默认 true",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "meshy_image_to_3d",
        "description": "使用 Meshy AI 从图片生成 3D 模型。需要提供图片的 URL。生成完成后会自动导入到场景中。",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_url": {
                    "type": "string",
                    "description": "图片的公开 URL 或 base64 数据 URI",
                },
            },
            "required": ["image_url"],
        },
    },
    {
        "name": "analyze_scene",
        "description": "截取当前3D视口画面，让AI分析场景并给出建议。可用于获取场景优化建议、构图建议、光照建议等。",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "想要AI分析的问题，如：这个场景的光照怎么样？构图有什么问题？",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "get_scene_info",
        "description": "获取当前场景的详细信息，包括所有物体、渲染设置、世界环境等。",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "setup_render",
        "description": "设置渲染参数。可设置渲染引擎、分辨率、采样数、输出路径等。",
        "input_schema": {
            "type": "object",
            "properties": {
                "engine": {
                    "type": "string",
                    "enum": ["cycles", "eevee", "workbench"],
                    "description": "渲染引擎",
                },
                "resolution_x": {
                    "type": "integer",
                    "description": "分辨率宽度",
                },
                "resolution_y": {
                    "type": "integer",
                    "description": "分辨率高度",
                },
                "samples": {
                    "type": "integer",
                    "description": "采样数（Cycles/EEVEE）",
                },
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径",
                },
                "file_format": {
                    "type": "string",
                    "enum": ["png", "jpg", "exr", "tiff"],
                    "description": "输出文件格式",
                },
                "use_gpu": {
                    "type": "boolean",
                    "description": "是否使用GPU渲染（仅Cycles）",
                },
            },
            "required": [],
        },
    },
    {
        "name": "render_image",
        "description": "执行渲染并保存图片到指定路径。",
        "input_schema": {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径（可选，默认保存到临时目录）",
                },
            },
            "required": [],
        },
    },
]


_meshy_tasks = {}


def _meshy_text_to_3d(prompt: str, refine: bool = True) -> dict:
    from . import meshy_api
    
    api = meshy_api.get_meshy_api()
    if api is None:
        return {"success": False, "result": None, "error": "请先在插件设置中配置 Meshy API Key"}

    try:
        prefs = bpy.context.preferences.addons["blender_mcp"].preferences
        ai_model = prefs.meshy_ai_model
    except:
        ai_model = "meshy-6"

    def on_preview_complete(task):
        if task.status == "SUCCEEDED" and refine:
            try:
                refine_task_id = api.text_to_3d_refine(task.task_id, enable_pbr=True)
                _meshy_tasks[refine_task_id] = {"type": "refine", "prompt": prompt}
                
                def on_refine_complete(refine_task):
                    if refine_task.status == "SUCCEEDED":
                        glb_url = refine_task.model_urls.get("glb")
                        texture_urls = refine_task.texture_urls
                        if glb_url:
                            meshy_api.download_and_import_model(
                                glb_url, 
                                f"Meshy_Refined_{task.task_id[:8]}", 
                                texture_urls
                            )
                
                api.on_task_complete = on_refine_complete
            except Exception as e:
                print(f"[Meshy] Refine failed: {e}")
        elif task.status == "SUCCEEDED" and not refine:
            glb_url = task.model_urls.get("glb")
            texture_urls = task.texture_urls
            if glb_url:
                meshy_api.download_and_import_model(
                    glb_url, 
                    f"Meshy_{task.task_id[:8]}", 
                    texture_urls
                )

    api.on_task_complete = on_preview_complete

    try:
        task_id = api.text_to_3d_preview(prompt, ai_model=ai_model)
        _meshy_tasks[task_id] = {"type": "preview", "prompt": prompt}
        
        return {
            "success": True,
            "result": f"已创建 Meshy 文生3D 任务，任务ID: {task_id}。模型生成中，完成后会自动导入场景（含PBR贴图）。预计需要 2-5 分钟。",
            "error": None,
            "task_id": task_id,
        }
    except Exception as e:
        return {"success": False, "result": None, "error": f"创建任务失败: {str(e)}"}


def _meshy_image_to_3d(image_url: str) -> dict:
    from . import meshy_api
    
    api = meshy_api.get_meshy_api()
    if api is None:
        return {"success": False, "result": None, "error": "请先在插件设置中配置 Meshy API Key"}

    try:
        prefs = bpy.context.preferences.addons["blender_mcp"].preferences
        ai_model = prefs.meshy_ai_model
    except:
        ai_model = "meshy-6"

    def on_complete(task):
        if task.status == "SUCCEEDED":
            glb_url = task.model_urls.get("glb")
            texture_urls = task.texture_urls
            if glb_url:
                meshy_api.download_and_import_model(
                    glb_url, 
                    f"Meshy_Image3D_{task.task_id[:8]}", 
                    texture_urls
                )

    api.on_task_complete = on_complete

    try:
        task_id = api.image_to_3d(image_url, enable_pbr=True, ai_model=ai_model)
        _meshy_tasks[task_id] = {"type": "image-to-3d", "image_url": image_url[:50]}
        
        return {
            "success": True,
            "result": f"已创建 Meshy 图生3D 任务，任务ID: {task_id}。模型生成中，完成后会自动导入场景（含PBR贴图）。预计需要 2-5 分钟。",
            "error": None,
            "task_id": task_id,
        }
    except Exception as e:
        return {"success": False, "result": None, "error": f"创建任务失败: {str(e)}"}


def execute_tool(tool_name: str, arguments: dict) -> dict:
    """
    执行工具并返回结果

    返回格式: {"success": bool, "result": Any, "error": str|None}
    """
    try:
        if tool_name == "list_objects":
            return _list_objects()
        elif tool_name == "create_primitive":
            return _create_primitive(**arguments)
        elif tool_name == "delete_object":
            return _delete_object(**arguments)
        elif tool_name == "transform_object":
            return _transform_object(**arguments)
        elif tool_name == "set_material":
            return _set_material(**arguments)
        elif tool_name == "set_metallic_roughness":
            return _set_metallic_roughness(**arguments)
        elif tool_name == "execute_python":
            # 特殊处理：需要用户确认
            return {
                "success": True,
                "result": "NEEDS_CONFIRMATION",
                "code": arguments.get("code"),
                "description": arguments.get("description"),
            }
        elif tool_name == "get_object_info":
            return _get_object_info(**arguments)
        elif tool_name == "meshy_text_to_3d":
            return _meshy_text_to_3d(**arguments)
        elif tool_name == "meshy_image_to_3d":
            return _meshy_image_to_3d(**arguments)
        elif tool_name == "analyze_scene":
            return _analyze_scene(**arguments)
        elif tool_name == "get_scene_info":
            return _get_scene_info_full()
        elif tool_name == "setup_render":
            return _setup_render(**arguments)
        elif tool_name == "render_image":
            return _render_image(**arguments)
        else:
            return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


# ----- 具体实现 -----


def _list_objects() -> dict:
    """列出所有物体"""
    objects = []
    for obj in bpy.context.scene.objects:
        objects.append(
            {"name": obj.name, "type": obj.type, "location": list(obj.location)}
        )
    return {"success": True, "result": objects, "error": None}


def _create_primitive(
    primitive_type: str, location: list = None, scale: list = None
) -> dict:
    """创建基础几何体"""
    location = location or [0, 0, 0]
    scale = scale or [1, 1, 1]

    ops_map = {
        "cube": bpy.ops.mesh.primitive_cube_add,
        "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
        "cylinder": bpy.ops.mesh.primitive_cylinder_add,
        "plane": bpy.ops.mesh.primitive_plane_add,
        "cone": bpy.ops.mesh.primitive_cone_add,
        "torus": bpy.ops.mesh.primitive_torus_add,
        "monkey": bpy.ops.mesh.primitive_monkey_add,
    }

    if primitive_type not in ops_map:
        return {
            "success": False,
            "result": None,
            "error": f"不支持的几何体类型: {primitive_type}",
        }

    ops_map[primitive_type](location=tuple(location))
    obj = bpy.context.active_object
    obj.scale = tuple(scale)

    return {
        "success": True,
        "result": f"创建了 {primitive_type}: {obj.name}",
        "error": None,
    }


def _delete_object(name: str) -> dict:
    """删除物体"""
    if name not in bpy.data.objects:
        return {"success": False, "result": None, "error": f"找不到物体: {name}"}

    obj = bpy.data.objects[name]
    bpy.data.objects.remove(obj, do_unlink=True)
    return {"success": True, "result": f"已删除: {name}", "error": None}


def _transform_object(
    name: str, location: list = None, rotation: list = None, scale: list = None
) -> dict:
    """变换物体"""
    if name not in bpy.data.objects:
        return {"success": False, "result": None, "error": f"找不到物体: {name}"}

    obj = bpy.data.objects[name]

    if location:
        obj.location = tuple(location)
    if rotation:
        import math

        obj.rotation_euler = tuple(math.radians(r) for r in rotation)
    if scale:
        obj.scale = tuple(scale)

    return {"success": True, "result": f"已变换: {name}", "error": None}


def _set_material(object_name: str, color: list, material_name: str = None) -> dict:
    """设置材质颜色"""
    if object_name not in bpy.data.objects:
        return {"success": False, "result": None, "error": f"找不到物体: {object_name}"}

    obj = bpy.data.objects[object_name]

    # 创建或获取材质
    mat_name = material_name or f"{object_name}_material"
    if mat_name in bpy.data.materials:
        mat = bpy.data.materials[mat_name]
    else:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True

    # 设置颜色
    if mat.use_nodes:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            # 确保颜色是 4 个值
            if len(color) == 3:
                color = color + [1.0]
            bsdf.inputs["Base Color"].default_value = tuple(color)

    # 应用材质
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return {
        "success": True,
        "result": f"已为 {object_name} 设置颜色 {color}",
        "error": None,
    }


def _set_metallic_roughness(
    object_name: str, metallic: float = None, roughness: float = None
) -> dict:
    """设置金属度和粗糙度"""
    if object_name not in bpy.data.objects:
        return {"success": False, "result": None, "error": f"找不到物体: {object_name}"}

    obj = bpy.data.objects[object_name]

    if not obj.data.materials:
        return {
            "success": False,
            "result": None,
            "error": f"{object_name} 没有材质，请先设置材质",
        }

    mat = obj.data.materials[0]
    if mat.use_nodes:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            if metallic is not None:
                bsdf.inputs["Metallic"].default_value = metallic
            if roughness is not None:
                bsdf.inputs["Roughness"].default_value = roughness

    return {
        "success": True,
        "result": f"已设置 {object_name} 的金属度/粗糙度",
        "error": None,
    }


def _get_object_info(name: str) -> dict:
    """获取物体信息"""
    if name not in bpy.data.objects:
        return {"success": False, "result": None, "error": f"找不到物体: {name}"}

    obj = bpy.data.objects[name]

    info = {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation_euler": [round(r, 4) for r in obj.rotation_euler],
        "scale": list(obj.scale),
        "materials": [mat.name for mat in obj.data.materials]
        if hasattr(obj.data, "materials")
        else [],
    }

    return {"success": True, "result": info, "error": None}


def execute_python_code(code: str) -> dict:
    try:
        exec_globals = {"bpy": bpy, "result": None}
        exec(code, exec_globals)

        result = exec_globals.get("result", "代码执行完成")
        return {"success": True, "result": result, "error": None}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def _analyze_scene(question: str) -> dict:
    from . import scene_utils
    
    image_data = scene_utils.capture_viewport_screenshot(1024, 768)
    if not image_data:
        return {"success": False, "result": None, "error": "无法截取视口画面"}
    
    scene_info = scene_utils.get_scene_info()
    
    return {
        "success": True,
        "result": "NEEDS_VISION_ANALYSIS",
        "image_data": image_data,
        "scene_info": scene_info,
        "question": question,
        "error": None,
    }


def _get_scene_info_full() -> dict:
    from . import scene_utils
    
    info = scene_utils.get_scene_info()
    return {"success": True, "result": info, "error": None}


def _setup_render(
    engine: str = None,
    resolution_x: int = None,
    resolution_y: int = None,
    samples: int = None,
    output_path: str = None,
    file_format: str = None,
    use_gpu: bool = None,
) -> dict:
    from . import scene_utils
    
    return scene_utils.setup_render_settings(
        engine=engine,
        resolution_x=resolution_x,
        resolution_y=resolution_y,
        samples=samples,
        output_path=output_path,
        file_format=file_format,
        use_gpu=use_gpu,
    )


def _render_image(output_path: str = None) -> dict:
    from . import scene_utils
    
    return scene_utils.render_image(output_path=output_path)
