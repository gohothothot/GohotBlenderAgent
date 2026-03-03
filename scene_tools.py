import bpy
import math
import os
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


def scene_apply_modifier(object_name: str, modifier_name: str) -> dict:
    try:
        if object_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {object_name}")
        obj = bpy.data.objects[object_name]
        mod = obj.modifiers.get(modifier_name)
        if mod is None:
            return _result(False, None, f"修改器不存在: {modifier_name}")
        if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META", "GREASEPENCIL"}:
            return _result(False, None, f"对象类型不支持应用修改器: {obj.type}")

        view_layer = bpy.context.view_layer
        for o in view_layer.objects:
            o.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier_name)
        return _result(True, {"object": object_name, "applied_modifier": modifier_name})
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


def scene_setup_daylight_water(
    sun_energy: float = 4.0,
    sun_angle: float = 1.2,
    sun_elevation: float = 35.0,
    sun_rotation: float = 25.0,
    sky_strength: float = 1.3,
) -> dict:
    """为水材质快速配置可见日光反射：Nishita 天空 + SUN 灯 + EEVEE 反射设置"""
    try:
        world = bpy.context.scene.world
        if world is None:
            world = bpy.data.worlds.new("World")
            bpy.context.scene.world = world
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        nodes.clear()

        sky = nodes.new("ShaderNodeTexSky")
        sky.location = (-450, 0)
        bg = nodes.new("ShaderNodeBackground")
        bg.location = (-150, 0)
        out = nodes.new("ShaderNodeOutputWorld")
        out.location = (120, 0)
        links.new(sky.outputs["Color"], bg.inputs["Color"])
        links.new(bg.outputs["Background"], out.inputs["Surface"])

        # Nishita 在室外日光/天空反射上通常更稳定
        if hasattr(sky, "sky_type"):
            sky.sky_type = "NISHITA"
        if hasattr(sky, "sun_elevation"):
            sky.sun_elevation = math.radians(float(sun_elevation))
        if hasattr(sky, "sun_rotation"):
            sky.sun_rotation = math.radians(float(sun_rotation))
        bg.inputs["Strength"].default_value = float(sky_strength)

        sun_obj = None
        for obj in bpy.data.objects:
            if obj.type == "LIGHT" and getattr(obj.data, "type", "") == "SUN":
                sun_obj = obj
                break
        if sun_obj is None:
            sun_data = bpy.data.lights.new(name="AgentSun", type="SUN")
            sun_obj = bpy.data.objects.new("AgentSun", sun_data)
            bpy.context.collection.objects.link(sun_obj)

        sun_obj.data.energy = float(sun_energy)
        if hasattr(sun_obj.data, "angle"):
            sun_obj.data.angle = math.radians(float(sun_angle))
        sun_obj.rotation_euler = (
            math.radians(90.0 - float(sun_elevation)),
            0.0,
            math.radians(float(sun_rotation)),
        )

        scene = bpy.context.scene
        if hasattr(scene, "eevee"):
            scene.eevee.use_ssr = True
            scene.eevee.use_ssr_refraction = True

        return _result(
            True,
            {
                "world": "Nishita Sky",
                "sun_light": sun_obj.name,
                "sun_energy": float(sun_energy),
                "sun_angle_deg": float(sun_angle),
                "sun_elevation_deg": float(sun_elevation),
                "sun_rotation_deg": float(sun_rotation),
                "sky_strength": float(sky_strength),
            },
        )
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


def scene_set_frame_range(frame_start: int, frame_end: int, fps: int = None) -> dict:
    try:
        scene = bpy.context.scene
        fs = int(frame_start)
        fe = int(frame_end)
        if fe < fs:
            return _result(False, None, "frame_end 不能小于 frame_start")
        scene.frame_start = fs
        scene.frame_end = fe
        if scene.frame_current < fs or scene.frame_current > fe:
            scene.frame_current = fs
        changes = {"frame_start": scene.frame_start, "frame_end": scene.frame_end}
        if fps is not None:
            scene.render.fps = int(fps)
            changes["fps"] = scene.render.fps
        return _result(True, changes)
    except Exception as e:
        return _result(False, None, str(e))


