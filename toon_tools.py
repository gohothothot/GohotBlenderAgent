"""
Toon/NPR Shader Tools - 二次元卡通渲染着色器工具

让 LLM 能够创建和转换卡通渲染材质，支持：
- 卡通漫反射 (Diffuse Ramp)
- 边缘光 (Rim Light)
- 卡通高光 (Toon Specular)
- 从 PBR 材质转换为卡通风格（保留贴图）
"""

import bpy
from typing import Any, List, Optional
from .shader_tools import _result, _get_material, _get_node_by_type


# ========== Toon Preset Configs ==========

TOON_PRESETS = {
    "toon_basic": {
        "base_color": (0.9, 0.9, 0.9, 1),
        "shadow_color": (0.15, 0.1, 0.2, 1),
        "mid_color": (0.5, 0.45, 0.55, 1),
        "lit_color": (1.0, 1.0, 1.0, 1),
        "shadow_pos": 0.35,
        "mid_pos": 0.55,
        "rim_color": (0.8, 0.85, 1.0, 1),
        "rim_threshold": 0.6,
        "rim_strength": 0.3,
        "spec_threshold": 0.88,
        "spec_strength": 0.2,
        "spec_color": (1.0, 1.0, 1.0, 1),
        "tips": (
            "参数调整提示:\n"
            "- 漫反射Ramp(Diffuse Ramp): 调整色标位置控制阴影边界锐度\n"
            "- 边缘光Ramp(Rim Ramp): 调整阈值控制边缘光宽度\n"
            "- 高光Ramp(Spec Ramp): 调整阈值控制高光大小\n"
            "- 阴影颜色: 修改Diffuse Ramp第一个色标颜色"
        ),
    },
    "toon_skin": {
        "base_color": (1.0, 0.85, 0.75, 1),
        "shadow_color": (0.45, 0.2, 0.18, 1),
        "mid_color": (0.75, 0.55, 0.48, 1),
        "lit_color": (1.0, 0.9, 0.85, 1),
        "shadow_pos": 0.3,
        "mid_pos": 0.5,
        "rim_color": (1.0, 0.8, 0.7, 1),
        "rim_threshold": 0.65,
        "rim_strength": 0.15,
        "spec_threshold": 0.95,
        "spec_strength": 0.05,
        "spec_color": (1.0, 0.95, 0.9, 1),
        "tips": (
            "参数调整提示:\n"
            "- 阴影颜色偏暖红: 修改Diffuse Ramp第一个色标\n"
            "- 皮肤过渡: 调整shadow_pos(0.3)让阴影更柔和\n"
            "- 边缘光较弱: 可增大Rim Strength节点的Factor值\n"
            "- 几乎无高光: 适合皮肤的哑光质感"
        ),
    },
    "toon_hair": {
        "base_color": (0.15, 0.1, 0.2, 1),
        "shadow_color": (0.05, 0.03, 0.08, 1),
        "mid_color": (0.12, 0.08, 0.18, 1),
        "lit_color": (0.9, 0.85, 1.0, 1),
        "shadow_pos": 0.4,
        "mid_pos": 0.6,
        "rim_color": (0.7, 0.6, 1.0, 1),
        "rim_threshold": 0.55,
        "rim_strength": 0.4,
        "spec_threshold": 0.75,
        "spec_strength": 0.35,
        "spec_color": (0.9, 0.85, 1.0, 1),
        "tips": (
            "参数调整提示:\n"
            "- 头发高光带: 调整Spec Ramp阈值(0.75)控制高光位置\n"
            "- 高光颜色: 修改Spec Color节点匹配发色\n"
            "- 边缘光较强: 营造头发轮廓感\n"
            "- Base Color: 修改BSDF的Base Color改变发色"
        ),
    },
    "toon_eye": {
        "base_color": (0.2, 0.4, 0.8, 1),
        "shadow_color": (0.05, 0.1, 0.3, 1),
        "mid_color": (0.15, 0.3, 0.6, 1),
        "lit_color": (0.8, 0.9, 1.0, 1),
        "shadow_pos": 0.3,
        "mid_pos": 0.5,
        "rim_color": (0.6, 0.7, 1.0, 1),
        "rim_threshold": 0.7,
        "rim_strength": 0.15,
        "spec_threshold": 0.7,
        "spec_strength": 0.5,
        "spec_color": (1.0, 1.0, 1.0, 1),
        "tips": (
            "参数调整提示:\n"
            "- 眼睛高光: Spec Ramp阈值较低(0.7)产生大高光\n"
            "- 高光强度: 增大Spec Strength让眼睛更有神\n"
            "- 虹膜颜色: 修改Base Color改变眼睛颜色\n"
            "- 建议配合眼睛贴图使用convert_to_toon"
        ),
    },
    "toon_cloth": {
        "base_color": (0.6, 0.6, 0.65, 1),
        "shadow_color": (0.2, 0.18, 0.25, 1),
        "mid_color": (0.4, 0.38, 0.45, 1),
        "lit_color": (0.85, 0.85, 0.9, 1),
        "shadow_pos": 0.32,
        "mid_pos": 0.52,
        "rim_color": (0.7, 0.7, 0.8, 1),
        "rim_threshold": 0.65,
        "rim_strength": 0.12,
        "spec_threshold": 0.95,
        "spec_strength": 0.03,
        "spec_color": (0.9, 0.9, 0.95, 1),
        "tips": (
            "参数调整提示:\n"
            "- 布料阴影柔和: shadow_pos较低(0.32)\n"
            "- 几乎无高光: 布料哑光质感\n"
            "- 边缘光微弱: 保持布料自然感\n"
            "- Base Color: 修改BSDF颜色改变布料颜色"
        ),
    },
    "toon_metal": {
        "base_color": (0.7, 0.7, 0.75, 1),
        "shadow_color": (0.1, 0.1, 0.15, 1),
        "mid_color": (0.35, 0.35, 0.45, 1),
        "lit_color": (1.0, 1.0, 1.0, 1),
        "shadow_pos": 0.4,
        "mid_pos": 0.6,
        "rim_color": (0.9, 0.9, 1.0, 1),
        "rim_threshold": 0.5,
        "rim_strength": 0.5,
        "spec_threshold": 0.7,
        "spec_strength": 0.6,
        "spec_color": (1.0, 1.0, 1.0, 1),
        "tips": (
            "参数调整提示:\n"
            "- 金属高光强: Spec Strength=0.6, 阈值较低\n"
            "- 强边缘光: Rim Strength=0.5营造金属反射感\n"
            "- 阴影对比强: shadow_pos=0.4产生锐利阴影\n"
            "- 可调整Base Color为金色/铜色等"
        ),
    },
}


