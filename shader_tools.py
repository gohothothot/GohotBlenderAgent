"""
Shader Node Manipulation Tools - 着色器节点操作工具

让 LLM 能够逐步构建复杂的程序化材质
"""

import bpy
import base64
import io
from typing import Any, List, Tuple, Union, Optional

# ========== Helper Functions ==========

def _result(success: bool, result: Any = None, error: str = None) -> dict:
    """标准结果格式"""
    return {"success": success, "result": result, "error": error}


def _get_material(name: str):
    """获取材质或抛出异常"""
    if name not in bpy.data.materials:
        raise ValueError(f"Material not found: {name}")
    return bpy.data.materials[name]


def _get_node(material, node_name: str):
    """获取节点或抛出异常"""
    node = material.node_tree.nodes.get(node_name)
    if node is None:
        raise ValueError(f"Node not found in material {material.name}: {node_name}")
    return node


def _get_node_by_type(material, node_type: str):
    """按类型查找节点"""
    for node in material.node_tree.nodes:
        if node.type == node_type:
            return node
    return None


def _get_output_node(material):
    """获取材质输出节点"""
    for node in material.node_tree.nodes:
        if node.type == 'OUTPUT_MATERIAL':
            return node
    return None


def _set_transmission(bsdf, value=1.0):
    """兼容不同 Blender 版本设置透射"""
    if 'Transmission Weight' in bsdf.inputs:
        bsdf.inputs['Transmission Weight'].default_value = value
    elif 'Transmission' in bsdf.inputs:
        bsdf.inputs['Transmission'].default_value = value


def _set_sss(bsdf, weight=0.0, radius=None, scale=1.0):
    """兼容不同 Blender 版本设置次表面散射"""
    if 'Subsurface Weight' in bsdf.inputs:
        bsdf.inputs['Subsurface Weight'].default_value = weight
    elif 'Subsurface' in bsdf.inputs:
        bsdf.inputs['Subsurface'].default_value = weight
    if radius and 'Subsurface Radius' in bsdf.inputs:
        bsdf.inputs['Subsurface Radius'].default_value = radius
    if 'Subsurface Scale' in bsdf.inputs:
        bsdf.inputs['Subsurface Scale'].default_value = scale


def _configure_eevee_transparency(mat):
    """为 EEVEE 配置透射/折射材质的必要设置

    EEVEE 中 Transmission 材质需要:
    1. 材质 blend_method = HASHED 或 BLEND
    2. 材质 use_screen_refraction = True
    3. 渲染设置 use_ssr = True, use_ssr_refraction = True
    不设置这些会导致透射材质显示为黑色/不透明
    """
    try:
        if hasattr(mat, 'blend_method'):
            mat.blend_method = 'HASHED'
        if hasattr(mat, 'use_screen_refraction'):
            mat.use_screen_refraction = True
        if hasattr(mat, 'refraction_depth'):
            mat.refraction_depth = 0.01

        scene = bpy.context.scene
        if hasattr(scene, 'eevee'):
            scene.eevee.use_ssr = True
            scene.eevee.use_ssr_refraction = True
    except Exception:
        pass


# ========== Material CRUD ==========

def shader_create_material(name: str, use_nodes: bool = True) -> dict:
    """创建新材质"""
    try:
        if name in bpy.data.materials:
            return _result(False, None, f"Material already exists: {name}")
        
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = use_nodes
        
        # 如果使用节点，创建默认的 BSDF
        if use_nodes:
            nodes = mat.node_tree.nodes
            nodes.clear()
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            output = nodes.new('ShaderNodeOutputMaterial')
            output.location = (300, 0)
            mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        
        return _result(True, f"Created material: {name}")
    except Exception as e:
        return _result(False, None, str(e))


def shader_delete_material(name: str) -> dict:
    """删除材质"""
    try:
        if name not in bpy.data.materials:
            return _result(False, None, f"Material not found: {name}")
        
        mat = bpy.data.materials[name]
        bpy.data.materials.remove(mat)
        return _result(True, f"Deleted material: {name}")
    except Exception as e:
        return _result(False, None, str(e))


def shader_list_materials() -> dict:
    """列出所有材质"""
    try:
        materials = []
        for mat in bpy.data.materials:
            info = {
                "name": mat.name,
                "use_nodes": mat.use_nodes,
                "node_count": len(mat.node_tree.nodes) if mat.use_nodes else 0,
            }
            materials.append(info)
        return _result(True, materials)
    except Exception as e:
        return _result(False, None, str(e))


def shader_assign_material(material_name: str, object_name: str, slot_index: int = None) -> dict:
    """为物体指定材质"""
    try:
        if material_name not in bpy.data.materials:
            return _result(False, None, f"Material not found: {material_name}")
        
        if object_name not in bpy.data.objects:
            return _result(False, None, f"Object not found: {object_name}")
        
        obj = bpy.data.objects[object_name]
        mat = bpy.data.materials[material_name]
        
        # 确保物体有 material_slots
        if not hasattr(obj.data, 'materials'):
            return _result(False, None, f"Object {object_name} doesn't support materials")
        
        if slot_index is not None:
            # 指定槽位
            if slot_index >= len(obj.data.materials):
                # 扩展槽位
                for _ in range(len(obj.data.materials), slot_index + 1):
                    obj.data.materials.append(None)
            obj.data.materials[slot_index] = mat
        else:
            # 默认添加到第一个空槽位或追加
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)
        
        return _result(True, f"Assigned material {material_name} to {object_name}")
    except Exception as e:
        return _result(False, None, str(e))


# ========== Node Graph Inspection ==========

def _collect_node_detail(node, include_values: bool = False) -> dict:
    """按需收集节点信息，避免无意义的大 payload"""
    if include_values:
        inputs = []
        outputs = []
        for inp in node.inputs:
            inp_info = {
                "name": inp.name,
                "type": str(inp.type),
                "default_value": _serialize_socket_value(inp.default_value),
                "linked": len(inp.links) > 0,
            }
            inputs.append(inp_info)
        for out in node.outputs:
            out_info = {
                "name": out.name,
                "type": str(out.type),
                "linked": len(out.links) > 0,
            }
            outputs.append(out_info)
        return {
            "name": node.name,
            "type": node.type,
            "label": node.label,
            "location": list(node.location),
            "inputs": inputs,
            "outputs": outputs,
        }

    linked_inputs = sum(1 for inp in node.inputs if len(inp.links) > 0)
    linked_outputs = sum(1 for out in node.outputs if len(out.links) > 0)
    return {
        "name": node.name,
        "type": node.type,
        "label": node.label,
        "location": [round(node.location.x, 2), round(node.location.y, 2)],
        "input_count": len(node.inputs),
        "output_count": len(node.outputs),
        "linked_inputs": linked_inputs,
        "linked_outputs": linked_outputs,
    }