def scene_set_current_frame(frame: int) -> dict:
    try:
        scene = bpy.context.scene
        target = int(frame)
        scene.frame_set(target)
        return _result(True, {"frame_current": int(scene.frame_current)})
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


def _resolve_output_path(path: str) -> str:
    p = str(path or "").strip()
    if p.startswith("//"):
        return bpy.path.abspath(p)
    return p


def scene_save_blend(filepath: str, compress: bool = True, make_dirs: bool = True) -> dict:
    try:
        path = _resolve_output_path(filepath)
        if not path:
            return _result(False, None, "filepath 不能为空")
        if not path.lower().endswith(".blend"):
            path = f"{path}.blend"
        folder = os.path.dirname(path)
        if folder and make_dirs:
            os.makedirs(folder, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=path, compress=bool(compress))
        return _result(True, {"saved": True, "filepath": path, "compress": bool(compress)})
    except Exception as e:
        return _result(False, None, str(e))


def scene_export_fbx(filepath: str, use_selection: bool = False, apply_modifiers: bool = True, make_dirs: bool = True) -> dict:
    try:
        path = _resolve_output_path(filepath)
        if not path:
            return _result(False, None, "filepath 不能为空")
        folder = os.path.dirname(path)
        if folder and make_dirs:
            os.makedirs(folder, exist_ok=True)
        bpy.ops.export_scene.fbx(
            filepath=path,
            use_selection=bool(use_selection),
            use_mesh_modifiers=bool(apply_modifiers),
        )
        return _result(True, {"exported": True, "format": "FBX", "filepath": path, "use_selection": bool(use_selection)})
    except Exception as e:
        return _result(False, None, str(e))


def scene_export_gltf(
    filepath: str,
    export_format: str = "GLB",
    use_selection: bool = False,
    make_dirs: bool = True,
) -> dict:
    try:
        path = _resolve_output_path(filepath)
        if not path:
            return _result(False, None, "filepath 不能为空")
        fmt = str(export_format or "GLB").upper()
        if fmt not in {"GLB", "GLTF_SEPARATE", "GLTF_EMBEDDED"}:
            return _result(False, None, f"无效 export_format: {fmt}")
        folder = os.path.dirname(path)
        if folder and make_dirs:
            os.makedirs(folder, exist_ok=True)
        bpy.ops.export_scene.gltf(
            filepath=path,
            export_format=fmt,
            use_selection=bool(use_selection),
        )
        return _result(True, {"exported": True, "format": fmt, "filepath": path, "use_selection": bool(use_selection)})
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


def controller_create_empty(
    name: str = "CTRL",
    location: list = None,
    display_type: str = "PLAIN_AXES",
) -> dict:
    """创建控制器 Empty（官方推荐用于约束/驱动控制）"""
    try:
        loc = tuple(location) if location else (0.0, 0.0, 0.0)
        bpy.ops.object.empty_add(type=display_type, location=loc)
        obj = bpy.context.active_object
        obj.name = name or obj.name
        return _result(True, {"name": obj.name, "location": list(obj.location), "type": obj.empty_display_type})
    except Exception as e:
        return _result(False, None, str(e))


def _controller_add_constraint(
    owner_name: str,
    target_name: str,
    constraint_type: str,
    influence: float = 1.0,
) -> dict:
    if owner_name not in bpy.data.objects:
        return _result(False, None, f"物体不存在: {owner_name}")
    if target_name not in bpy.data.objects:
        return _result(False, None, f"目标不存在: {target_name}")
    owner = bpy.data.objects[owner_name]
    target = bpy.data.objects[target_name]
    c = owner.constraints.new(type=constraint_type)
    c.target = target
    c.influence = max(0.0, min(1.0, float(influence)))
    return _result(True, {"owner": owner_name, "target": target_name, "constraint": c.name, "type": constraint_type, "influence": c.influence})


def controller_add_copy_location(owner_name: str, target_name: str, influence: float = 1.0) -> dict:
    try:
        return _controller_add_constraint(owner_name, target_name, "COPY_LOCATION", influence=influence)
    except Exception as e:
        return _result(False, None, str(e))


