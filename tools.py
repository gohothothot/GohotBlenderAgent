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
    # ----- 着色器节点操作 -----
    {
        "name": "shader_create_material",
        "description": "创建新材质。返回材质名称。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "材质名称"},
                "use_nodes": {"type": "boolean", "description": "是否使用节点（默认true）"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "shader_delete_material",
        "description": "删除指定材质",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "材质名称"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "shader_list_materials",
        "description": "列出场景中所有材质及其基本信息",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "shader_assign_material",
        "description": "将材质分配给物体",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "object_name": {"type": "string", "description": "物体名称"},
                "slot_index": {"type": "integer", "description": "材质槽索引（可选，默认添加新槽）"}
            },
            "required": ["material_name", "object_name"]
        }
    },
    {
        "name": "shader_inspect_nodes",
        "description": "查看材质的完整节点图结构，包括所有节点、连接、输入输出值",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"}
            },
            "required": ["material_name"]
        }
    },
    {
        "name": "shader_add_node",
        "description": "向材质添加着色器节点。常用类型：ShaderNodeBsdfPrincipled, ShaderNodeTexNoise, ShaderNodeTexVoronoi, ShaderNodeTexWave, ShaderNodeValToRGB(ColorRamp), ShaderNodeBump, ShaderNodeNormalMap, ShaderNodeMixShader, ShaderNodeMix, ShaderNodeMath, ShaderNodeMapping, ShaderNodeTexCoord, ShaderNodeSeparateXYZ, ShaderNodeCombineXYZ, ShaderNodeFresnel, ShaderNodeLayerWeight, ShaderNodeTexImage, ShaderNodeTexGradient, ShaderNodeTexChecker, ShaderNodeMapRange, ShaderNodeRGBCurves, ShaderNodeEmission, ShaderNodeBsdfGlass, ShaderNodeBsdfTransparent, ShaderNodeOutputMaterial",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_type": {"type": "string", "description": "节点类型（如 ShaderNodeTexNoise）"},
                "label": {"type": "string", "description": "节点标签（可选）"},
                "location": {"type": "array", "items": {"type": "number"}, "description": "节点位置 [x, y]（可选）"}
            },
            "required": ["material_name", "node_type"]
        }
    },
    {
        "name": "shader_delete_node",
        "description": "删除材质中的指定节点",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "节点名称"}
            },
            "required": ["material_name", "node_name"]
        }
    },
    {
        "name": "shader_set_node_input",
        "description": "设置节点输入值。值可以是数字（float）、颜色数组[r,g,b,a]、向量数组[x,y,z]",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "节点名称"},
                "input_name": {"type": "string", "description": "输入名称（如 Base Color, Scale, Roughness）"},
                "value": {"description": "输入值：数字、颜色[r,g,b,a]或向量[x,y,z]"}
            },
            "required": ["material_name", "node_name", "input_name", "value"]
        }
    },
    {
        "name": "shader_set_node_property",
        "description": "设置节点属性（如 blend_type, operation, distribution 等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "节点名称"},
                "property_name": {"type": "string", "description": "属性名称"},
                "value": {"description": "属性值"}
            },
            "required": ["material_name", "node_name", "property_name", "value"]
        }
    },
    {
        "name": "shader_link_nodes",
        "description": "连接两个节点。从 from_node 的 from_output 连接到 to_node 的 to_input",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "from_node": {"type": "string", "description": "源节点名称"},
                "from_output": {"type": "string", "description": "源节点输出名称（如 Color, Fac, BSDF）"},
                "to_node": {"type": "string", "description": "目标节点名称"},
                "to_input": {"type": "string", "description": "目标节点输入名称（如 Base Color, Surface）"}
            },
            "required": ["material_name", "from_node", "from_output", "to_node", "to_input"]
        }
    },
    {
        "name": "shader_unlink_nodes",
        "description": "断开两个节点之间的连接",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "from_node": {"type": "string", "description": "源节点名称"},
                "from_output": {"type": "string", "description": "源节点输出名称"},
                "to_node": {"type": "string", "description": "目标节点名称"},
                "to_input": {"type": "string", "description": "目标节点输入名称"}
            },
            "required": ["material_name", "from_node", "from_output", "to_node", "to_input"]
        }
    },
    {
        "name": "shader_colorramp_add_stop",
        "description": "向 ColorRamp 节点添加颜色停靠点",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "ColorRamp 节点名称"},
                "position": {"type": "number", "description": "位置 0.0-1.0"},
                "color": {"type": "array", "items": {"type": "number"}, "description": "颜色 [r, g, b, a]"}
            },
            "required": ["material_name", "node_name", "position", "color"]
        }
    },
    {
        "name": "shader_colorramp_remove_stop",
        "description": "移除 ColorRamp 节点的颜色停靠点",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "ColorRamp 节点名称"},
                "index": {"type": "integer", "description": "停靠点索引"}
            },
            "required": ["material_name", "node_name", "index"]
        }
    },
    {
        "name": "shader_colorramp_set_interpolation",
        "description": "设置 ColorRamp 节点的插值模式",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "ColorRamp 节点名称"},
                "interpolation": {"type": "string", "enum": ["LINEAR", "EASE", "CARDINAL", "B_SPLINE", "CONSTANT"], "description": "插值模式"}
            },
            "required": ["material_name", "node_name", "interpolation"]
        }
    },
    {
        "name": "shader_create_procedural_material",
        "description": "从预设创建完整的程序化材质。预设包括：wood(木纹), marble(大理石), metal_scratched(磨损金属), brick(砖块), fabric(布料), glass(玻璃), gold(黄金), rubber(橡胶), concrete(混凝土), plastic(塑料), water(水), ice(冰), lava(熔岩), crystal(水晶), snow(雪), leather(皮革), neon(霓虹), emissive(发光)",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "材质名称"},
                "preset": {"type": "string", "enum": ["wood", "marble", "metal_scratched", "brick", "fabric", "glass", "gold", "rubber", "concrete", "plastic", "water", "ice", "lava", "crystal", "snow", "leather", "neon", "emissive"], "description": "预设类型"}
            },
            "required": ["name", "preset"]
        }
    },
    {
        "name": "shader_preview_material",
        "description": "渲染材质预览球并返回图片",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "resolution": {"type": "integer", "description": "分辨率（默认256）"}
            },
            "required": ["material_name"]
        }
    },
    {
        "name": "shader_configure_eevee",
        "description": "为 EEVEE 配置透射材质的必要渲染设置（Screen Space Refraction等）。当透射材质（水、玻璃、冰等）在 EEVEE 中显示为黑色时使用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"}
            },
            "required": ["material_name"]
        }
    },
    {
        "name": "shader_create_toon_material",
        "description": "创建卡通/二次元渲染材质（NPR）。预设包括：toon_basic(基础卡通), toon_skin(皮肤), toon_hair(头发), toon_eye(眼睛), toon_cloth(布料), toon_metal(金属)。创建后会返回参数调整提示。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "材质名称"},
                "preset": {
                    "type": "string",
                    "enum": ["toon_basic", "toon_skin", "toon_hair", "toon_eye", "toon_cloth", "toon_metal"],
                    "description": "卡通预设类型"
                }
            },
            "required": ["name", "preset"]
        }
    },
    {
        "name": "shader_convert_to_toon",
        "description": "将现有PBR材质转换为卡通渲染风格，保留原有贴图。适用于MeshyAI生成的模型：导入后调用此工具将PBR材质转为二次元卡通风格。转换后会返回参数调整提示。",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "要转换的材质名称"},
                "keep_textures": {"type": "boolean", "description": "是否保留原有贴图（默认true）"}
            },
            "required": ["material_name"]
        }
    },
    {
        "name": "shader_list_available_nodes",
        "description": "列出所有可用的着色器节点类型，按类别分组（shader/texture/color/vector/converter/input/output/layout）。用于发现可用节点。",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "shader_get_node_sockets",
        "description": "获取指定节点的所有输入输出 socket 详细信息：类型、默认值、是否已连接、连接来源。创建节点后用此工具查看可用的 socket。",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "节点名称"}
            },
            "required": ["material_name", "node_name"]
        }
    },
    {
        "name": "shader_batch_add_nodes",
        "description": "批量添加节点（减少往返次数）。每项可指定 type/name/label/location/inputs/properties。",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "description": "节点类型（如 ShaderNodeBsdfPrincipled）"},
                            "name": {"type": "string", "description": "节点名称（可选）"},
                            "label": {"type": "string", "description": "节点标签（可选）"},
                            "location": {"type": "array", "items": {"type": "number"}, "description": "[x, y] 位置"},
                            "inputs": {"type": "object", "description": "输入值 {\"InputName\": value}"},
                            "properties": {"type": "object", "description": "节点属性 {\"prop\": value}"}
                        },
                        "required": ["type"]
                    },
                    "description": "要添加的节点列表"
                }
            },
            "required": ["material_name", "nodes"]
        }
    },
    {
        "name": "shader_batch_link_nodes",
        "description": "批量连接节点（减少往返次数）。每项指定 from_node/from_output/to_node/to_input。",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "links": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from_node": {"type": "string"},
                            "from_output": {"type": "string"},
                            "to_node": {"type": "string"},
                            "to_input": {"type": "string"}
                        },
                        "required": ["from_node", "from_output", "to_node", "to_input"]
                    },
                    "description": "要创建的连接列表"
                }
            },
            "required": ["material_name", "links"]
        }
    },
    {
        "name": "shader_clear_nodes",
        "description": "清除材质的所有节点。可选保留输出节点。用于重建材质前清理。",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "keep_output": {"type": "boolean", "description": "是否保留输出节点（默认true）"}
            },
            "required": ["material_name"]
        }
    },
    {
        "name": "shader_get_material_summary",
        "description": "获取材质完整摘要：节点数量、连接数量、使用的节点类型、Principled BSDF 关键参数、材质设置。用于检查和对比材质。",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"}
            },
            "required": ["material_name"]
        }
    },
    {
        "name": "anim_add_uv_scroll",
        "description": "为材质的 Mapping 节点添加 UV 滚动动画（基于 Driver，无需脚本）。可分别设置 X/Y/Z 轴的滚动速度。",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "Mapping 节点名称"},
                "speed_x": {"type": "number", "description": "X轴滚动速度（每帧偏移量，默认0）"},
                "speed_y": {"type": "number", "description": "Y轴滚动速度（每帧偏移量，默认0）"},
                "speed_z": {"type": "number", "description": "Z轴滚动速度（每帧偏移量，默认0）"}
            },
            "required": ["material_name", "node_name"]
        }
    },
    {
        "name": "anim_add_uv_rotate",
        "description": "为材质的 Mapping 节点添加 UV 旋转动画",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "Mapping 节点名称"},
                "speed": {"type": "number", "description": "旋转速度（弧度/帧，默认0.01）"},
                "axis": {"type": "string", "enum": ["X", "Y", "Z"], "description": "旋转轴（默认Z）"}
            },
            "required": ["material_name", "node_name"]
        }
    },
    {
        "name": "anim_add_uv_scale",
        "description": "为材质的 Mapping 节点添加 UV 缩放动画",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "Mapping 节点名称"},
                "speed_x": {"type": "number", "description": "X轴缩放速度（每帧变化量）"},
                "speed_y": {"type": "number", "description": "Y轴缩放速度"},
                "speed_z": {"type": "number", "description": "Z轴缩放速度"},
                "base_scale": {"type": "number", "description": "初始缩放值（默认1.0）"}
            },
            "required": ["material_name", "node_name"]
        }
    },
    {
        "name": "anim_add_value_driver",
        "description": "为任意节点输入添加 Driver 表达式动画。expression 中可用: frame(当前帧), sin, cos, abs, min, max, pow, sqrt。常用: 'frame*0.01'(线性), 'sin(frame*0.1)'(波动), '0.5+0.5*sin(frame*0.05)'(0~1波动)",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "节点名称"},
                "input_name": {"type": "string", "description": "输入名称"},
                "expression": {"type": "string", "description": "Driver 表达式"},
                "index": {"type": "integer", "description": "向量/颜色的分量索引（-1表示标量，默认-1）"}
            },
            "required": ["material_name", "node_name", "input_name", "expression"]
        }
    },
    {
        "name": "anim_add_keyframe",
        "description": "为节点输入在指定帧插入关键帧",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "节点名称"},
                "input_name": {"type": "string", "description": "输入名称"},
                "frame": {"type": "integer", "description": "帧号"},
                "value": {"description": "值（数字或数组）"},
                "index": {"type": "integer", "description": "向量分量索引（-1表示全部，默认-1）"}
            },
            "required": ["material_name", "node_name", "input_name", "frame", "value"]
        }
    },
    {
        "name": "anim_remove_driver",
        "description": "移除节点输入上的 Driver 动画",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_name": {"type": "string", "description": "材质名称"},
                "node_name": {"type": "string", "description": "节点名称"},
                "input_name": {"type": "string", "description": "输入名称"},
                "index": {"type": "integer", "description": "向量分量索引（-1表示全部，默认-1）"}
            },
            "required": ["material_name", "node_name", "input_name"]
        }
    },
    {
        "name": "web_search",
        "description": "搜索网络获取参考资料。在制作复杂 shader、不确定参数、或需要参考时使用。搜索 Blender 教程、shader 技巧、材质参数等。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词（建议用英文搜索效果更好）"},
                "max_results": {"type": "integer", "description": "最大结果数（默认5）"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "web_fetch",
        "description": "智能抓取网页内容。自动识别 bilibili/YouTube/普通网页，提取标题、描述、关键词等结构化信息。",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "网页 URL"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "web_search_blender",
        "description": "Blender 专题搜索 - 自动组合多个搜索词搜索 Blender 教程、shader 节点设置、程序化材质等",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "搜索主题（如 water, glass, ice, toon shading）"}
            },
            "required": ["topic"]
        }
    },
    {
        "name": "web_analyze_reference",
        "description": "分析参考链接，提取 Blender 材质/着色器相关信息：检测涉及的节点类型、材质类型、渲染引擎、关键参数（IOR/粗糙度等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "参考链接 URL"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "scene_add_light",
        "description": "添加灯光。类型：POINT(点光), SUN(太阳光), SPOT(聚光灯), AREA(面光)",
        "input_schema": {
            "type": "object",
            "properties": {
                "light_type": {"type": "string", "enum": ["POINT", "SUN", "SPOT", "AREA"], "description": "灯光类型"},
                "location": {"type": "array", "items": {"type": "number"}, "description": "位置 [x,y,z]"},
                "energy": {"type": "number", "description": "能量（默认1000）"},
                "color": {"type": "array", "items": {"type": "number"}, "description": "颜色 [r,g,b]"},
                "name": {"type": "string", "description": "名称"}
            },
            "required": []
        }
    },
    {
        "name": "scene_modify_light",
        "description": "修改灯光参数",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "灯光物体名称"},
                "energy": {"type": "number", "description": "能量"},
                "color": {"type": "array", "items": {"type": "number"}, "description": "颜色 [r,g,b]"},
                "spot_size": {"type": "number", "description": "聚光灯锥角（度）"},
                "spot_blend": {"type": "number", "description": "聚光灯柔和度 0-1"},
                "shadow_soft_size": {"type": "number", "description": "阴影柔和度"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "scene_add_camera",
        "description": "添加相机",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "array", "items": {"type": "number"}, "description": "位置 [x,y,z]"},
                "rotation": {"type": "array", "items": {"type": "number"}, "description": "旋转角度 [x,y,z]"},
                "lens": {"type": "number", "description": "焦距mm（默认50）"},
                "name": {"type": "string", "description": "名称"}
            },
            "required": []
        }
    },
    {
        "name": "scene_set_active_camera",
        "description": "设置活动相机",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "相机名称"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "scene_add_modifier",
        "description": "为物体添加修改器。类型：SUBSURF, MIRROR, ARRAY, BEVEL, SOLIDIFY, BOOLEAN, DECIMATE, SMOOTH, WIREFRAME, DISPLACE, SIMPLE_DEFORM, CURVE, ARMATURE",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "物体名称"},
                "modifier_type": {"type": "string", "description": "修改器类型"},
                "name": {"type": "string", "description": "修改器名称"}
            },
            "required": ["object_name", "modifier_type"]
        }
    },
    {
        "name": "scene_set_modifier_param",
        "description": "设置修改器参数。如 levels=2, offset=1.0, count=3 等",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "物体名称"},
                "modifier_name": {"type": "string", "description": "修改器名称"},
                "param_name": {"type": "string", "description": "参数名"},
                "value": {"description": "参数值"}
            },
            "required": ["object_name", "modifier_name", "param_name", "value"]
        }
    },
    {
        "name": "scene_remove_modifier",
        "description": "移除修改器",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "物体名称"},
                "modifier_name": {"type": "string", "description": "修改器名称"}
            },
            "required": ["object_name", "modifier_name"]
        }
    },
    {
        "name": "scene_manage_collection",
        "description": "管理集合。action: create(创建), delete(删除), move_object(移动物体到集合), list(列出所有集合)",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "delete", "move_object", "list"], "description": "操作"},
                "collection_name": {"type": "string", "description": "集合名称"},
                "object_name": {"type": "string", "description": "物体名称（move_object时需要）"},
                "parent_name": {"type": "string", "description": "父集合名称（create时可选）"}
            },
            "required": ["action", "collection_name"]
        }
    },
    {
        "name": "scene_set_world",
        "description": "设置世界环境（背景颜色或HDRI）",
        "input_schema": {
            "type": "object",
            "properties": {
                "color": {"type": "array", "items": {"type": "number"}, "description": "背景颜色 [r,g,b]"},
                "strength": {"type": "number", "description": "强度（默认1.0）"},
                "use_hdri": {"type": "boolean", "description": "是否使用HDRI"},
                "hdri_path": {"type": "string", "description": "HDRI文件路径"}
            },
            "required": []
        }
    },
    {
        "name": "scene_duplicate_object",
        "description": "复制物体",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "源物体名称"},
                "linked": {"type": "boolean", "description": "是否关联复制（默认false）"},
                "new_name": {"type": "string", "description": "新名称"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "scene_parent_object",
        "description": "设置父子关系",
        "input_schema": {
            "type": "object",
            "properties": {
                "child_name": {"type": "string", "description": "子物体名称"},
                "parent_name": {"type": "string", "description": "父物体名称"}
            },
            "required": ["child_name", "parent_name"]
        }
    },
    {
        "name": "scene_set_visibility",
        "description": "设置物体可见性",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "物体名称"},
                "visible": {"type": "boolean", "description": "视口可见"},
                "render_visible": {"type": "boolean", "description": "渲染可见"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "scene_get_render_settings",
        "description": "获取当前渲染设置：引擎、分辨率、EEVEE/Cycles参数、色彩管理等。用于检查当前渲染配置。",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "scene_set_render_settings",
        "description": "设置渲染参数：引擎(EEVEE/CYCLES/WORKBENCH)、分辨率、采样数、SSR、透明胶片、视图变换等。",
        "input_schema": {
            "type": "object",
            "properties": {
                "engine": {"type": "string", "description": "渲染引擎: EEVEE/CYCLES/WORKBENCH"},
                "resolution": {"type": "array", "items": {"type": "number"}, "description": "[宽, 高]"},
                "samples": {"type": "integer", "description": "采样数"},
                "use_ssr": {"type": "boolean", "description": "启用屏幕空间反射"},
                "use_ssr_refraction": {"type": "boolean", "description": "启用SSR折射"},
                "film_transparent": {"type": "boolean", "description": "透明背景"},
                "view_transform": {"type": "string", "description": "视图变换(如 Filmic, Standard)"}
            },
            "required": []
        }
    },
    {
        "name": "scene_get_object_materials",
        "description": "获取物体的所有材质详细信息：主着色器类型、关键参数值（Base Color/Metallic/Roughness/IOR/Transmission等）、材质设置。",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "物体名称"}
            },
            "required": ["object_name"]
        }
    },
    {
        "name": "scene_get_world_info",
        "description": "获取世界环境设置：背景颜色/强度、是否使用HDRI等。",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "scene_list_all_materials",
        "description": "列出场景中所有材质及其使用情况：哪些物体在用、节点数量等。",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "kb_search",
        "description": "搜索本地知识库。在 web_search 之前先查本地知识库，避免重复搜索。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "kb_save",
        "description": "保存知识到本地知识库（如成功的shader配方、有用的参考资料）",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "知识条目名称"},
                "description": {"type": "string", "description": "详细描述"},
                "tags": {"type": "string", "description": "标签，逗号分隔"}
            },
            "required": ["name", "description"]
        }
    },
    {
        "name": "get_action_log",
        "description": "获取最近的操作日志，用于回顾之前的操作和结果",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "获取最近几条日志（默认5）"}
            },
            "required": []
        }
    },
    {
        "name": "get_todo_list",
        "description": "获取当前 TODO 列表，包括用户待办和 Agent 待办。Agent 应主动读取并帮助完成标记为 Agent 类型的待办事项。",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "complete_todo",
        "description": "将指定索引的 TODO 标记为已完成",
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "TODO 项的索引（从0开始）"}
            },
            "required": ["index"]
        }
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
        elif tool_name == "get_todo_list":
            return _get_todo_list()
        elif tool_name == "complete_todo":
            return _complete_todo(**arguments)
        elif tool_name.startswith("anim_"):
            from . import animation_tools
            return animation_tools.execute_anim_tool(tool_name, arguments)
        elif tool_name in ("web_search", "web_fetch", "web_search_blender", "web_analyze_reference"):
            from . import web_search
            return web_search.execute_web_tool(tool_name, arguments)
        elif tool_name in ("kb_search", "kb_save"):
            from . import knowledge_base
            return knowledge_base.execute_kb_tool(tool_name, arguments)
        elif tool_name == "get_action_log":
            from . import action_log
            count = arguments.get("count", 5)
            logs = action_log.get_recent_logs(count)
            if not logs:
                return {"success": True, "result": "暂无操作日志", "error": None}
            summaries = []
            for log in logs:
                s = f"[{log.get('session_id', '?')}] {log.get('user_request', '')[:60]} → {len(log.get('actions', []))} 步操作"
                if log.get('final_result'):
                    s += f" → {log['final_result'][:60]}"
                summaries.append(s)
            return {"success": True, "result": "\n".join(summaries), "error": None}
        elif tool_name.startswith("scene_"):
            from . import scene_tools
            return scene_tools.execute_scene_tool(tool_name, arguments)
        elif tool_name in ("shader_create_toon_material", "shader_convert_to_toon"):
            from . import toon_tools
            return toon_tools.execute_toon_tool(tool_name, arguments)
        elif tool_name.startswith("shader_"):
            from . import shader_tools
            func = getattr(shader_tools, tool_name, None)
            if func:
                return func(**arguments)
            else:
                return {"success": False, "result": None, "error": f"未知着色器工具: {tool_name}"}
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


def _get_todo_list() -> dict:
    try:
        state = bpy.context.scene.blender_agent
        todos = []
        for i, item in enumerate(state.todos):
            todos.append({
                "index": i,
                "content": item.content,
                "type": item.todo_type,
                "done": item.done,
            })
        return {"success": True, "result": todos, "error": None}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def _complete_todo(index: int) -> dict:
    try:
        state = bpy.context.scene.blender_agent
        if 0 <= index < len(state.todos):
            state.todos[index].done = True
            content = state.todos[index].content
            return {"success": True, "result": f"已完成: {content}", "error": None}
        return {"success": False, "result": None, "error": f"无效索引: {index}"}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}