def shader_inspect_nodes(
    material_name: str,
    node_names: Optional[List[str]] = None,
    query: str = "",
    include_values: bool = False,
    include_links: bool = True,
    limit: int = 30,
    offset: int = 0,
    compact: bool = True,
) -> dict:
    """分页查看节点图结构，默认返回轻量摘要以减少 token 使用"""
    try:
        mat = _get_material(material_name)

        if not mat.use_nodes:
            return _result(False, None, "Material does not use nodes")

        all_nodes = list(mat.node_tree.nodes)
        if node_names:
            wanted = set(node_names)
            all_nodes = [n for n in all_nodes if n.name in wanted]

        total_nodes = len(all_nodes)
        safe_limit = max(1, min(int(limit or 30), 200))
        safe_offset = max(0, int(offset or 0))
        page_nodes = all_nodes[safe_offset:safe_offset + safe_limit]
        page_names = {n.name for n in page_nodes}

        nodes_info = [_collect_node_detail(n, include_values=(include_values and not compact)) for n in page_nodes]

        links_info = []
        if include_links:
            for link in mat.node_tree.links:
                # 只返回当前页相关连接，防止连接信息膨胀
                if link.from_node.name in page_names or link.to_node.name in page_names:
                    links_info.append({
                        "from_node": link.from_node.name,
                        "from_socket": link.from_socket.name,
                        "to_node": link.to_node.name,
                        "to_socket": link.to_socket.name,
                    })

        node_types = {}
        for node in all_nodes:
            node_types[node.bl_idname] = node_types.get(node.bl_idname, 0) + 1
        top_types = sorted(node_types.items(), key=lambda x: x[1], reverse=True)[:12]

        payload = {
            "material_name": material_name,
            "graph_summary": {
                "total_nodes": total_nodes,
                "total_links": len(mat.node_tree.links),
                "node_type_top": [{"type": t, "count": c} for t, c in top_types],
            },
            "page": {
                "offset": safe_offset,
                "limit": safe_limit,
                "returned": len(nodes_info),
                "has_more": safe_offset + safe_limit < total_nodes,
            },
            "nodes": nodes_info,
            "links": links_info if include_links else [],
        }
        try:
            from .context.indexer import get_graph_indexer
            get_graph_indexer().upsert_from_inspect(material_name, payload)
        except Exception:
            pass
        return _result(True, payload)
    except Exception as e:
        return _result(False, None, str(e))


def _serialize_socket_value(value) -> Any:
    """序列化 socket 默认值"""
    try:
        if hasattr(value, '__len__'):
            # 处理向量/颜色
            if len(value) == 4:
                return list(value)  # RGBA
            elif len(value) == 3:
                return list(value)  # XYZ
            elif len(value) == 2:
                return list(value)
            else:
                return list(value)
        return value
    except:
        return value


# ========== Node CRUD ==========

def shader_add_node(material_name: str, node_type: str, label: str = None, location: tuple = None) -> dict:
    """添加着色器节点"""
    try:
        mat = _get_material(material_name)
        
        if not mat.use_nodes:
            return _result(False, None, "Material does not use nodes")
        
        try:
            node = mat.node_tree.nodes.new(type=node_type)
        except RuntimeError:
            return _result(False, None, f"Invalid node type: {node_type}")
        
        # 设置标签
        if label:
            node.label = label
        else:
            node.label = node_type.replace('ShaderNode', '').replace('Bsdf', ' BSDF').replace('Tex', ' Texture ')
        
        # 设置位置
        if location:
            node.location = location
        else:
            # 默认放在画布中央偏左
            node.location = (0, 0)
        
        return _result(True, {
            "name": node.name,
            "type": node.type,
            "label": node.label,
        })
    except Exception as e:
        return _result(False, None, str(e))


def shader_delete_node(material_name: str, node_name: str) -> dict:
    """删除节点"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)
        
        mat.node_tree.nodes.remove(node)
        return _result(True, f"Deleted node: {node_name}")
    except Exception as e:
        return _result(False, None, str(e))


# ========== Node Properties ==========

def shader_set_node_input(material_name: str, node_name: str, input_name: str, value: Union[float, List, str]) -> dict:
    """设置节点输入值"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)
        
        # 查找输入 socket
        input_socket = node.inputs.get(input_name)
        if input_socket is None:
            return _result(False, None, f"Input not found: {input_name}")
        
        # 设置值
        if isinstance(value, (int, float)):
            # 浮点数输入
            input_socket.default_value = value
        elif isinstance(value, (list, tuple)):
            socket_type = input_socket.type
            if socket_type == 'RGBA' and len(value) == 3:
                input_socket.default_value = tuple(value) + (1.0,)
            elif socket_type == 'RGBA' and len(value) == 4:
                input_socket.default_value = tuple(value)
            elif socket_type == 'VECTOR' and len(value) == 3:
                input_socket.default_value = tuple(value)
            elif len(value) == 4:
                input_socket.default_value = tuple(value)
            elif len(value) == 3:
                try:
                    input_socket.default_value = tuple(value)
                except TypeError:
                    input_socket.default_value = tuple(value) + (1.0,)
            elif len(value) == 2:
                input_socket.default_value = tuple(value)
            else:
                return _result(False, None, f"Invalid value length: {len(value)}")
        elif isinstance(value, str):
            # 字符串 - 可能是图像或特殊输入
            input_socket.default_value = value
        else:
            return _result(False, None, f"Invalid value type: {type(value)}")
        
        return _result(True, f"Set {node_name}.{input_name} = {value}")
    except Exception as e:
        return _result(False, None, str(e))


def shader_set_node_property(material_name: str, node_name: str, property_name: str, value: Any) -> dict:
    """设置节点属性"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)
        
        # 检查属性是否存在
        if not hasattr(node, property_name):
            return _result(False, None, f"Property not found: {property_name}")
        
        setattr(node, property_name, value)
        return _result(True, f"Set {node_name}.{property_name} = {value}")
    except Exception as e:
        return _result(False, None, str(e))


# ========== Node Linking ==========

def shader_link_nodes(material_name: str, from_node: str, from_output: str, to_node: str, to_input: str) -> dict:
    """连接两个节点"""
    try:
        mat = _get_material(material_name)
        
        # 获取节点
        node_from = _get_node(mat, from_node)
        node_to = _get_node(mat, to_node)
        
        # 获取 socket
        from_socket = node_from.outputs.get(from_output)
        to_socket = node_to.inputs.get(to_input)
        
        if from_socket is None:
            return _result(False, None, f"Output not found: {from_output}")
        if to_socket is None:
            return _result(False, None, f"Input not found: {to_input}")
        
        # 检查是否已连接
        for link in mat.node_tree.links:
            if link.to_socket == to_socket:
                mat.node_tree.links.remove(link)
        
        # 创建连接
        mat.node_tree.links.new(from_socket, to_socket)
        
        return _result(True, f"Linked {from_node}.{from_output} -> {to_node}.{to_input}")
    except Exception as e:
        return _result(False, None, str(e))


def shader_unlink_nodes(material_name: str, from_node: str, from_output: str, to_node: str, to_input: str) -> dict:
    """断开两个节点的连接"""
    try:
        mat = _get_material(material_name)
        
        # 查找匹配的连接
        link_to_remove = None
        for link in mat.node_tree.links:
            if (link.from_node.name == from_node and 
                link.from_socket.name == from_output and
                link.to_node.name == to_node and 
                link.to_socket.name == to_input):
                link_to_remove = link
                break
        
        if link_to_remove:
            mat.node_tree.links.remove(link_to_remove)
            return _result(True, f"Unlinked {from_node}.{from_output} -> {to_node}.{to_input}")
        else:
            return _result(False, None, "Link not found")
    except Exception as e:
        return _result(False, None, str(e))


# ========== ColorRamp Operations ==========

def shader_colorramp_add_stop(material_name: str, node_name: str, position: float, color: List[float]) -> dict:
    """为 ColorRamp 添加色标"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)
        
        if node.type != 'VALTORGB':
            return _result(False, None, f"Node {node_name} is not a ColorRamp (ValToRGB)")
        
        # 颜色应该是 4 个值 (RGBA)
        if len(color) == 3:
            color = color + [1.0]
        
        # 添加色标
        element = node.color_ramp.elements.new(position=position)
        element.color = tuple(color)
        
        return _result(True, f"Added stop at {position} with color {color}")
    except Exception as e:
        return _result(False, None, str(e))


