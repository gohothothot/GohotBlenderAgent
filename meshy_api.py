import json
import urllib.request
import urllib.error
import os
import tempfile
import threading
import time
from typing import Callable, Optional

bpy = None

def init_bpy():
    global bpy
    if bpy is None:
        import bpy as _bpy
        bpy = _bpy


MESHY_API_BASE = "https://api.meshy.ai"


class MeshyTask:
    def __init__(self, task_id: str, task_type: str):
        self.task_id = task_id
        self.task_type = task_type
        self.status = "PENDING"
        self.progress = 0
        self.model_urls = {}
        self.texture_urls = []
        self.error_message = ""
        self.thumbnail_url = ""


class MeshyAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.active_tasks = {}
        self.on_task_update: Optional[Callable[[MeshyTask], None]] = None
        self.on_task_complete: Optional[Callable[[MeshyTask], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        url = f"{MESHY_API_BASE}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if data:
            body = json.dumps(data).encode("utf-8")
        else:
            body = None

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise Exception(f"Meshy API 错误 {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise Exception(f"网络错误: {e.reason}")

    def text_to_3d_preview(self, prompt: str, ai_model: str = "meshy-6") -> str:
        data = {
            "mode": "preview",
            "prompt": prompt,
            "ai_model": ai_model,
        }
        result = self._request("POST", "/openapi/v2/text-to-3d", data)
        task_id = result.get("result")
        
        task = MeshyTask(task_id, "text-to-3d-preview")
        self.active_tasks[task_id] = task
        
        self._start_polling(task_id, "/openapi/v2/text-to-3d")
        return task_id

    def text_to_3d_refine(self, preview_task_id: str, enable_pbr: bool = True) -> str:
        data = {
            "mode": "refine",
            "preview_task_id": preview_task_id,
            "enable_pbr": enable_pbr,
        }
        result = self._request("POST", "/openapi/v2/text-to-3d", data)
        task_id = result.get("result")
        
        task = MeshyTask(task_id, "text-to-3d-refine")
        self.active_tasks[task_id] = task
        
        self._start_polling(task_id, "/openapi/v2/text-to-3d")
        return task_id

    def image_to_3d(self, image_url: str, enable_pbr: bool = True, ai_model: str = "meshy-6") -> str:
        data = {
            "image_url": image_url,
            "enable_pbr": enable_pbr,
            "ai_model": ai_model,
            "should_texture": True,
        }
        result = self._request("POST", "/openapi/v1/image-to-3d", data)
        task_id = result.get("result")
        
        task = MeshyTask(task_id, "image-to-3d")
        self.active_tasks[task_id] = task
        
        self._start_polling(task_id, "/openapi/v1/image-to-3d")
        return task_id

    def get_task_status(self, task_id: str, endpoint_base: str) -> dict:
        return self._request("GET", f"{endpoint_base}/{task_id}")

    def _start_polling(self, task_id: str, endpoint_base: str):
        def poll():
            while True:
                try:
                    status = self.get_task_status(task_id, endpoint_base)
                    task = self.active_tasks.get(task_id)
                    if not task:
                        break

                    task.status = status.get("status", "UNKNOWN")
                    task.progress = status.get("progress", 0)
                    task.model_urls = status.get("model_urls", {})
                    task.texture_urls = status.get("texture_urls", [])
                    task.thumbnail_url = status.get("thumbnail_url", "")

                    if task.status == "FAILED":
                        task.error_message = status.get("task_error", {}).get("message", "未知错误")
                        if self.on_error:
                            self._safe_callback(self.on_error, f"Meshy 任务失败: {task.error_message}")
                        break

                    if self.on_task_update:
                        self._safe_callback(self.on_task_update, task)

                    if task.status == "SUCCEEDED":
                        if self.on_task_complete:
                            self._safe_callback(self.on_task_complete, task)
                        break

                    time.sleep(3)

                except Exception as e:
                    if self.on_error:
                        self._safe_callback(self.on_error, str(e))
                    break

        thread = threading.Thread(target=poll, daemon=True)
        thread.start()

    def _safe_callback(self, callback, *args):
        init_bpy()
        def do_callback():
            try:
                callback(*args)
            except Exception as e:
                print(f"[Meshy] 回调错误: {e}")
            return None
        bpy.app.timers.register(do_callback)


def download_and_import_model(glb_url: str, model_name: str = "MeshyModel", texture_urls: list = None) -> dict:
    init_bpy()
    
    try:
        temp_dir = tempfile.gettempdir()
        meshy_dir = os.path.join(temp_dir, "meshy_models")
        os.makedirs(meshy_dir, exist_ok=True)
        
        file_path = os.path.join(meshy_dir, f"{model_name}.glb")

        req = urllib.request.Request(glb_url)
        with urllib.request.urlopen(req, timeout=120) as response:
            with open(file_path, "wb") as f:
                f.write(response.read())

        bpy.ops.import_scene.gltf(filepath=file_path)

        imported_objects = bpy.context.selected_objects
        
        if imported_objects and texture_urls:
            mesh_objects = [obj for obj in imported_objects if obj.type == 'MESH']
            if mesh_objects:
                mat = create_pbr_material_from_textures(model_name, texture_urls, meshy_dir)
                if mat:
                    for obj in mesh_objects:
                        if obj.data.materials:
                            obj.data.materials[0] = mat
                        else:
                            obj.data.materials.append(mat)

        if imported_objects:
            for obj in imported_objects:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = imported_objects[0]

        return {
            "success": True,
            "result": f"模型已导入: {model_name}，共 {len(imported_objects)} 个对象",
            "file_path": file_path,
            "objects": [obj.name for obj in imported_objects],
        }

    except Exception as e:
        return {
            "success": False,
            "result": None,
            "error": f"下载或导入失败: {str(e)}",
        }


def create_pbr_material_from_textures(model_name: str, texture_urls: list, save_dir: str):
    init_bpy()
    
    if not texture_urls or len(texture_urls) == 0:
        return None
    
    tex_data = texture_urls[0] if isinstance(texture_urls, list) else texture_urls
    
    mat = bpy.data.materials.new(name=f"{model_name}_Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    nodes.clear()
    
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 0)
    
    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (300, 0)
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    
    x_offset = -600
    y_offset = 300
    
    base_color_url = tex_data.get("base_color")
    if base_color_url:
        tex_path = download_texture(base_color_url, save_dir, f"{model_name}_basecolor")
        if tex_path:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.location = (x_offset, y_offset)
            tex_node.image = bpy.data.images.load(tex_path)
            tex_node.image.colorspace_settings.name = 'sRGB'
            links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
            y_offset -= 300
    
    metallic_url = tex_data.get("metallic")
    if metallic_url:
        tex_path = download_texture(metallic_url, save_dir, f"{model_name}_metallic")
        if tex_path:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.location = (x_offset, y_offset)
            tex_node.image = bpy.data.images.load(tex_path)
            tex_node.image.colorspace_settings.name = 'Non-Color'
            links.new(tex_node.outputs['Color'], bsdf.inputs['Metallic'])
            y_offset -= 300
    
    roughness_url = tex_data.get("roughness")
    if roughness_url:
        tex_path = download_texture(roughness_url, save_dir, f"{model_name}_roughness")
        if tex_path:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.location = (x_offset, y_offset)
            tex_node.image = bpy.data.images.load(tex_path)
            tex_node.image.colorspace_settings.name = 'Non-Color'
            links.new(tex_node.outputs['Color'], bsdf.inputs['Roughness'])
            y_offset -= 300
    
    normal_url = tex_data.get("normal")
    if normal_url:
        tex_path = download_texture(normal_url, save_dir, f"{model_name}_normal")
        if tex_path:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.location = (x_offset - 200, y_offset)
            tex_node.image = bpy.data.images.load(tex_path)
            tex_node.image.colorspace_settings.name = 'Non-Color'
            
            normal_map = nodes.new('ShaderNodeNormalMap')
            normal_map.location = (x_offset + 100, y_offset)
            
            links.new(tex_node.outputs['Color'], normal_map.inputs['Color'])
            links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])
    
    return mat


def download_texture(url: str, save_dir: str, name: str) -> str:
    try:
        ext = ".png"
        if ".jpg" in url.lower() or ".jpeg" in url.lower():
            ext = ".jpg"
        
        file_path = os.path.join(save_dir, f"{name}{ext}")
        
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(file_path, "wb") as f:
                f.write(response.read())
        
        return file_path
    except Exception as e:
        print(f"[Meshy] 下载贴图失败 {name}: {e}")
        return None


_meshy_api = None

def get_meshy_api() -> Optional[MeshyAPI]:
    global _meshy_api
    init_bpy()
    
    try:
        prefs = bpy.context.preferences.addons["blender_mcp"].preferences
        if not prefs.meshy_api_key:
            return None
        
        if _meshy_api is None or _meshy_api.api_key != prefs.meshy_api_key:
            _meshy_api = MeshyAPI(prefs.meshy_api_key)
        
        return _meshy_api
    except:
        return None


def reset_meshy_api():
    global _meshy_api
    _meshy_api = None