# ========== Core Toon Builder ==========

def _build_toon_core(nodes, links, output, base_color_source=None, config=None):
    """
    构建卡通渲染核心节点图

    Args:
        nodes: material.node_tree.nodes
        links: material.node_tree.links
        output: Material Output node
        base_color_source: 可选的纹理节点输出socket，用于与toon ramp相乘
        config: 预设配置字典

    Returns:
        dict: 关键节点引用
    """
    if config is None:
        config = TOON_PRESETS["toon_basic"]

    # --- Principled BSDF (用于捕获光照信息) ---
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.label = "Toon BSDF"
    bsdf.location = (-600, 300)
    bsdf.inputs['Roughness'].default_value = 1.0
    bsdf.inputs['Metallic'].default_value = 0.0
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.0
    elif 'Specular' in bsdf.inputs:
        bsdf.inputs['Specular'].default_value = 0.0
    bsdf.inputs['Base Color'].default_value = config["base_color"]

    # 如果有纹理源，连接到BSDF的Base Color
    if base_color_source is not None:
        links.new(base_color_source, bsdf.inputs['Base Color'])

    # --- Shader to RGB (核心：将光照转为颜色数据) ---
    shader2rgb = nodes.new('ShaderNodeShaderToRGB')
    shader2rgb.label = "Shader To RGB"
    shader2rgb.location = (-400, 300)
    links.new(bsdf.outputs['BSDF'], shader2rgb.inputs['Shader'])

    # --- Diffuse Ramp (卡通漫反射色阶) ---
    diff_ramp = nodes.new('ShaderNodeValToRGB')
    diff_ramp.label = "Diffuse Ramp"
    diff_ramp.location = (-200, 300)
    diff_ramp.color_ramp.interpolation = 'CONSTANT'

    els = diff_ramp.color_ramp.elements
    els[0].position = 0.0
    els[0].color = config["shadow_color"]
    els[1].position = config["shadow_pos"]
    els[1].color = config["mid_color"]
    e_lit = diff_ramp.color_ramp.elements.new(config["mid_pos"])
    e_lit.color = config["lit_color"]

    links.new(shader2rgb.outputs['Color'], diff_ramp.inputs['Fac'])

    # --- 确定漫反射输出 ---
    # 如果有纹理源，将toon ramp与纹理相乘
    if base_color_source is not None:
        tex_multiply = nodes.new('ShaderNodeMix')
        tex_multiply.label = "Tex x Toon"
        tex_multiply.location = (0, 300)
        tex_multiply.data_type = 'RGBA'
        tex_multiply.blend_type = 'MULTIPLY'
        tex_multiply.inputs[0].default_value = 1.0  # Factor
        links.new(diff_ramp.outputs['Color'], tex_multiply.inputs[6])  # A
        links.new(base_color_source, tex_multiply.inputs[7])  # B
        diffuse_output = tex_multiply.outputs[2]  # Result
    else:
        diffuse_output = diff_ramp.outputs['Color']
        tex_multiply = None

    # --- Rim Light (边缘光) ---
    layer_weight = nodes.new('ShaderNodeLayerWeight')
    layer_weight.label = "Rim Detect"
    layer_weight.location = (-400, -100)
    layer_weight.inputs['Blend'].default_value = 0.5

    rim_ramp = nodes.new('ShaderNodeValToRGB')
    rim_ramp.label = "Rim Ramp"
    rim_ramp.location = (-200, -100)
    rim_ramp.color_ramp.interpolation = 'CONSTANT'
    rim_ramp.color_ramp.elements[0].position = 0.0
    rim_ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    rim_ramp.color_ramp.elements[1].position = config["rim_threshold"]
    rim_ramp.color_ramp.elements[1].color = config["rim_color"]

    links.new(layer_weight.outputs['Fresnel'], rim_ramp.inputs['Fac'])

    # Rim Strength (控制边缘光强度)
    rim_mix = nodes.new('ShaderNodeMix')
    rim_mix.label = "Rim Strength"
    rim_mix.location = (0, -100)
    rim_mix.data_type = 'RGBA'
    rim_mix.blend_type = 'ADD'
    rim_mix.inputs[0].default_value = config["rim_strength"]
    links.new(diffuse_output, rim_mix.inputs[6])  # A
    links.new(rim_ramp.outputs['Color'], rim_mix.inputs[7])  # B

    # --- Toon Specular (卡通高光) ---
    fresnel = nodes.new('ShaderNodeFresnel')
    fresnel.label = "Spec Fresnel"
    fresnel.location = (-400, -400)
    fresnel.inputs['IOR'].default_value = 1.5

    spec_ramp = nodes.new('ShaderNodeValToRGB')
    spec_ramp.label = "Spec Ramp"
    spec_ramp.location = (-200, -400)
    spec_ramp.color_ramp.interpolation = 'CONSTANT'
    spec_ramp.color_ramp.elements[0].position = 0.0
    spec_ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    spec_ramp.color_ramp.elements[1].position = config["spec_threshold"]
    spec_ramp.color_ramp.elements[1].color = config["spec_color"]

    links.new(fresnel.outputs['Fac'], spec_ramp.inputs['Fac'])

    # Spec Strength
    spec_mix = nodes.new('ShaderNodeMix')
    spec_mix.label = "Spec Strength"
    spec_mix.location = (200, -200)
    spec_mix.data_type = 'RGBA'
    spec_mix.blend_type = 'ADD'
    spec_mix.inputs[0].default_value = config["spec_strength"]
    links.new(rim_mix.outputs[2], spec_mix.inputs[6])  # A (diffuse + rim)
    links.new(spec_ramp.outputs['Color'], spec_mix.inputs[7])  # B

    # --- Emission Output (绕过PBR重新光照) ---
    emission = nodes.new('ShaderNodeEmission')
    emission.label = "Toon Output"
    emission.location = (400, 0)
    emission.inputs['Strength'].default_value = 1.0
    links.new(spec_mix.outputs[2], emission.inputs['Color'])

    # 连接到输出
    output.location = (600, 0)
    links.new(emission.outputs['Emission'], output.inputs['Surface'])

    return {
        "bsdf": bsdf,
        "shader2rgb": shader2rgb,
        "diff_ramp": diff_ramp,
        "tex_multiply": tex_multiply,
        "layer_weight": layer_weight,
        "rim_ramp": rim_ramp,
        "rim_mix": rim_mix,
        "fresnel": fresnel,
        "spec_ramp": spec_ramp,
        "spec_mix": spec_mix,
        "emission": emission,
    }


