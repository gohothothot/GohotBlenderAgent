import bpy
import math
from .shader_tools import _result


def scene_add_light(light_type: str = "POINT", location: list = None,
                    energy: float = 1000.0, color: list = None, name: str = None) -> dict:
    try:
        valid_types = {"POINT", "SUN", "SPOT", "AREA"}
        light_type = light_type.upper()
        if light_type not in valid_types:
            return _result(False, None, f"无效灯光类型: {light_type}，可用: {valid_types}")

        loc = tuple(location) if location else (0, 0, 5)
        light_data = bpy.data.lights.new(name=name or f"{light_type}_Light", type=light_type)
        light_data.energy = energy
        if color:
            light_data.color = tuple(color[:3])

        light_obj = bpy.data.objects.new(light_data.name, light_data)
        light_obj.location = loc
        bpy.context.collection.objects.link(light_obj)

        return _result(True, f"已创建 {light_type} 灯光: {light_obj.name}，位置={list(loc)}，能量={energy}")
    except Exception as e:
        return _result(False, None, str(e))


def scene_modify_light(name: str, energy: float = None, color: list = None,
                       spot_size: float = None, spot_blend: float = None,
                       shadow_soft_size: float = None) -> dict:
    try:
        if name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {name}")
        obj = bpy.data.objects[name]
        if obj.type != 'LIGHT':
            return _result(False, None, f"{name} 不是灯光")

        light = obj.data
        changes = []
        if energy is not None:
            light.energy = energy
            changes.append(f"能量={energy}")
        if color is not None:
            light.color = tuple(color[:3])
            changes.append(f"颜色={color[:3]}")
        if spot_size is not None and light.type == 'SPOT':
            light.spot_size = math.radians(spot_size)
            changes.append(f"锥角={spot_size}°")
        if spot_blend is not None and light.type == 'SPOT':
            light.spot_blend = spot_blend
            changes.append(f"柔和={spot_blend}")
        if shadow_soft_size is not None:
            light.shadow_soft_size = shadow_soft_size
            changes.append(f"阴影柔和={shadow_soft_size}")

        return _result(True, f"已修改灯光 {name}: {', '.join(changes)}")
    except Exception as e:
        return _result(False, None, str(e))


def scene_add_camera(location: list = None, rotation: list = None,
                     lens: float = 50.0, name: str = None) -> dict:
    try:
        cam_data = bpy.data.cameras.new(name=name or "Camera")
        cam_data.lens = lens

        cam_obj = bpy.data.objects.new(cam_data.name, cam_data)
        if location:
            cam_obj.location = tuple(location)
        if rotation:
            cam_obj.rotation_euler = tuple(math.radians(r) for r in rotation)

        bpy.context.collection.objects.link(cam_obj)

        return _result(True, f"已创建相机: {cam_obj.name}，焦距={lens}mm")
    except Exception as e:
        return _result(False, None, str(e))


def scene_set_active_camera(name: str) -> dict:
    try:
        if name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {name}")
        obj = bpy.data.objects[name]
        if obj.type != 'CAMERA':
            return _result(False, None, f"{name} 不是相机")
        bpy.context.scene.camera = obj
        return _result(True, f"已设置活动相机: {name}")
    except Exception as e:
        return _result(False, None, str(e))


def scene_add_modifier(object_name: str, modifier_type: str, name: str = None, **params) -> dict:
    try:
        if object_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {object_name}")
        obj = bpy.data.objects[object_name]

        valid_types = {
            "SUBSURF", "MIRROR", "ARRAY", "BEVEL", "SOLIDIFY",
            "BOOLEAN", "DECIMATE", "SMOOTH", "WIREFRAME", "SHRINKWRAP",
            "DISPLACE", "SIMPLE_DEFORM", "CURVE", "ARMATURE",
        }
        modifier_type = modifier_type.upper()
        if modifier_type not in valid_types:
            return _result(False, None, f"无效修改器: {modifier_type}，可用: {valid_types}")

        mod = obj.modifiers.new(name=name or modifier_type, type=modifier_type)

        for key, val in params.items():
            if hasattr(mod, key):
                setattr(mod, key, val)

        return _result(True, f"已为 {object_name} 添加修改器: {mod.name} ({modifier_type})")
    except Exception as e:
        return _result(False, None, str(e))


