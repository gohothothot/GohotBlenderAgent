import os
import tempfile
import base64
import urllib.request
import json

bpy = None

def init_bpy():
    global bpy
    if bpy is None:
        import bpy as _bpy
        bpy = _bpy


def capture_viewport_screenshot(width: int = 1024, height: int = 768) -> str:
    """
    截取当前 3D 视口并返回 base64 编码的图片
    """
    init_bpy()
    
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, "blender_viewport_capture.png")
    
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    override = bpy.context.copy()
                    override['area'] = area
                    override['region'] = region
                    
                    old_filepath = bpy.context.scene.render.filepath
                    old_res_x = bpy.context.scene.render.resolution_x
                    old_res_y = bpy.context.scene.render.resolution_y
                    old_res_percentage = bpy.context.scene.render.resolution_percentage
                    old_file_format = bpy.context.scene.render.image_settings.file_format
                    
                    bpy.context.scene.render.filepath = filepath
                    bpy.context.scene.render.resolution_x = width
                    bpy.context.scene.render.resolution_y = height
                    bpy.context.scene.render.resolution_percentage = 100
                    bpy.context.scene.render.image_settings.file_format = 'PNG'
                    
                    with bpy.context.temp_override(**override):
                        bpy.ops.render.opengl(write_still=True)
                    
                    bpy.context.scene.render.filepath = old_filepath
                    bpy.context.scene.render.resolution_x = old_res_x
                    bpy.context.scene.render.resolution_y = old_res_y
                    bpy.context.scene.render.resolution_percentage = old_res_percentage
                    bpy.context.scene.render.image_settings.file_format = old_file_format
                    
                    break
            break
    
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        return image_data
    
    return None


def capture_render_preview(width: int = 1024, height: int = 768, samples: int = 32) -> str:
    """
    快速渲染预览并返回 base64 编码的图片
    """
    init_bpy()
    
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, "blender_render_preview.png")
    
    old_filepath = bpy.context.scene.render.filepath
    old_res_x = bpy.context.scene.render.resolution_x
    old_res_y = bpy.context.scene.render.resolution_y
    old_res_percentage = bpy.context.scene.render.resolution_percentage
    old_file_format = bpy.context.scene.render.image_settings.file_format
    
    old_samples = None
    if bpy.context.scene.render.engine == 'CYCLES':
        old_samples = bpy.context.scene.cycles.samples
        bpy.context.scene.cycles.samples = samples
    elif bpy.context.scene.render.engine == 'BLENDER_EEVEE_NEXT':
        old_samples = bpy.context.scene.eevee.taa_render_samples
        bpy.context.scene.eevee.taa_render_samples = samples
    
    bpy.context.scene.render.filepath = filepath
    bpy.context.scene.render.resolution_x = width
    bpy.context.scene.render.resolution_y = height
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    
    bpy.ops.render.render(write_still=True)
    
    bpy.context.scene.render.filepath = old_filepath
    bpy.context.scene.render.resolution_x = old_res_x
    bpy.context.scene.render.resolution_y = old_res_y
    bpy.context.scene.render.resolution_percentage = old_res_percentage
    bpy.context.scene.render.image_settings.file_format = old_file_format
    
    if old_samples is not None:
        if bpy.context.scene.render.engine == 'CYCLES':
            bpy.context.scene.cycles.samples = old_samples
        elif bpy.context.scene.render.engine == 'BLENDER_EEVEE_NEXT':
            bpy.context.scene.eevee.taa_render_samples = old_samples
    
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        return image_data
    
    return None