def shader_colorramp_remove_stop(material_name: str, node_name: str, index: int) -> dict:
    """移除 ColorRamp 色标"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)
        
        if node.type != 'VALTORGB':
            return _result(False, None, f"Node {node_name} is not a ColorRamp")
        
        elements = node.color_ramp.elements
        if index >= len(elements):
            return _result(False, None, f"Invalid index: {index}")
        
        # 至少保留一个色标
        if len(elements) <= 2:
            return _result(False, None, "Cannot remove, need at least 2 stops")
        
        elements.remove(elements[index])
        return _result(True, f"Removed stop at index {index}")
    except Exception as e:
        return _result(False, None, str(e))


def shader_colorramp_set_interpolation(material_name: str, node_name: str, interpolation: str) -> dict:
    """设置 ColorRamp 插值"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)
        
        if node.type != 'VALTORGB':
            return _result(False, None, f"Node {node_name} is not a ColorRamp")
        
        valid_interpolations = ['LINEAR', 'EASE', 'CARDINAL', 'B_SPLINE', 'CONSTANT']
        interpolation = interpolation.upper()
        
        if interpolation not in valid_interpolations:
            return _result(False, None, f"Invalid interpolation: {interpolation}")
        
        node.color_ramp.interpolation = interpolation
        return _result(True, f"Set interpolation to {interpolation}")
    except Exception as e:
        return _result(False, None, str(e))


# ========== Procedural Material Presets ==========