def scene_set_modifier_param(object_name: str, modifier_name: str,
                             param_name: str, value) -> dict:
    try:
        if object_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {object_name}")
        obj = bpy.data.objects[object_name]
        mod = obj.modifiers.get(modifier_name)
        if mod is None:
            return _result(False, None, f"修改器不存在: {modifier_name}")
        if not hasattr(mod, param_name):
            return _result(False, None, f"参数不存在: {param_name}")

        setattr(mod, param_name, value)
        return _result(True, f"已设置 {object_name}.{modifier_name}.{param_name} = {value}")
    except Exception as e:
        return _result(False, None, str(e))


def scene_remove_modifier(object_name: str, modifier_name: str) -> dict:
    try:
        if object_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {object_name}")
        obj = bpy.data.objects[object_name]
        mod = obj.modifiers.get(modifier_name)
        if mod is None:
            return _result(False, None, f"修改器不存在: {modifier_name}")
        obj.modifiers.remove(mod)
        return _result(True, f"已移除 {object_name} 的修改器: {modifier_name}")
    except Exception as e:
        return _result(False, None, str(e))


def scene_manage_collection(action: str, collection_name: str,
                            object_name: str = None, parent_name: str = None) -> dict:
    try:
        if action == "create":
            if collection_name in bpy.data.collections:
                return _result(False, None, f"集合已存在: {collection_name}")
            col = bpy.data.collections.new(collection_name)
            parent = bpy.data.collections.get(parent_name) if parent_name else bpy.context.scene.collection
            parent.children.link(col)
            return _result(True, f"已创建集合: {collection_name}")

        elif action == "delete":
            col = bpy.data.collections.get(collection_name)
            if col is None:
                return _result(False, None, f"集合不存在: {collection_name}")
            bpy.data.collections.remove(col)
            return _result(True, f"已删除集合: {collection_name}")

        elif action == "move_object":
            if not object_name:
                return _result(False, None, "需要 object_name")
            if object_name not in bpy.data.objects:
                return _result(False, None, f"物体不存在: {object_name}")
            col = bpy.data.collections.get(collection_name)
            if col is None:
                return _result(False, None, f"集合不存在: {collection_name}")
            obj = bpy.data.objects[object_name]
            for c in obj.users_collection:
                c.objects.unlink(obj)
            col.objects.link(obj)
            return _result(True, f"已将 {object_name} 移至集合 {collection_name}")

        elif action == "list":
            cols = []
            for col in bpy.data.collections:
                cols.append({
                    "name": col.name,
                    "objects": [o.name for o in col.objects],
                })
            return _result(True, cols)

        return _result(False, None, f"无效操作: {action}，可用: create, delete, move_object, list")
    except Exception as e:
        return _result(False, None, str(e))


def scene_set_world(color: list = None, strength: float = 1.0,
                    use_hdri: bool = False, hdri_path: str = None) -> dict:
    try:
        world = bpy.context.scene.world
        if world is None:
            world = bpy.data.worlds.new("World")
            bpy.context.scene.world = world

        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links

        bg = None
        output = None
        for node in nodes:
            if node.type == 'BACKGROUND':
                bg = node
            elif node.type == 'OUTPUT_WORLD':
                output = node

        if bg is None:
            nodes.clear()
            bg = nodes.new('ShaderNodeBackground')
            output = nodes.new('ShaderNodeOutputWorld')
            output.location = (200, 0)
            links.new(bg.outputs['Background'], output.inputs['Surface'])

        if use_hdri and hdri_path:
            env_tex = None
            for node in nodes:
                if node.type == 'TEX_ENVIRONMENT':
                    env_tex = node
                    break
            if env_tex is None:
                env_tex = nodes.new('ShaderNodeTexEnvironment')
                env_tex.location = (-300, 0)
                links.new(env_tex.outputs['Color'], bg.inputs['Color'])
            env_tex.image = bpy.data.images.load(hdri_path)
            bg.inputs['Strength'].default_value = strength
            return _result(True, f"已设置 HDRI 环境: {hdri_path}，强度={strength}")
        else:
            if color:
                bg.inputs['Color'].default_value = tuple(color[:3]) + (1.0,) if len(color) == 3 else tuple(color)
            bg.inputs['Strength'].default_value = strength
            return _result(True, f"已设置世界环境颜色，强度={strength}")

    except Exception as e:
        return _result(False, None, str(e))