def controller_add_copy_rotation(owner_name: str, target_name: str, influence: float = 1.0) -> dict:
    try:
        return _controller_add_constraint(owner_name, target_name, "COPY_ROTATION", influence=influence)
    except Exception as e:
        return _result(False, None, str(e))


def controller_add_copy_scale(owner_name: str, target_name: str, influence: float = 1.0) -> dict:
    try:
        return _controller_add_constraint(owner_name, target_name, "COPY_SCALE", influence=influence)
    except Exception as e:
        return _result(False, None, str(e))


def controller_add_track_to(owner_name: str, target_name: str, track_axis: str = "TRACK_Z", up_axis: str = "UP_Y", influence: float = 1.0) -> dict:
    try:
        result = _controller_add_constraint(owner_name, target_name, "TRACK_TO", influence=influence)
        if not result.get("success"):
            return result
        owner = bpy.data.objects[owner_name]
        c = owner.constraints[-1]
        c.track_axis = track_axis
        c.up_axis = up_axis
        return _result(True, {"owner": owner_name, "target": target_name, "constraint": c.name, "track_axis": c.track_axis, "up_axis": c.up_axis})
    except Exception as e:
        return _result(False, None, str(e))


def controller_add_custom_property(object_name: str, prop_name: str, value: float = 0.0, min_value: float = 0.0, max_value: float = 1.0) -> dict:
    """给对象添加自定义属性（用于驱动控制器）"""
    try:
        if object_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {object_name}")
        obj = bpy.data.objects[object_name]
        obj[prop_name] = float(value)
        try:
            ui = obj.id_properties_ui(prop_name)
            ui.update(min=float(min_value), max=float(max_value), soft_min=float(min_value), soft_max=float(max_value))
        except Exception:
            pass
        return _result(True, {"object": object_name, "property": prop_name, "value": float(obj[prop_name])})
    except Exception as e:
        return _result(False, None, str(e))


def _find_constraint(obj, constraint_name: str = "", constraint_type: str = ""):
    if constraint_name:
        c = obj.constraints.get(constraint_name)
        if c is not None:
            return c
    if constraint_type:
        ctype = str(constraint_type).upper().strip()
        for c in obj.constraints:
            if c.type == ctype:
                return c
    return None


def controller_add_child_of(owner_name: str, target_name: str, influence: float = 1.0, set_inverse: bool = True) -> dict:
    """添加 Child Of 约束（常用于控制器级联）"""
    try:
        result = _controller_add_constraint(owner_name, target_name, "CHILD_OF", influence=influence)
        if not result.get("success"):
            return result
        owner = bpy.data.objects[owner_name]
        c = owner.constraints[-1]
        if set_inverse:
            try:
                mat = owner.matrix_world.copy()
                c.inverse_matrix = bpy.data.objects[target_name].matrix_world.inverted() @ mat
            except Exception:
                pass
        return _result(True, {"owner": owner_name, "target": target_name, "constraint": c.name, "type": c.type, "influence": c.influence})
    except Exception as e:
        return _result(False, None, str(e))


def controller_set_constraint_influence(
    owner_name: str,
    constraint_name: str = "",
    constraint_type: str = "",
    influence: float = 1.0,
) -> dict:
    """设置约束影响值（可按约束名或类型定位）"""
    try:
        if owner_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {owner_name}")
        obj = bpy.data.objects[owner_name]
        c = _find_constraint(obj, constraint_name=constraint_name, constraint_type=constraint_type)
        if c is None:
            return _result(False, None, f"未找到约束: name={constraint_name}, type={constraint_type}")
        c.influence = max(0.0, min(1.0, float(influence)))
        return _result(True, {"owner": owner_name, "constraint": c.name, "type": c.type, "influence": c.influence})
    except Exception as e:
        return _result(False, None, str(e))


def controller_remove_constraint(owner_name: str, constraint_name: str = "", constraint_type: str = "") -> dict:
    """移除约束（可按约束名或类型定位）"""
    try:
        if owner_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {owner_name}")
        obj = bpy.data.objects[owner_name]
        c = _find_constraint(obj, constraint_name=constraint_name, constraint_type=constraint_type)
        if c is None:
            return _result(False, None, f"未找到约束: name={constraint_name}, type={constraint_type}")
        cname = c.name
        obj.constraints.remove(c)
        return _result(True, {"owner": owner_name, "removed_constraint": cname})
    except Exception as e:
        return _result(False, None, str(e))