def get_scene_info() -> dict:
    """
    获取当前场景的详细信息
    """
    init_bpy()
    
    scene = bpy.context.scene
    
    objects_info = []
    for obj in scene.objects:
        obj_info = {
            "name": obj.name,
            "type": obj.type,
            "location": [round(v, 3) for v in obj.location],
            "visible": obj.visible_get(),
        }
        if obj.type == 'MESH':
            obj_info["vertices"] = len(obj.data.vertices)
            obj_info["faces"] = len(obj.data.polygons)
            obj_info["materials"] = [mat.name for mat in obj.data.materials if mat]
        elif obj.type == 'LIGHT':
            obj_info["light_type"] = obj.data.type
            obj_info["energy"] = obj.data.energy
        elif obj.type == 'CAMERA':
            obj_info["lens"] = obj.data.lens
        objects_info.append(obj_info)
    
    render_info = {
        "engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "resolution_percentage": scene.render.resolution_percentage,
        "fps": scene.render.fps,
        "frame_range": [scene.frame_start, scene.frame_end],
        "current_frame": scene.frame_current,
    }
    
    if scene.render.engine == 'CYCLES':
        render_info["samples"] = scene.cycles.samples
        render_info["device"] = scene.cycles.device
    elif scene.render.engine == 'BLENDER_EEVEE_NEXT':
        render_info["samples"] = scene.eevee.taa_render_samples
    
    world_info = None
    if scene.world:
        world_info = {
            "name": scene.world.name,
            "use_nodes": scene.world.use_nodes,
        }
    
    return {
        "objects_count": len(scene.objects),
        "objects": objects_info,
        "render": render_info,
        "world": world_info,
    }


def setup_render_settings(
    engine: str = None,
    resolution_x: int = None,
    resolution_y: int = None,
    samples: int = None,
    output_path: str = None,
    file_format: str = None,
    use_gpu: bool = None,
) -> dict:
    """
    设置渲染参数
    """
    init_bpy()
    
    scene = bpy.context.scene
    changes = []
    
    if engine:
        engine_map = {
            "cycles": "CYCLES",
            "eevee": "BLENDER_EEVEE_NEXT",
            "workbench": "BLENDER_WORKBENCH",
        }
        engine_id = engine_map.get(engine.lower(), engine.upper())
        scene.render.engine = engine_id
        changes.append(f"渲染引擎: {engine_id}")
    
    if resolution_x:
        scene.render.resolution_x = resolution_x
        changes.append(f"分辨率宽: {resolution_x}")
    
    if resolution_y:
        scene.render.resolution_y = resolution_y
        changes.append(f"分辨率高: {resolution_y}")
    
    if samples:
        if scene.render.engine == 'CYCLES':
            scene.cycles.samples = samples
        elif scene.render.engine == 'BLENDER_EEVEE_NEXT':
            scene.eevee.taa_render_samples = samples
        changes.append(f"采样数: {samples}")
    
    if output_path:
        scene.render.filepath = output_path
        changes.append(f"输出路径: {output_path}")
    
    if file_format:
        format_map = {
            "png": "PNG",
            "jpg": "JPEG",
            "jpeg": "JPEG",
            "exr": "OPEN_EXR",
            "tiff": "TIFF",
        }
        fmt = format_map.get(file_format.lower(), file_format.upper())
        scene.render.image_settings.file_format = fmt
        changes.append(f"文件格式: {fmt}")
    
    if use_gpu is not None and scene.render.engine == 'CYCLES':
        scene.cycles.device = 'GPU' if use_gpu else 'CPU'
        changes.append(f"设备: {'GPU' if use_gpu else 'CPU'}")
    
    return {
        "success": True,
        "result": f"渲染设置已更新: {', '.join(changes)}",
        "error": None,
    }


def render_image(output_path: str = None) -> dict:
    """
    执行渲染并保存图片
    """
    init_bpy()
    
    scene = bpy.context.scene
    
    if output_path:
        scene.render.filepath = output_path
    
    if not scene.render.filepath:
        temp_dir = tempfile.gettempdir()
        scene.render.filepath = os.path.join(temp_dir, "blender_render_output.png")
    
    bpy.ops.render.render(write_still=True)
    
    return {
        "success": True,
        "result": f"渲染完成，已保存到: {scene.render.filepath}",
        "output_path": scene.render.filepath,
        "error": None,
    }


def render_animation(output_path: str = None) -> dict:
    """
    渲染动画序列
    """
    init_bpy()
    
    scene = bpy.context.scene
    
    if output_path:
        scene.render.filepath = output_path
    
    bpy.ops.render.render(animation=True)
    
    return {
        "success": True,
        "result": f"动画渲染完成，帧范围: {scene.frame_start}-{scene.frame_end}",
        "output_path": scene.render.filepath,
        "error": None,
    }