def scene_duplicate_object(name: str, linked: bool = False, new_name: str = None) -> dict:
    try:
        if name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {name}")

        src = bpy.data.objects[name]
        if linked:
            new_obj = src.copy()
        else:
            new_obj = src.copy()
            if src.data:
                new_obj.data = src.data.copy()

        if new_name:
            new_obj.name = new_name

        bpy.context.collection.objects.link(new_obj)
        return _result(True, f"已复制 {name} → {new_obj.name}")
    except Exception as e:
        return _result(False, None, str(e))


def scene_parent_object(child_name: str, parent_name: str) -> dict:
    try:
        if child_name not in bpy.data.objects:
            return _result(False, None, f"子物体不存在: {child_name}")
        if parent_name not in bpy.data.objects:
            return _result(False, None, f"父物体不存在: {parent_name}")

        child = bpy.data.objects[child_name]
        parent = bpy.data.objects[parent_name]
        child.parent = parent
        return _result(True, f"已设置 {child_name} 的父级为 {parent_name}")
    except Exception as e:
        return _result(False, None, str(e))


def scene_set_visibility(name: str, visible: bool = True,
                         render_visible: bool = True) -> dict:
    try:
        if name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {name}")
        obj = bpy.data.objects[name]
        obj.hide_viewport = not visible
        obj.hide_render = not render_visible
        return _result(True, f"已设置 {name} 可见性: 视口={visible}, 渲染={render_visible}")
    except Exception as e:
        return _result(False, None, str(e))


def scene_get_render_settings() -> dict:
    """获取当前渲染设置的完整信息"""
    try:
        scene = bpy.context.scene
        render = scene.render
        
        settings = {
            "engine": render.engine,
            "resolution": [render.resolution_x, render.resolution_y],
            "resolution_percentage": render.resolution_percentage,
            "film_transparent": render.film_transparent,
            "fps": scene.render.fps,
            "frame_range": [scene.frame_start, scene.frame_end, scene.frame_current],
        }
        
        # EEVEE settings
        if hasattr(scene, 'eevee'):
            eevee = scene.eevee
            settings["eevee"] = {
                "use_ssr": eevee.use_ssr,
                "use_ssr_refraction": eevee.use_ssr_refraction,
                "use_bloom": getattr(eevee, 'use_bloom', 'N/A'),
                "use_gtao": getattr(eevee, 'use_gtao', 'N/A'),
                "taa_render_samples": getattr(eevee, 'taa_render_samples', 'N/A'),
                "taa_samples": getattr(eevee, 'taa_samples', 'N/A'),
                "shadow_cube_size": getattr(eevee, 'shadow_cube_size', 'N/A'),
                "shadow_cascade_size": getattr(eevee, 'shadow_cascade_size', 'N/A'),
            }
        
        # Cycles settings
        if render.engine == 'CYCLES':
            cycles = scene.cycles
            settings["cycles"] = {
                "samples": cycles.samples,
                "preview_samples": cycles.preview_samples,
                "use_denoising": cycles.use_denoising,
                "device": cycles.device,
            }
        
        # Color management
        settings["color_management"] = {
            "view_transform": scene.view_settings.view_transform,
            "look": scene.view_settings.look,
            "exposure": scene.view_settings.exposure,
            "gamma": scene.view_settings.gamma,
        }
        
        return _result(True, settings)
    except Exception as e:
        return _result(False, None, str(e))