def object_rename(old_name: str, new_name: str) -> dict:
    try:
        if old_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {old_name}")
        if not new_name or not str(new_name).strip():
            return _result(False, None, "new_name 不能为空")
        obj = bpy.data.objects[old_name]
        obj.name = str(new_name).strip()
        return _result(True, {"old_name": old_name, "new_name": obj.name})
    except Exception as e:
        return _result(False, None, str(e))


def object_select_set_active(object_name: str, select: bool = True) -> dict:
    try:
        if object_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {object_name}")
        bpy.ops.object.select_all(action="DESELECT")
        obj = bpy.data.objects[object_name]
        obj.select_set(bool(select))
        bpy.context.view_layer.objects.active = obj if select else None
        return _result(True, {"object": object_name, "selected": bool(select), "active": bool(select)})
    except Exception as e:
        return _result(False, None, str(e))


def object_duplicate_linked(name: str, new_name: str = "", location: list = None) -> dict:
    try:
        if name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {name}")
        src = bpy.data.objects[name]
        dup = src.copy()
        # linked duplicate: share mesh data block
        dup.data = src.data
        if new_name:
            dup.name = str(new_name).strip()
        if location and len(location) >= 3:
            dup.location = (float(location[0]), float(location[1]), float(location[2]))
        bpy.context.collection.objects.link(dup)
        return _result(True, {"source": name, "duplicate": dup.name, "linked_data": True, "location": list(dup.location)})
    except Exception as e:
        return _result(False, None, str(e))


def _resolve_gn_tree(object_name: str, modifier_name: str = ""):
    if object_name not in bpy.data.objects:
        return None, f"物体不存在: {object_name}"
    obj = bpy.data.objects[object_name]
    mod = None
    if modifier_name:
        mod = obj.modifiers.get(modifier_name)
    if mod is None:
        for m in obj.modifiers:
            if m.type == "NODES":
                mod = m
                break
    if mod is None:
        return None, "未找到 Geometry Nodes 修改器"
    if mod.type != "NODES":
        return None, f"修改器不是 Geometry Nodes: {mod.name}"
    if mod.node_group is None:
        mod.node_group = bpy.data.node_groups.new(name=f"GN_{obj.name}", type="GeometryNodeTree")
        # 初始化 IO
        group = mod.node_group
        nodes = group.nodes
        inp = nodes.new("NodeGroupInput")
        out = nodes.new("NodeGroupOutput")
        inp.location = (-400, 0)
        out.location = (300, 0)
        try:
            if hasattr(group, "interface"):
                group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
                group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
            else:
                group.inputs.new("NodeSocketGeometry", "Geometry")
                group.outputs.new("NodeSocketGeometry", "Geometry")
        except Exception:
            pass
    return mod.node_group, ""


def gn_create_modifier(object_name: str, modifier_name: str = "GeometryNodes") -> dict:
    """给对象创建 Geometry Nodes 修改器并初始化节点组"""
    try:
        if object_name not in bpy.data.objects:
            return _result(False, None, f"物体不存在: {object_name}")
        obj = bpy.data.objects[object_name]
        mod = obj.modifiers.get(modifier_name)
        if mod is None:
            mod = obj.modifiers.new(name=modifier_name, type="NODES")
        group, err = _resolve_gn_tree(object_name, modifier_name=mod.name)
        if group is None:
            return _result(False, None, err)
        return _result(True, {"object": object_name, "modifier": mod.name, "node_group": group.name})
    except Exception as e:
        return _result(False, None, str(e))


def gn_add_node(object_name: str, node_type: str, node_name: str = "", modifier_name: str = "", location: list = None) -> dict:
    try:
        group, err = _resolve_gn_tree(object_name, modifier_name=modifier_name)
        if group is None:
            return _result(False, None, err)
        node = group.nodes.new(node_type)
        if node_name:
            node.name = node_name
            node.label = node_name
        if location and len(location) >= 2:
            node.location = (float(location[0]), float(location[1]))
        return _result(True, {"node": node.name, "type": node.bl_idname, "group": group.name})
    except Exception as e:
        return _result(False, None, str(e))