def shader_create_procedural_material(name: str, preset: str) -> dict:
    """从预设创建完整的程序化材质"""
    try:
        # 先创建材质
        result = shader_create_material(name)
        if not result["success"]:
            return result
        
        mat = bpy.data.materials[name]
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # 清除默认节点
        nodes.clear()
        
        # 创建输出节点
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (800, 0)
        
        preset = preset.lower()
        
        if preset == "wood":
            # Wood: Noise + Wave + ColorRamp -> BSDF
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-800, 0)
            
            mapping = nodes.new('ShaderNodeMapping')
            mapping.location = (-600, 0)
            
            noise = nodes.new('ShaderNodeTexNoise')
            noise.location = (-400, 0)
            noise.inputs['Scale'].default_value = 50.0
            noise.inputs['Detail'].default_value = 15.0
            
            wave = nodes.new('ShaderNodeTexWave')
            wave.location = (-400, -200)
            wave.inputs['Scale'].default_value = 20.0
            wave.inputs['Distortion'].default_value = 2.0
            
            math_wave = nodes.new('ShaderNodeMath')
            math_wave.location = (-200, -200)
            math_wave.operation = 'MULTIPLY'
            math_wave.inputs[1].default_value = 0.5
            
            math_add = nodes.new('ShaderNodeMath')
            math_add.location = (-200, 0)
            math_add.operation = 'ADD'
            
            color_ramp = nodes.new('ShaderNodeValToRGB')
            color_ramp.location = (0, 0)
            color_ramp.color_ramp.elements[0].color = (0.15, 0.07, 0.02, 1)  # Dark brown
            color_ramp.color_ramp.elements[1].color = (0.35, 0.18, 0.08, 1)  # Light brown
            
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (400, 0)
            bsdf.inputs['Roughness'].default_value = 0.6
            
            # 连接
            links.new(coord.outputs['Object'], mapping.inputs['Vector'])
            links.new(mapping.outputs['Vector'], noise.inputs['Vector'])
            links.new(mapping.outputs['Vector'], wave.inputs['Vector'])
            links.new(wave.outputs['Color'], math_wave.inputs[0])
            links.new(noise.outputs['Fac'], math_add.inputs[0])
            links.new(math_wave.outputs['Value'], math_add.inputs[1])
            links.new(math_add.outputs['Value'], color_ramp.inputs['Fac'])
            links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            
        elif preset == "marble":
            # Marble: Noise + Voronoi + ColorRamp -> BSDF
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-800, 0)
            
            mapping = nodes.new('ShaderNodeMapping')
            mapping.location = (-600, 0)
            
            noise = nodes.new('ShaderNodeTexNoise')
            noise.location = (-400, 0)
            noise.inputs['Scale'].default_value = 5.0
            noise.inputs['Detail'].default_value = 8.0
            
            voronoi = nodes.new('ShaderNodeTexVoronoi')
            voronoi.location = (-400, -200)
            voronoi.inputs['Scale'].default_value = 8.0
            
            math_sub = nodes.new('ShaderNodeMath')
            math_sub.location = (-200, 0)
            math_sub.operation = 'SUBTRACT'
            
            math_abs = nodes.new('ShaderNodeMath')
            math_abs.location = (0, 0)
            math_abs.operation = 'ABSOLUTE'
            
            color_ramp = nodes.new('ShaderNodeValToRGB')
            color_ramp.location = (200, 0)
            color_ramp.color_ramp.elements[0].color = (0.05, 0.05, 0.05, 1)  # Dark veins
            color_ramp.color_ramp.elements[1].color = (0.95, 0.95, 0.95, 1)  # White
            
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (400, 0)
            bsdf.inputs['Roughness'].default_value = 0.2
            
            # 连接
            links.new(coord.outputs['Object'], mapping.inputs['Vector'])
            links.new(mapping.outputs['Vector'], noise.inputs['Vector'])
            links.new(mapping.outputs['Vector'], voronoi.inputs['Vector'])
            links.new(noise.outputs['Fac'], math_sub.inputs[0])
            links.new(voronoi.outputs['Distance'], math_sub.inputs[1])
            links.new(math_sub.outputs['Value'], math_abs.inputs[0])
            links.new(math_abs.outputs['Value'], color_ramp.inputs['Fac'])
            links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            
        elif preset == "metal_scratched":
            # Metal with scratches
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-600, 0)
            
            noise = nodes.new('ShaderNodeTexNoise')
            noise.location = (-400, 0)
            noise.inputs['Scale'].default_value = 200.0
            noise.inputs['Detail'].default_value = 2.0
            
            map_range = nodes.new('ShaderNodeMapRange')
            map_range.location = (-200, 0)
            map_range.inputs['From Min'].default_value = 0.0
            map_range.inputs['From Max'].default_value = 1.0
            map_range.inputs['To Min'].default_value = 0.3
            map_range.inputs['To Max'].default_value = 0.8
            
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1)
            bsdf.inputs['Metallic'].default_value = 1.0
            
            links.new(coord.outputs['UV'], noise.inputs['Vector'])
            links.new(noise.outputs['Fac'], map_range.inputs['Value'])
            links.new(map_range.outputs['Result'], bsdf.inputs['Roughness'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            
        elif preset == "gold":
            # Gold: Simple metallic
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Base Color'].default_value = (1.0, 0.766, 0.336, 1)  # Gold
            bsdf.inputs['Metallic'].default_value = 1.0
            bsdf.inputs['Roughness'].default_value = 0.2
            
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            
        elif preset == "glass":
            # Glass: Transmission = 1
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Base Color'].default_value = (1.0, 1.0, 1.0, 1)
            bsdf.inputs['Metallic'].default_value = 0.0
            bsdf.inputs['Roughness'].default_value = 0.0
            bsdf.inputs['IOR'].default_value = 1.45
            if 'Transmission Weight' in bsdf.inputs:
                bsdf.inputs['Transmission Weight'].default_value = 1.0
            elif 'Transmission' in bsdf.inputs:
                bsdf.inputs['Transmission'].default_value = 1.0
            
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            
            _configure_eevee_transparency(mat)

        elif preset == "brick":
            # Brick pattern
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-600, 0)
            
            brick = nodes.new('ShaderNodeTexBrick')
            brick.location = (-400, 0)
            brick.inputs['Scale'].default_value = 5.0
            
            color_ramp = nodes.new('ShaderNodeValToRGB')
            color_ramp.location = (-200, 0)
            color_ramp.color_ramp.elements[0].color = (0.3, 0.2, 0.15, 1)  # Mortar
            color_ramp.color_ramp.elements[1].color = (0.7, 0.3, 0.2, 1)  # Brick
            
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Roughness'].default_value = 0.8
            
            links.new(coord.outputs['Object'], brick.inputs['Vector'])
            links.new(brick.outputs['Fac'], color_ramp.inputs['Fac'])
            links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            
        elif preset == "fabric":
            # Fabric: weave pattern
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-600, 0)
            
            wave_x = nodes.new('ShaderNodeTexWave')
            wave_x.location = (-400, 0)
            wave_x.inputs['Scale'].default_value = 40.0
            wave_x.inputs['Distortion'].default_value = 0.0
            
            wave_y = nodes.new('ShaderNodeTexWave')
            wave_y.location = (-400, -200)
            wave_y.inputs['Scale'].default_value = 40.0
            wave_y.inputs['Distortion'].default_value = 0.0
            wave_y.bands_direction = 'Y'
            
            math = nodes.new('ShaderNodeMath')
            math.location = (-200, 0)
            math.operation = 'MULTIPLY'
            
            color_ramp = nodes.new('ShaderNodeValToRGB')
            color_ramp.location = (0, 0)
            color_ramp.color_ramp.elements[0].color = (0.1, 0.1, 0.15, 1)
            color_ramp.color_ramp.elements[1].color = (0.3, 0.3, 0.35, 1)
            
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (200, 0)
            bsdf.inputs['Roughness'].default_value = 0.9
            
            links.new(coord.outputs['UV'], wave_x.inputs['Vector'])
            links.new(coord.outputs['UV'], wave_y.inputs['Vector'])
            links.new(wave_x.outputs['Color'], math.inputs[0])
            links.new(wave_y.outputs['Color'], math.inputs[1])
            links.new(math.outputs['Value'], color_ramp.inputs['Fac'])
            links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            
        elif preset == "rubber":
            # Rubber: dark, matte, slightly rough
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Base Color'].default_value = (0.05, 0.05, 0.05, 1)
            bsdf.inputs['Metallic'].default_value = 0.0
            bsdf.inputs['Roughness'].default_value = 0.7
            
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            
        elif preset == "concrete":
            # Concrete: rough, gray
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-600, 0)
            
            noise = nodes.new('ShaderNodeTexNoise')
            noise.location = (-400, 0)
            noise.inputs['Scale'].default_value = 100.0
            noise.inputs['Detail'].default_value = 8.0
            
            color_ramp = nodes.new('ShaderNodeValToRGB')
            color_ramp.location = (-200, 0)
            color_ramp.color_ramp.elements[0].color = (0.4, 0.4, 0.4, 1)
            color_ramp.color_ramp.elements[1].color = (0.6, 0.6, 0.6, 1)
            
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Roughness'].default_value = 0.9
            
            links.new(coord.outputs['Object'], noise.inputs['Vector'])
            links.new(noise.outputs['Fac'], color_ramp.inputs['Fac'])
            links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            
        elif preset == "plastic":
            # Plastic: smooth, slight reflection
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Base Color'].default_value = (0.8, 0.1, 0.1, 1)  # Red plastic
            bsdf.inputs['Metallic'].default_value = 0.0
            bsdf.inputs['Roughness'].default_value = 0.3
            bsdf.inputs['IOR'].default_value = 1.45
            
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            
        elif preset == "water":
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-1000, 0)
            mapping = nodes.new('ShaderNodeMapping')
            mapping.location = (-800, 0)

            noise1 = nodes.new('ShaderNodeTexNoise')
            noise1.location = (-600, 200)
            noise1.inputs['Scale'].default_value = 4.0
            noise1.inputs['Detail'].default_value = 8.0
            noise1.inputs['Roughness'].default_value = 0.5

            noise2 = nodes.new('ShaderNodeTexNoise')
            noise2.location = (-600, -100)
            noise2.inputs['Scale'].default_value = 12.0
            noise2.inputs['Detail'].default_value = 4.0
            noise2.inputs['Roughness'].default_value = 0.7

            mix_noise = nodes.new('ShaderNodeMath')
            mix_noise.location = (-400, 100)
            mix_noise.operation = 'ADD'

            map_range = nodes.new('ShaderNodeMapRange')
            map_range.location = (-200, 100)
            map_range.inputs['From Min'].default_value = 0.0
            map_range.inputs['From Max'].default_value = 2.0
            map_range.inputs['To Min'].default_value = 0.0
            map_range.inputs['To Max'].default_value = 1.0

            bump = nodes.new('ShaderNodeBump')
            bump.location = (0, 100)
            bump.inputs['Strength'].default_value = 0.02
            bump.inputs['Distance'].default_value = 0.1

            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (200, 0)
            bsdf.inputs['Base Color'].default_value = (0.3, 0.65, 0.6, 1)
            bsdf.inputs['Roughness'].default_value = 0.05
            bsdf.inputs['IOR'].default_value = 1.333
            _set_transmission(bsdf, 1.0)

            output.location = (600, 0)

            links.new(coord.outputs['Object'], mapping.inputs['Vector'])
            links.new(mapping.outputs['Vector'], noise1.inputs['Vector'])
            links.new(mapping.outputs['Vector'], noise2.inputs['Vector'])
            links.new(noise1.outputs['Fac'], mix_noise.inputs[0])
            links.new(noise2.outputs['Fac'], mix_noise.inputs[1])
            links.new(mix_noise.outputs['Value'], map_range.inputs['Value'])
            links.new(map_range.outputs['Result'], bump.inputs['Height'])
            links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

            _configure_eevee_transparency(mat)

        elif preset == "ice":
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-1000, 0)
            mapping = nodes.new('ShaderNodeMapping')
            mapping.location = (-800, 0)

            voronoi = nodes.new('ShaderNodeTexVoronoi')
            voronoi.location = (-600, 300)
            voronoi.inputs['Scale'].default_value = 15.0
            voronoi.feature = 'DISTANCE_TO_EDGE'

            crack_ramp = nodes.new('ShaderNodeValToRGB')
            crack_ramp.location = (-400, 300)
            crack_ramp.color_ramp.elements[0].position = 0.0
            crack_ramp.color_ramp.elements[0].color = (0.7, 0.85, 1.0, 1)
            crack_ramp.color_ramp.elements[1].position = 0.05
            crack_ramp.color_ramp.elements[1].color = (0.95, 0.97, 1.0, 1)

            noise_fine = nodes.new('ShaderNodeTexNoise')
            noise_fine.location = (-600, 0)
            noise_fine.inputs['Scale'].default_value = 30.0
            noise_fine.inputs['Detail'].default_value = 8.0

            bump1 = nodes.new('ShaderNodeBump')
            bump1.location = (-200, 0)
            bump1.inputs['Strength'].default_value = 0.03

            voronoi2 = nodes.new('ShaderNodeTexVoronoi')
            voronoi2.location = (-600, -200)
            voronoi2.inputs['Scale'].default_value = 5.0

            bump2 = nodes.new('ShaderNodeBump')
            bump2.location = (-200, -200)
            bump2.inputs['Strength'].default_value = 0.02

            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (200, 0)
            bsdf.inputs['Roughness'].default_value = 0.1
            bsdf.inputs['IOR'].default_value = 1.31
            _set_transmission(bsdf, 0.95)
            _set_sss(bsdf, weight=0.3, radius=(0.5, 0.7, 1.0), scale=0.1)

            vol = nodes.new('ShaderNodeVolumeAbsorption')
            vol.location = (200, -400)
            vol.inputs['Color'].default_value = (0.7, 0.85, 1.0, 1)
            vol.inputs['Density'].default_value = 0.15

            output.location = (600, 0)

            links.new(coord.outputs['Object'], mapping.inputs['Vector'])
            links.new(mapping.outputs['Vector'], voronoi.inputs['Vector'])
            links.new(mapping.outputs['Vector'], noise_fine.inputs['Vector'])
            links.new(mapping.outputs['Vector'], voronoi2.inputs['Vector'])
            links.new(voronoi.outputs['Distance'], crack_ramp.inputs['Fac'])
            links.new(crack_ramp.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(noise_fine.outputs['Fac'], bump1.inputs['Height'])
            links.new(voronoi2.outputs['Distance'], bump2.inputs['Height'])
            links.new(bump2.outputs['Normal'], bump1.inputs['Normal'])
            links.new(bump1.outputs['Normal'], bsdf.inputs['Normal'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
            links.new(vol.outputs['Volume'], output.inputs['Volume'])

            _configure_eevee_transparency(mat)

        elif preset == "lava":
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-1000, 0)

            noise = nodes.new('ShaderNodeTexNoise')
            noise.location = (-800, 0)
            noise.inputs['Scale'].default_value = 4.0
            noise.inputs['Detail'].default_value = 8.0
            noise.inputs['Roughness'].default_value = 0.7

            voronoi = nodes.new('ShaderNodeTexVoronoi')
            voronoi.location = (-800, -250)
            voronoi.inputs['Scale'].default_value = 3.0

            mix_fac = nodes.new('ShaderNodeMath')
            mix_fac.location = (-600, 0)
            mix_fac.operation = 'MULTIPLY'

            color_ramp = nodes.new('ShaderNodeValToRGB')
            color_ramp.location = (-400, 100)
            els = color_ramp.color_ramp.elements
            els[0].position = 0.0
            els[0].color = (0.02, 0.02, 0.02, 1)
            els[1].position = 0.6
            els[1].color = (1.0, 0.8, 0.1, 1)
            e_mid1 = color_ramp.color_ramp.elements.new(0.4)
            e_mid1.color = (0.3, 0.02, 0.0, 1)
            e_mid2 = color_ramp.color_ramp.elements.new(0.5)
            e_mid2.color = (1.0, 0.3, 0.0, 1)

            emit_ramp = nodes.new('ShaderNodeValToRGB')
            emit_ramp.location = (-400, -200)
            emit_ramp.color_ramp.elements[0].position = 0.0
            emit_ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
            emit_ramp.color_ramp.elements[1].position = 0.45
            emit_ramp.color_ramp.elements[1].color = (1, 1, 1, 1)

            rough_ramp = nodes.new('ShaderNodeValToRGB')
            rough_ramp.location = (-400, -450)
            rough_ramp.color_ramp.elements[0].position = 0.0
            rough_ramp.color_ramp.elements[0].color = (0.9, 0.9, 0.9, 1)
            rough_ramp.color_ramp.elements[1].position = 0.45
            rough_ramp.color_ramp.elements[1].color = (0.3, 0.3, 0.3, 1)

            emit_mult = nodes.new('ShaderNodeMath')
            emit_mult.location = (-100, -200)
            emit_mult.operation = 'MULTIPLY'
            emit_mult.inputs[1].default_value = 15.0

            bump = nodes.new('ShaderNodeBump')
            bump.location = (-100, -450)
            bump.inputs['Strength'].default_value = 0.3

            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (200, 0)
            bsdf.inputs['Metallic'].default_value = 0.0

            output.location = (600, 0)

            links.new(coord.outputs['Object'], noise.inputs['Vector'])
            links.new(coord.outputs['Object'], voronoi.inputs['Vector'])
            links.new(noise.outputs['Fac'], mix_fac.inputs[0])
            links.new(voronoi.outputs['Distance'], mix_fac.inputs[1])
            links.new(mix_fac.outputs['Value'], color_ramp.inputs['Fac'])
            links.new(mix_fac.outputs['Value'], emit_ramp.inputs['Fac'])
            links.new(mix_fac.outputs['Value'], rough_ramp.inputs['Fac'])
            links.new(mix_fac.outputs['Value'], bump.inputs['Height'])
            links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(color_ramp.outputs['Color'], bsdf.inputs['Emission Color'])
            links.new(emit_ramp.outputs['Color'], emit_mult.inputs[0])
            links.new(emit_mult.outputs['Value'], bsdf.inputs['Emission Strength'])
            links.new(rough_ramp.outputs['Color'], bsdf.inputs['Roughness'])
            links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        elif preset == "crystal":
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-800, 0)

            voronoi = nodes.new('ShaderNodeTexVoronoi')
            voronoi.location = (-600, 100)
            voronoi.inputs['Scale'].default_value = 3.0
            voronoi.feature = 'F1'

            color_ramp = nodes.new('ShaderNodeValToRGB')
            color_ramp.location = (-400, 100)
            color_ramp.color_ramp.elements[0].color = (0.6, 0.4, 0.9, 1)
            color_ramp.color_ramp.elements[1].color = (0.9, 0.7, 1.0, 1)

            noise = nodes.new('ShaderNodeTexNoise')
            noise.location = (-600, -150)
            noise.inputs['Scale'].default_value = 50.0
            noise.inputs['Detail'].default_value = 6.0

            bump = nodes.new('ShaderNodeBump')
            bump.location = (-200, -150)
            bump.inputs['Strength'].default_value = 0.01

            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (200, 0)
            bsdf.inputs['Roughness'].default_value = 0.02
            bsdf.inputs['IOR'].default_value = 2.42
            _set_transmission(bsdf, 1.0)

            output.location = (600, 0)

            links.new(coord.outputs['Object'], voronoi.inputs['Vector'])
            links.new(coord.outputs['Object'], noise.inputs['Vector'])
            links.new(voronoi.outputs['Distance'], color_ramp.inputs['Fac'])
            links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(noise.outputs['Fac'], bump.inputs['Height'])
            links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

            _configure_eevee_transparency(mat)

        elif preset == "snow":
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-1000, 0)

            noise_color = nodes.new('ShaderNodeTexNoise')
            noise_color.location = (-700, 300)
            noise_color.inputs['Scale'].default_value = 200.0
            noise_color.inputs['Detail'].default_value = 10.0

            color_ramp = nodes.new('ShaderNodeValToRGB')
            color_ramp.location = (-500, 300)
            color_ramp.color_ramp.elements[0].color = (0.92, 0.92, 0.98, 1)
            color_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1)

            noise_grain = nodes.new('ShaderNodeTexNoise')
            noise_grain.location = (-700, 0)
            noise_grain.inputs['Scale'].default_value = 50.0
            noise_grain.inputs['Detail'].default_value = 8.0

            bump1 = nodes.new('ShaderNodeBump')
            bump1.location = (-300, 0)
            bump1.inputs['Strength'].default_value = 0.15

            noise_mound = nodes.new('ShaderNodeTexNoise')
            noise_mound.location = (-700, -250)
            noise_mound.inputs['Scale'].default_value = 8.0
            noise_mound.inputs['Detail'].default_value = 3.0

            bump2 = nodes.new('ShaderNodeBump')
            bump2.location = (-300, -250)
            bump2.inputs['Strength'].default_value = 0.3

            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (200, 0)
            bsdf.inputs['Roughness'].default_value = 0.8
            _set_sss(bsdf, weight=0.8, radius=(0.9, 0.9, 1.0), scale=0.05)

            output.location = (600, 0)

            links.new(coord.outputs['Object'], noise_color.inputs['Vector'])
            links.new(coord.outputs['Object'], noise_grain.inputs['Vector'])
            links.new(coord.outputs['Object'], noise_mound.inputs['Vector'])
            links.new(noise_color.outputs['Fac'], color_ramp.inputs['Fac'])
            links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(noise_grain.outputs['Fac'], bump1.inputs['Height'])
            links.new(noise_mound.outputs['Fac'], bump2.inputs['Height'])
            links.new(bump2.outputs['Normal'], bump1.inputs['Normal'])
            links.new(bump1.outputs['Normal'], bsdf.inputs['Normal'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        elif preset == "leather":
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-800, 0)

            voronoi = nodes.new('ShaderNodeTexVoronoi')
            voronoi.location = (-600, 200)
            voronoi.inputs['Scale'].default_value = 30.0
            voronoi.feature = 'F1'

            grain_ramp = nodes.new('ShaderNodeValToRGB')
            grain_ramp.location = (-400, 200)
            grain_ramp.color_ramp.elements[0].color = (0.10, 0.05, 0.02, 1)
            grain_ramp.color_ramp.elements[1].color = (0.20, 0.10, 0.05, 1)

            noise = nodes.new('ShaderNodeTexNoise')
            noise.location = (-600, -100)
            noise.inputs['Scale'].default_value = 100.0
            noise.inputs['Detail'].default_value = 6.0

            mix_bump = nodes.new('ShaderNodeMath')
            mix_bump.location = (-400, -100)
            mix_bump.operation = 'ADD'

            bump = nodes.new('ShaderNodeBump')
            bump.location = (-200, 0)
            bump.inputs['Strength'].default_value = 0.15

            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (200, 0)
            bsdf.inputs['Roughness'].default_value = 0.6
            bsdf.inputs['IOR'].default_value = 1.5

            output.location = (600, 0)

            links.new(coord.outputs['UV'], voronoi.inputs['Vector'])
            links.new(coord.outputs['UV'], noise.inputs['Vector'])
            links.new(voronoi.outputs['Distance'], grain_ramp.inputs['Fac'])
            links.new(grain_ramp.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(voronoi.outputs['Distance'], mix_bump.inputs[0])
            links.new(noise.outputs['Fac'], mix_bump.inputs[1])
            links.new(mix_bump.outputs['Value'], bump.inputs['Height'])
            links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        elif preset == "neon":
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Base Color'].default_value = (0.0, 1.0, 1.0, 1)
            bsdf.inputs['Roughness'].default_value = 0.0
            bsdf.inputs['Emission Color'].default_value = (0.0, 1.0, 1.0, 1)
            bsdf.inputs['Emission Strength'].default_value = 10.0
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        elif preset == "emissive":
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Base Color'].default_value = (1.0, 0.9, 0.8, 1)
            bsdf.inputs['Roughness'].default_value = 0.0
            bsdf.inputs['Emission Color'].default_value = (1.0, 0.9, 0.8, 1)
            bsdf.inputs['Emission Strength'].default_value = 5.0
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        else:
            # Fallback: basic Principled BSDF
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Base Color'].default_value = (0.5, 0.5, 0.5, 1)
            
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        
        return _result(True, f"Created procedural material: {name} ({preset})")
    except Exception as e:
        return _result(False, None, str(e))


# ========== Material Preview ==========

def shader_preview_material(material_name: str, resolution: int = 256) -> dict:
    """渲染材质预览球并返回 base64 图片"""
    import os
    import tempfile

    try:
        mat = _get_material(material_name)

        scene = bpy.context.scene
        preview_obj = None

        # 保存原始状态
        prev_engine = scene.render.engine
        prev_res_x = scene.render.resolution_x
        prev_res_y = scene.render.resolution_y
        prev_res_pct = scene.render.resolution_percentage
        prev_filepath = scene.render.filepath
        prev_format = scene.render.image_settings.file_format
        prev_active = bpy.context.view_layer.objects.active

        try:
            # 创建预览球
            bpy.ops.mesh.primitive_uv_sphere_add(
                segments=64, ring_count=32, radius=1, location=(0, 0, 100)
            )
            preview_obj = bpy.context.active_object
            preview_obj.name = "_mat_preview_sphere"
            if preview_obj.data.materials:
                preview_obj.data.materials[0] = mat
            else:
                preview_obj.data.materials.append(mat)

            # 设置渲染参数
            # Blender 5.0 用 BLENDER_EEVEE_NEXT，旧版用 BLENDER_EEVEE
            try:
                scene.render.engine = 'BLENDER_EEVEE_NEXT'
            except TypeError:
                scene.render.engine = 'BLENDER_EEVEE'

            scene.render.resolution_x = resolution
            scene.render.resolution_y = resolution
            scene.render.resolution_percentage = 100
            scene.render.image_settings.file_format = 'PNG'

            # 输出到临时文件
            temp_path = os.path.join(tempfile.gettempdir(), f"mat_preview_{material_name}.png")
            scene.render.filepath = temp_path

            # OpenGL 视口渲染（快速）
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            override = bpy.context.copy()
                            override['area'] = area
                            override['region'] = region
                            with bpy.context.temp_override(**override):
                                bpy.ops.render.opengl(write_still=True)
                            break
                    break

            # 读取图片并转 base64
            if os.path.exists(temp_path):
                with open(temp_path, "rb") as f:
                    base64_data = base64.b64encode(f.read()).decode('utf-8')
                os.remove(temp_path)
                return _result(True, {"image": base64_data, "resolution": resolution})
            else:
                return _result(False, None, "Failed to render preview image")

        finally:
            # 清理预览球
            if preview_obj and preview_obj.name in bpy.data.objects:
                bpy.data.objects.remove(preview_obj, do_unlink=True)

            # 恢复所有设置
            scene.render.engine = prev_engine
            scene.render.resolution_x = prev_res_x
            scene.render.resolution_y = prev_res_y
            scene.render.resolution_percentage = prev_res_pct
            scene.render.filepath = prev_filepath
            scene.render.image_settings.file_format = prev_format
            if prev_active and prev_active.name in bpy.data.objects:
                bpy.context.view_layer.objects.active = prev_active

    except Exception as e:
        return _result(False, None, str(e))


def shader_configure_eevee(material_name: str) -> dict:
    """为 EEVEE 配置透射材质的必要渲染设置"""
    try:
        mat = _get_material(material_name)
        _configure_eevee_transparency(mat)
        return _result(True,
            f"已为 {material_name} 配置 EEVEE 透射设置:\n"
            "- blend_method = HASHED\n"
            "- Screen Space Refraction = 开启\n"
            "- 渲染设置 SSR + SSR Refraction = 开启\n\n"
            "如果材质仍然显示为黑色，请确认渲染引擎为 EEVEE。"
        )
    except Exception as e:
        return _result(False, None, str(e))


# ========== Node Introspection Tools ==========

def shader_list_available_nodes() -> dict:
    """列出所有可用的着色器节点类型，按类别分组"""
    try:
        import bpy
        
        # Complete categorized list of all Blender shader nodes
        categories = {
            "shader": [
                "ShaderNodeBsdfPrincipled", "ShaderNodeBsdfDiffuse", "ShaderNodeBsdfGlossy",
                "ShaderNodeBsdfGlass", "ShaderNodeBsdfRefraction", "ShaderNodeBsdfTransparent",
                "ShaderNodeBsdfTranslucent", "ShaderNodeBsdfAnisotropic", "ShaderNodeBsdfToon",
                "ShaderNodeBsdfVelvet", "ShaderNodeBsdfHair", "ShaderNodeBsdfHairPrincipled",
                "ShaderNodeSubsurfaceScattering", "ShaderNodeEmission", "ShaderNodeBackground",
                "ShaderNodeHoldout", "ShaderNodeAddShader", "ShaderNodeMixShader",
                "ShaderNodeVolumeAbsorption", "ShaderNodeVolumeScatter", "ShaderNodeVolumePrincipled",
                "ShaderNodeEeveeSpecular",
            ],
            "texture": [
                "ShaderNodeTexImage", "ShaderNodeTexEnvironment", "ShaderNodeTexSky",
                "ShaderNodeTexNoise", "ShaderNodeTexVoronoi", "ShaderNodeTexWave",
                "ShaderNodeTexMusgrave", "ShaderNodeTexGradient", "ShaderNodeTexMagic",
                "ShaderNodeTexChecker", "ShaderNodeTexBrick", "ShaderNodeTexWhiteNoise",
                "ShaderNodeTexPointDensity", "ShaderNodeTexIES",
            ],
            "color": [
                "ShaderNodeMixRGB", "ShaderNodeMix", "ShaderNodeRGBCurve", "ShaderNodeInvert",
                "ShaderNodeHueSaturation", "ShaderNodeBrightContrast", "ShaderNodeGamma",
                "ShaderNodeLight", # actually ShaderNodeLightFalloff
            ],
            "vector": [
                "ShaderNodeMapping", "ShaderNodeNormalMap", "ShaderNodeNormal",
                "ShaderNodeBump", "ShaderNodeDisplacement", "ShaderNodeVectorDisplacement",
                "ShaderNodeVectorCurve", "ShaderNodeVectorMath", "ShaderNodeVectorRotate",
                "ShaderNodeVectorTransform",
            ],
            "converter": [
                "ShaderNodeMath", "ShaderNodeMapRange", "ShaderNodeClamp",
                "ShaderNodeValToRGB", "ShaderNodeRGBToBW",
                "ShaderNodeSeparateXYZ", "ShaderNodeCombineXYZ",
                "ShaderNodeSeparateRGB", "ShaderNodeCombineRGB",
                "ShaderNodeSeparateHSV", "ShaderNodeCombineHSV",
                "ShaderNodeSeparateColor", "ShaderNodeCombineColor",
                "ShaderNodeShaderToRGB", "ShaderNodeBlackbody", "ShaderNodeWavelength",
            ],
            "input": [
                "ShaderNodeTexCoord", "ShaderNodeUVMap", "ShaderNodeAttribute",
                "ShaderNodeVertexColor", "ShaderNodeObjectInfo", "ShaderNodeCameraData",
                "ShaderNodeLightPath", "ShaderNodeFresnel", "ShaderNodeLayerWeight",
                "ShaderNodeNewGeometry", "ShaderNodeWireframe", "ShaderNodeTangent",
                "ShaderNodeParticleInfo", "ShaderNodeHairInfo", "ShaderNodeVolumeInfo",
                "ShaderNodeAmbientOcclusion", "ShaderNodeBevel",
                "ShaderNodeValue", "ShaderNodeRGB",
            ],
            "output": [
                "ShaderNodeOutputMaterial", "ShaderNodeOutputWorld", "ShaderNodeOutputLight",
                "ShaderNodeOutputAOV", "ShaderNodeOutputLineStyle",
            ],
            "layout": [
                "NodeFrame", "NodeReroute", "ShaderNodeGroup",
            ],
        }
        
        # Verify which nodes actually exist in this Blender version
        verified = {}
        for cat, node_types in categories.items():
            verified[cat] = []
            for nt in node_types:
                if hasattr(bpy.types, nt):
                    verified[cat].append(nt)
        
        return _result(True, verified)
    except Exception as e:
        return _result(False, None, str(e))


def shader_get_node_sockets(material_name: str, node_name: str) -> dict:
    """获取指定节点的所有输入输出 socket 详细信息，包括类型、默认值、是否已连接"""
    try:
        mat = _get_material(material_name)
        node = _get_node(mat, node_name)
        
        inputs = []
        for inp in node.inputs:
            info = {
                "name": inp.name,
                "type": inp.type,  # RGBA, VECTOR, VALUE, SHADER, etc.
                "is_linked": inp.is_linked,
            }
            # Get default value if available
            try:
                if hasattr(inp, 'default_value'):
                    val = inp.default_value
                    if hasattr(val, '__len__'):
                        info["default_value"] = list(val)
                    else:
                        info["default_value"] = val
            except:
                pass
            
            # Show what it's connected to
            if inp.is_linked:
                link = inp.links[0]
                info["linked_from"] = f"{link.from_node.name}.{link.from_socket.name}"
            
            inputs.append(info)
        
        outputs = []
        for out in node.outputs:
            info = {
                "name": out.name,
                "type": out.type,
                "is_linked": out.is_linked,
            }
            if out.is_linked:
                connections = [f"{l.to_node.name}.{l.to_socket.name}" for l in out.links]
                info["linked_to"] = connections
            outputs.append(info)
        
        # Also get node properties
        properties = {}
        for prop_name in ['operation', 'blend_type', 'data_type', 'distribution',
                          'interpolation', 'projection', 'color_space', 'component',
                          'mode', 'feature', 'distance', 'wave_type', 'wave_profile',
                          'musgrave_type', 'gradient_type', 'voronoi_dimensions',
                          'noise_dimensions', 'coloring']:
            if hasattr(node, prop_name):
                try:
                    properties[prop_name] = str(getattr(node, prop_name))
                except:
                    pass
        
        return _result(True, {
            "node_name": node.name,
            "node_type": node.bl_idname,
            "node_label": node.label,
            "inputs": inputs,
            "outputs": outputs,
            "properties": properties,
        })
    except Exception as e:
        return _result(False, None, str(e))


def shader_batch_add_nodes(material_name: str, nodes: list) -> dict:
    """批量添加节点。nodes 是列表，每项: {"type": "ShaderNodeXxx", "name": "可选名称", "label": "可选标签", "location": [x, y], "inputs": {"InputName": value}, "properties": {"prop": value}}"""
    try:
        mat = _get_material(material_name)
        if not mat.use_nodes:
            return _result(False, None, "Material does not use nodes")
        
        created = []
        for node_spec in nodes:
            node_type = node_spec.get("type")
            if not node_type:
                continue
            
            try:
                node = mat.node_tree.nodes.new(type=node_type)
            except RuntimeError:
                created.append({"error": f"Invalid node type: {node_type}"})
                continue
            
            # Set name if provided
            if "name" in node_spec:
                node.name = node_spec["name"]
            
            # Set label
            if "label" in node_spec:
                node.label = node_spec["label"]
            
            # Set location
            if "location" in node_spec:
                node.location = tuple(node_spec["location"])
            
            # Set input values
            if "inputs" in node_spec:
                for input_name, value in node_spec["inputs"].items():
                    inp = node.inputs.get(input_name)
                    if inp is None:
                        continue
                    try:
                        if isinstance(value, (list, tuple)):
                            socket_type = inp.type
                            if socket_type == 'RGBA' and len(value) == 3:
                                inp.default_value = tuple(value) + (1.0,)
                            else:
                                inp.default_value = tuple(value)
                        else:
                            inp.default_value = value
                    except:
                        pass
            
            # Set properties
            if "properties" in node_spec:
                for prop_name, prop_value in node_spec["properties"].items():
                    if hasattr(node, prop_name):
                        try:
                            setattr(node, prop_name, prop_value)
                        except:
                            pass
            
            created.append({
                "name": node.name,
                "type": node.bl_idname,
                "label": node.label,
            })
        
        return _result(True, {"created_nodes": created, "count": len(created)})
    except Exception as e:
        return _result(False, None, str(e))


def shader_batch_link_nodes(material_name: str, links: list) -> dict:
    """批量连接节点。links 是列表，每项: {"from_node": "name", "from_output": "socket", "to_node": "name", "to_input": "socket"}"""
    try:
        mat = _get_material(material_name)
        
        linked = []
        errors = []
        for link_spec in links:
            try:
                node_from = mat.node_tree.nodes.get(link_spec["from_node"])
                node_to = mat.node_tree.nodes.get(link_spec["to_node"])
                
                if not node_from:
                    errors.append(f"Node not found: {link_spec['from_node']}")
                    continue
                if not node_to:
                    errors.append(f"Node not found: {link_spec['to_node']}")
                    continue
                
                from_socket = node_from.outputs.get(link_spec["from_output"])
                to_socket = node_to.inputs.get(link_spec["to_input"])
                
                if not from_socket:
                    errors.append(f"Output not found: {link_spec['from_node']}.{link_spec['from_output']}")
                    continue
                if not to_socket:
                    errors.append(f"Input not found: {link_spec['to_node']}.{link_spec['to_input']}")
                    continue
                
                # Remove existing link to this input
                for existing in mat.node_tree.links:
                    if existing.to_socket == to_socket:
                        mat.node_tree.links.remove(existing)
                        break
                
                mat.node_tree.links.new(from_socket, to_socket)
                linked.append(f"{link_spec['from_node']}.{link_spec['from_output']} -> {link_spec['to_node']}.{link_spec['to_input']}")
            except Exception as e:
                errors.append(str(e))
        
        return _result(True, {"linked": linked, "errors": errors})
    except Exception as e:
        return _result(False, None, str(e))


def shader_clear_nodes(material_name: str, keep_output: bool = True) -> dict:
    """清除材质的所有节点（可选保留输出节点）"""
    try:
        mat = _get_material(material_name)
        if not mat.use_nodes:
            return _result(False, None, "Material does not use nodes")
        
        nodes = mat.node_tree.nodes
        if keep_output:
            output_node = None
            for node in nodes:
                if node.type == 'OUTPUT_MATERIAL':
                    output_node = node
                    break
            nodes.clear()
            if output_node is None:
                # Recreate output
                output = nodes.new('ShaderNodeOutputMaterial')
                output.location = (800, 0)
            # Note: clear() removes all, so we need to recreate
            output = nodes.new('ShaderNodeOutputMaterial')
            output.location = (800, 0)
        else:
            nodes.clear()
        
        return _result(True, f"Cleared all nodes from {material_name}")
    except Exception as e:
        return _result(False, None, str(e))


def shader_get_material_summary(
    material_name: str,
    detail_level: str = "basic",
    include_node_index: bool = False,
    node_index_limit: int = 80,
) -> dict:
    """获取材质摘要，默认轻量返回，必要时再拉 full 详情"""
    try:
        mat = _get_material(material_name)
        if not mat.use_nodes:
            return _result(True, {"name": material_name, "use_nodes": False})
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        node_types = {}
        key_params = {}
        level = (detail_level or "basic").lower()
        
        for node in nodes:
            bl_type = node.bl_idname
            if bl_type not in node_types:
                node_types[bl_type] = 0
            node_types[bl_type] += 1
            
            # Extract key parameters from important nodes
            if node.type == 'BSDF_PRINCIPLED':
                params = {}
                for inp in node.inputs:
                    if inp.is_linked:
                        params[inp.name] = f"[linked from {inp.links[0].from_node.name}]"
                    elif hasattr(inp, 'default_value'):
                        try:
                            val = inp.default_value
                            if hasattr(val, '__len__'):
                                params[inp.name] = [round(v, 3) for v in val]
                            else:
                                params[inp.name] = round(val, 3) if isinstance(val, float) else val
                        except:
                            pass
                # basic 模式下只保留高价值参数，减少无效噪音
                if level == "basic":
                    high_value_keys = {
                        "Base Color", "Metallic", "Roughness", "IOR",
                        "Transmission", "Transmission Weight", "Alpha",
                        "Emission Color", "Emission Strength", "Normal",
                    }
                    params = {k: v for k, v in params.items() if k in high_value_keys}
                key_params["Principled BSDF"] = params
        
        # Material settings
        mat_settings = {
            "blend_method": getattr(mat, 'blend_method', 'N/A'),
            "use_screen_refraction": getattr(mat, 'use_screen_refraction', 'N/A'),
            "use_backface_culling": getattr(mat, 'use_backface_culling', False),
        }
        
        summary = {
            "name": material_name,
            "node_count": len(nodes),
            "link_count": len(links),
            "node_types_used": node_types,
            "key_parameters": key_params,
            "material_settings": mat_settings,
        }

        if include_node_index:
            limited = list(nodes)[:max(1, min(int(node_index_limit or 80), 300))]
            summary["node_index"] = [
                {"name": n.name, "type": n.bl_idname, "label": n.label}
                for n in limited
            ]
            summary["node_index_truncated"] = len(nodes) > len(limited)

        if level == "full":
            summary["connections_preview"] = [
                f"{l.from_node.name}.{l.from_socket.name} -> {l.to_node.name}.{l.to_socket.name}"
                for l in list(links)[:120]
            ]
            summary["connections_truncated"] = len(links) > 120

        try:
            from .context.indexer import get_graph_indexer
            get_graph_indexer().upsert_from_summary(material_name, summary)
        except Exception:
            pass
        return _result(True, summary)
    except Exception as e:
        return _result(False, None, str(e))


def shader_search_index(material_name: str, query: str, top_k: int = 10) -> dict:
    """在本地节点索引中做轻量语义检索，优先返回候选节点名"""
    try:
        from .context.indexer import get_graph_indexer

        indexer = get_graph_indexer()
        sem = indexer.semantic_search(material_name=material_name, query=query, top_k=top_k)
        candidates = []
        for item in sem.get("items", []):
            meta = item.get("metadata", {})
            if meta.get("kind") == "node" and meta.get("node_name"):
                candidates.append({
                    "node_name": meta.get("node_name"),
                    "node_type": meta.get("node_type", ""),
                    "node_label": meta.get("node_label", ""),
                    "score": item.get("score", 0),
                })

        # 语义命中为空时，回退关键词过滤
        if not candidates:
            fallback = indexer.query_nodes(material_name=material_name, keyword=query, limit=top_k, offset=0)
            candidates = [{
                "node_name": n.get("name", ""),
                "node_type": n.get("type", ""),
                "node_label": n.get("label", ""),
                "score": 0.0,
            } for n in fallback.get("items", [])]

        return _result(True, {
            "material_name": material_name,
            "query": query,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "hint": "优先使用返回的 node_name 列表调用 shader_inspect_nodes(node_names=[...], compact=false, include_values=true) 做精读。",
        })
    except Exception as e:
        return _result(False, None, str(e))


# ========== Tool Execution ==========

def execute_shader_tool(tool_name: str, arguments: dict) -> dict:
    """
    执行着色器工具
    
    返回格式: {"success": bool, "result": Any, "error": str|None}
    """
    try:
        if tool_name == "shader_create_material":
            return shader_create_material(**arguments)
        elif tool_name == "shader_delete_material":
            return shader_delete_material(**arguments)
        elif tool_name == "shader_list_materials":
            return shader_list_materials()
        elif tool_name == "shader_assign_material":
            return shader_assign_material(**arguments)
        elif tool_name == "shader_inspect_nodes":
            return shader_inspect_nodes(**arguments)
        elif tool_name == "shader_add_node":
            return shader_add_node(**arguments)
        elif tool_name == "shader_delete_node":
            return shader_delete_node(**arguments)
        elif tool_name == "shader_set_node_input":
            return shader_set_node_input(**arguments)
        elif tool_name == "shader_set_node_property":
            return shader_set_node_property(**arguments)
        elif tool_name == "shader_link_nodes":
            return shader_link_nodes(**arguments)
        elif tool_name == "shader_unlink_nodes":
            return shader_unlink_nodes(**arguments)
        elif tool_name == "shader_colorramp_add_stop":
            return shader_colorramp_add_stop(**arguments)
        elif tool_name == "shader_colorramp_remove_stop":
            return shader_colorramp_remove_stop(**arguments)
        elif tool_name == "shader_colorramp_set_interpolation":
            return shader_colorramp_set_interpolation(**arguments)
        elif tool_name == "shader_create_procedural_material":
            return shader_create_procedural_material(**arguments)
        elif tool_name == "shader_preview_material":
            return shader_preview_material(**arguments)
        elif tool_name == "shader_configure_eevee":
            return shader_configure_eevee(**arguments)
        elif tool_name == "shader_list_available_nodes":
            return shader_list_available_nodes()
        elif tool_name == "shader_get_node_sockets":
            return shader_get_node_sockets(**arguments)
        elif tool_name == "shader_batch_add_nodes":
            return shader_batch_add_nodes(**arguments)
        elif tool_name == "shader_batch_link_nodes":
            return shader_batch_link_nodes(**arguments)
        elif tool_name == "shader_clear_nodes":
            return shader_clear_nodes(**arguments)
        elif tool_name == "shader_get_material_summary":
            return shader_get_material_summary(**arguments)
        elif tool_name == "shader_search_index":
            return shader_search_index(**arguments)
        else:
            return _result(False, None, f"Unknown tool: {tool_name}")
    except Exception as e:
        return _result(False, None, str(e))