def scene_set_render_settings(engine: str = None, resolution: list = None,
                               samples: int = None, use_ssr: bool = None,
                               use_ssr_refraction: bool = None,
                               film_transparent: bool = None,
                               view_transform: str = None) -> dict:
    """设置渲染参数"""
    try:
        scene = bpy.context.scene
        changes = []
        
        if engine:
            engine = engine.upper()
            engine_map = {
                "EEVEE": "BLENDER_EEVEE_NEXT",
                "EEVEE_NEXT": "BLENDER_EEVEE_NEXT",
                "BLENDER_EEVEE": "BLENDER_EEVEE_NEXT",
                "BLENDER_EEVEE_NEXT": "BLENDER_EEVEE_NEXT",
                "CYCLES": "CYCLES",
                "WORKBENCH": "BLENDER_WORKBENCH",
            }
            target_engine = engine_map.get(engine, engine)
            try:
                scene.render.engine = target_engine
            except TypeError:
                # Fallback for older Blender
                if "EEVEE" in engine:
                    scene.render.engine = "BLENDER_EEVEE"
            changes.append(f"引擎={scene.render.engine}")
        
        if resolution:
            scene.render.resolution_x = resolution[0]
            scene.render.resolution_y = resolution[1]
            changes.append(f"分辨率={resolution}")
        
        if samples is not None:
            if scene.render.engine == 'CYCLES':
                scene.cycles.samples = samples
            elif hasattr(scene, 'eevee'):
                scene.eevee.taa_render_samples = samples
            changes.append(f"采样={samples}")
        
        if use_ssr is not None and hasattr(scene, 'eevee'):
            scene.eevee.use_ssr = use_ssr
            changes.append(f"SSR={use_ssr}")
        
        if use_ssr_refraction is not None and hasattr(scene, 'eevee'):
            scene.eevee.use_ssr_refraction = use_ssr_refraction
            changes.append(f"SSR折射={use_ssr_refraction}")
        
        if film_transparent is not None:
            scene.render.film_transparent = film_transparent
            changes.append(f"透明胶片={film_transparent}")
        
        if view_transform:
            scene.view_settings.view_transform = view_transform
            changes.append(f"视图变换={view_transform}")
        
        return _result(True, f"已更新渲染设置: {', '.join(changes)}")
    except Exception as e:
        return _result(False, None, str(e))


def scene_get_object_materials(object_name: str) -> dict:
    """获取物体的所有材质及其详细信息"""
    try:
        if object_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {object_name}")
        
        obj = bpy.data.objects[object_name]
        if not hasattr(obj.data, 'materials'):
            return _result(False, None, f"{object_name} 不支持材质")
        
        materials = []
        for i, mat in enumerate(obj.data.materials):
            if mat is None:
                materials.append({"slot": i, "name": None})
                continue
            
            mat_info = {
                "slot": i,
                "name": mat.name,
                "use_nodes": mat.use_nodes,
            }
            
            if mat.use_nodes:
                # Count nodes and get key info
                nodes = mat.node_tree.nodes
                links = mat.node_tree.links
                mat_info["node_count"] = len(nodes)
                mat_info["link_count"] = len(links)
                
                # Find main shader type
                for node in nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        mat_info["main_shader"] = "Principled BSDF"
                        # Get key values
                        key_vals = {}
                        for inp_name in ['Base Color', 'Metallic', 'Roughness', 'IOR', 
                                        'Transmission Weight', 'Transmission', 'Alpha',
                                        'Emission Strength']:
                            inp = node.inputs.get(inp_name)
                            if inp:
                                if inp.is_linked:
                                    key_vals[inp_name] = "[linked]"
                                else:
                                    try:
                                        val = inp.default_value
                                        if hasattr(val, '__len__'):
                                            key_vals[inp_name] = [round(v, 3) for v in val]
                                        else:
                                            key_vals[inp_name] = round(val, 3)
                                    except:
                                        pass
                        mat_info["key_values"] = key_vals
                        break
                    elif node.type == 'EMISSION':
                        mat_info["main_shader"] = "Emission"
                        break
                    elif node.type == 'BSDF_GLASS':
                        mat_info["main_shader"] = "Glass BSDF"
                        break
                
                # Material settings
                mat_info["blend_method"] = getattr(mat, 'blend_method', 'N/A')
                mat_info["use_screen_refraction"] = getattr(mat, 'use_screen_refraction', 'N/A')
            
            materials.append(mat_info)
        
        return _result(True, {"object": object_name, "materials": materials})
    except Exception as e:
        return _result(False, None, str(e))