def gn_link_nodes(
    object_name: str,
    from_node: str,
    from_socket: str,
    to_node: str,
    to_socket: str,
    modifier_name: str = "",
) -> dict:
    try:
        group, err = _resolve_gn_tree(object_name, modifier_name=modifier_name)
        if group is None:
            return _result(False, None, err)
        fn = group.nodes.get(from_node)
        tn = group.nodes.get(to_node)
        if fn is None or tn is None:
            return _result(False, None, f"节点不存在: from={from_node}, to={to_node}")
        fs = fn.outputs.get(from_socket)
        ts = tn.inputs.get(to_socket)
        if fs is None or ts is None:
            return _result(False, None, f"插槽不存在: {from_socket}->{to_socket}")
        group.links.new(fs, ts)
        return _result(True, {"group": group.name, "from": f"{from_node}.{from_socket}", "to": f"{to_node}.{to_socket}"})
    except Exception as e:
        return _result(False, None, str(e))


def gn_set_input_default(
    object_name: str,
    node_name: str,
    input_name: str,
    value,
    modifier_name: str = "",
) -> dict:
    try:
        group, err = _resolve_gn_tree(object_name, modifier_name=modifier_name)
        if group is None:
            return _result(False, None, err)
        node = group.nodes.get(node_name)
        if node is None:
            return _result(False, None, f"节点不存在: {node_name}")
        inp = node.inputs.get(input_name)
        if inp is None:
            return _result(False, None, f"输入不存在: {input_name}")
        if isinstance(value, (list, tuple)):
            for i, v in enumerate(value):
                inp.default_value[i] = v
        else:
            inp.default_value = value
        return _result(True, {"node": node_name, "input": input_name, "value": value})
    except Exception as e:
        return _result(False, None, str(e))


def gn_expose_group_input(
    object_name: str,
    socket_name: str,
    socket_type: str = "NodeSocketFloat",
    default_value=None,
    modifier_name: str = "",
) -> dict:
    try:
        group, err = _resolve_gn_tree(object_name, modifier_name=modifier_name)
        if group is None:
            return _result(False, None, err)
        created = False
        # Blender 4.x interface API
        if hasattr(group, "interface"):
            exists = False
            for item in group.interface.items_tree:
                if getattr(item, "item_type", "") == "SOCKET" and getattr(item, "name", "") == socket_name and getattr(item, "in_out", "") == "INPUT":
                    exists = True
                    break
            if not exists:
                group.interface.new_socket(name=socket_name, in_out="INPUT", socket_type=socket_type)
                created = True
        else:
            if socket_name not in group.inputs:
                group.inputs.new(socket_type, socket_name)
                created = True
        # 设置 Group Input 默认值（若可用）
        for node in group.nodes:
            if node.bl_idname == "NodeGroupInput":
                sock = node.outputs.get(socket_name)
                if sock and default_value is not None:
                    try:
                        sock.default_value = default_value
                    except Exception:
                        pass
                break
        return _result(True, {"group": group.name, "socket": socket_name, "created": created})
    except Exception as e:
        return _result(False, None, str(e))


def gn_get_summary(object_name: str, modifier_name: str = "") -> dict:
    try:
        group, err = _resolve_gn_tree(object_name, modifier_name=modifier_name)
        if group is None:
            return _result(False, None, err)
        nodes = []
        for n in group.nodes:
            nodes.append({"name": n.name, "type": n.bl_idname, "inputs": len(n.inputs), "outputs": len(n.outputs)})
        links = []
        for l in group.links:
            links.append(f"{l.from_node.name}.{l.from_socket.name} -> {l.to_node.name}.{l.to_socket.name}")
        return _result(True, {"group": group.name, "node_count": len(nodes), "link_count": len(links), "nodes": nodes[:120], "links": links[:200]})
    except Exception as e:
        return _result(False, None, str(e))