# ========== Toon Material Creation ==========

def shader_create_toon_material(name: str, preset: str = "toon_basic") -> dict:
    """从预设创建卡通渲染材质"""
    try:
        preset = preset.lower()
        if preset not in TOON_PRESETS:
            valid = ", ".join(TOON_PRESETS.keys())
            return _result(False, None, f"未知预设: {preset}。可用: {valid}")

        if name in bpy.data.materials:
            return _result(False, None, f"材质已存在: {name}")

        config = TOON_PRESETS[preset]

        # 创建材质
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        # 创建输出节点
        output = nodes.new('ShaderNodeOutputMaterial')

        # 构建卡通核心
        _build_toon_core(nodes, links, output, config=config)

        tips = config["tips"]
        msg = f"已创建卡通材质: {name} ({preset})\n\n{tips}"
        return _result(True, msg)

    except Exception as e:
        return _result(False, None, str(e))


# ========== PBR to Toon Conversion ==========

def shader_convert_to_toon(material_name: str, keep_textures: bool = True) -> dict:
    """
    将现有PBR材质转换为卡通渲染风格（保留贴图）

    这是 MeshyAI 工作流的关键函数：
    导入模型后，调用此函数将PBR材质转为二次元卡通风格
    """
    try:
        mat = _get_material(material_name)

        if not mat.use_nodes:
            return _result(False, None, f"材质 {material_name} 未使用节点")

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # 查找现有的纹理节点和BSDF
        texture_nodes = []
        base_color_tex = None

        # 找到 Principled BSDF 和它的 Base Color 输入
        bsdf = _get_node_by_type(mat, 'BSDF_PRINCIPLED')
        if bsdf:
            base_input = bsdf.inputs.get('Base Color')
            if base_input and base_input.links:
                from_node = base_input.links[0].from_node
                if from_node.type == 'TEX_IMAGE':
                    base_color_tex = from_node

        # 收集所有纹理节点（如果保留贴图）
        if keep_textures:
            for node in nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    texture_nodes.append(node)

        # 清除非纹理节点
        nodes_to_remove = []
        for node in nodes:
            if keep_textures and node in texture_nodes:
                continue
            nodes_to_remove.append(node)

        for node in nodes_to_remove:
            nodes.remove(node)

        # 创建输出节点
        output = nodes.new('ShaderNodeOutputMaterial')

        # 确定纹理源
        tex_source = None
        if base_color_tex and base_color_tex.name in nodes:
            base_color_tex.location = (-800, 300)
            tex_source = base_color_tex.outputs['Color']

        # 使用 toon_basic 配置构建卡通核心
        config = TOON_PRESETS["toon_basic"]
        _build_toon_core(nodes, links, output,
                         base_color_source=tex_source,
                         config=config)

        tips = (
            "PBR转卡通完成！参数调整提示:\n"
            "- 贴图已保留并与卡通Ramp相乘\n"
            "- Diffuse Ramp: 调整色标位置控制阴影锐度\n"
            "- Rim Ramp: 调整阈值控制边缘光宽度\n"
            "- Spec Ramp: 调整阈值控制高光大小\n"
            "- 阴影颜色: 修改Diffuse Ramp第一个色标\n"
            "- 如需更暖的阴影，将阴影色标改为偏红棕色"
        )

        tex_info = ""
        if base_color_tex:
            tex_info = f"（已保留贴图: {base_color_tex.image.name}）"

        msg = f"已将 {material_name} 转换为卡通风格{tex_info}\n\n{tips}"
        return _result(True, msg)

    except Exception as e:
        return _result(False, None, str(e))


# ========== Tool Router ==========

def execute_toon_tool(tool_name: str, arguments: dict) -> dict:
    """执行卡通渲染工具"""
    try:
        if tool_name == "shader_create_toon_material":
            return shader_create_toon_material(**arguments)
        elif tool_name == "shader_convert_to_toon":
            return shader_convert_to_toon(**arguments)
        else:
            return _result(False, None, f"未知卡通工具: {tool_name}")
    except Exception as e:
        return _result(False, None, str(e))