def scene_get_world_info() -> dict:
    """获取世界环境设置信息"""
    try:
        world = bpy.context.scene.world
        if not world:
            return _result(True, {"world": None, "message": "没有设置世界环境"})
        
        info = {
            "name": world.name,
            "use_nodes": world.use_nodes,
        }
        
        if world.use_nodes:
            nodes = world.node_tree.nodes
            links = world.node_tree.links
            info["node_count"] = len(nodes)
            
            # Find background node
            for node in nodes:
                if node.type == 'BACKGROUND':
                    bg_info = {}
                    color_inp = node.inputs.get('Color')
                    strength_inp = node.inputs.get('Strength')
                    if color_inp:
                        if color_inp.is_linked:
                            bg_info["color"] = "[linked]"
                        else:
                            bg_info["color"] = list(color_inp.default_value)
                    if strength_inp:
                        bg_info["strength"] = strength_inp.default_value
                    info["background"] = bg_info
                    break
        
        return _result(True, info)
    except Exception as e:
        return _result(False, None, str(e))


def scene_list_all_materials() -> dict:
    """列出场景中所有材质及其使用情况"""
    try:
        result = []
        for mat in bpy.data.materials:
            info = {
                "name": mat.name,
                "use_nodes": mat.use_nodes,
                "users": mat.users,
            }
            
            # Find which objects use this material
            used_by = []
            for obj in bpy.data.objects:
                if hasattr(obj.data, 'materials'):
                    for m in obj.data.materials:
                        if m and m.name == mat.name:
                            used_by.append(obj.name)
                            break
            info["used_by"] = used_by
            
            if mat.use_nodes:
                info["node_count"] = len(mat.node_tree.nodes)
            
            result.append(info)
        
        return _result(True, result)
    except Exception as e:
        return _result(False, None, str(e))


def execute_scene_tool(tool_name: str, arguments: dict) -> dict:
    tools_map = {
        "scene_add_light": scene_add_light,
        "scene_modify_light": scene_modify_light,
        "scene_add_camera": scene_add_camera,
        "scene_set_active_camera": scene_set_active_camera,
        "scene_add_modifier": scene_add_modifier,
        "scene_set_modifier_param": scene_set_modifier_param,
        "scene_remove_modifier": scene_remove_modifier,
        "scene_manage_collection": scene_manage_collection,
        "scene_set_world": scene_set_world,
        "scene_duplicate_object": scene_duplicate_object,
        "scene_parent_object": scene_parent_object,
        "scene_set_visibility": scene_set_visibility,
        "scene_get_render_settings": scene_get_render_settings,
        "scene_set_render_settings": scene_set_render_settings,
        "scene_get_object_materials": scene_get_object_materials,
        "scene_get_world_info": scene_get_world_info,
        "scene_list_all_materials": scene_list_all_materials,
    }
    try:
        func = tools_map.get(tool_name)
        if func:
            return func(**arguments)
        return _result(False, None, f"未知场景工具: {tool_name}")
    except Exception as e:
        return _result(False, None, str(e))