def gn_remove_node(object_name: str, node_name: str, modifier_name: str = "") -> dict:
    try:
        group, err = _resolve_gn_tree(object_name, modifier_name=modifier_name)
        if group is None:
            return _result(False, None, err)
        node = group.nodes.get(node_name)
        if node is None:
            return _result(False, None, f"节点不存在: {node_name}")
        group.nodes.remove(node)
        return _result(True, {"group": group.name, "removed": node_name})
    except Exception as e:
        return _result(False, None, str(e))


def gn_auto_layout_nodes(object_name: str, modifier_name: str = "", x_gap: float = 220.0, y_gap: float = 140.0) -> dict:
    try:
        group, err = _resolve_gn_tree(object_name, modifier_name=modifier_name)
        if group is None:
            return _result(False, None, err)
        nodes = list(group.nodes)
        if not nodes:
            return _result(True, {"group": group.name, "node_count": 0})
        # 简单按类型分层排布：输入 -> 处理中间 -> 输出
        inputs = [n for n in nodes if "Input" in n.bl_idname]
        outputs = [n for n in nodes if "Output" in n.bl_idname]
        middles = [n for n in nodes if n not in inputs and n not in outputs]
        ordered = inputs + middles + outputs
        for i, n in enumerate(ordered):
            n.location = (float(i) * float(x_gap), -float(i % 3) * float(y_gap))
        return _result(True, {"group": group.name, "node_count": len(nodes), "arranged": [n.name for n in ordered[:80]]})
    except Exception as e:
        return _result(False, None, str(e))


def gn_find_node_by_type(object_name: str, node_type: str, modifier_name: str = "") -> dict:
    try:
        group, err = _resolve_gn_tree(object_name, modifier_name=modifier_name)
        if group is None:
            return _result(False, None, err)
        key = str(node_type or "").strip().lower()
        hits = []
        for n in group.nodes:
            if key in n.bl_idname.lower() or key == n.bl_idname.lower():
                hits.append({"name": n.name, "type": n.bl_idname})
        return _result(True, {"group": group.name, "query": node_type, "count": len(hits), "nodes": hits[:120]})
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
        "scene_apply_modifier": scene_apply_modifier,
        "scene_manage_collection": scene_manage_collection,
        "scene_set_world": scene_set_world,
        "scene_setup_daylight_water": scene_setup_daylight_water,
        "scene_duplicate_object": scene_duplicate_object,
        "scene_parent_object": scene_parent_object,
        "scene_set_visibility": scene_set_visibility,
        "scene_get_render_settings": scene_get_render_settings,
        "scene_set_frame_range": scene_set_frame_range,
        "scene_set_current_frame": scene_set_current_frame,
        "scene_set_render_settings": scene_set_render_settings,
        "scene_save_blend": scene_save_blend,
        "scene_export_fbx": scene_export_fbx,
        "scene_export_gltf": scene_export_gltf,
        "scene_get_object_materials": scene_get_object_materials,
        "scene_get_world_info": scene_get_world_info,
        "scene_list_all_materials": scene_list_all_materials,
        "controller_create_empty": controller_create_empty,
        "controller_add_copy_location": controller_add_copy_location,
        "controller_add_copy_rotation": controller_add_copy_rotation,
        "controller_add_copy_scale": controller_add_copy_scale,
        "controller_add_track_to": controller_add_track_to,
        "controller_add_custom_property": controller_add_custom_property,
        "controller_add_child_of": controller_add_child_of,
        "controller_set_constraint_influence": controller_set_constraint_influence,
        "controller_remove_constraint": controller_remove_constraint,
        "object_rename": object_rename,
        "object_select_set_active": object_select_set_active,
        "object_duplicate_linked": object_duplicate_linked,
        "gn_create_modifier": gn_create_modifier,
        "gn_add_node": gn_add_node,
        "gn_link_nodes": gn_link_nodes,
        "gn_set_input_default": gn_set_input_default,
        "gn_expose_group_input": gn_expose_group_input,
        "gn_get_summary": gn_get_summary,
        "gn_remove_node": gn_remove_node,
        "gn_auto_layout_nodes": gn_auto_layout_nodes,
        "gn_find_node_by_type": gn_find_node_by_type,
    }
    try:
        func = tools_map.get(tool_name)
        if func:
            return func(**arguments)
        return _result(False, None, f"未知场景工具: {tool_name}")
    except Exception as e:
        return _result(False, None, str(e))
