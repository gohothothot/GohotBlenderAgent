import json
import threading
import urllib.request
import urllib.error
import os
from datetime import datetime
from typing import Callable, Optional

bpy = None

LOG_FILE = os.path.join(os.path.dirname(__file__), "agent_error.log")


def init_bpy():
    global bpy
    if bpy is None:
        import bpy as _bpy
        bpy = _bpy


def log_error(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}\n"
    print(f"[Agent Error] {message}")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except:
        pass


def log_debug(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [DEBUG] {message}\n"
    print(f"[Agent Debug] {message}")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except:
        pass


class BlenderAgent:
    def __init__(self, api_base: str, api_key: str, model: str):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.conversation_history = []
        self.max_history = 20

        self.on_message: Optional[Callable[[str, str], None]] = None
        self.on_tool_call: Optional[Callable[[str, dict], None]] = None
        self.on_code_confirm: Optional[Callable[[str, str, Callable], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

        self.system_prompt = """你是 Gohot Blender Agent，一个专业的 Blender 3D 助手。

=== 核心规则 ===
严格禁止使用 execute_python！所有操作必须通过 MCP 工具完成，绝不生成 Python 脚本。

=== 完整工具集 ===

物体操作：list_objects, create_primitive, delete_object, transform_object, get_object_info
场景操作：scene_add_light, scene_modify_light, scene_add_camera, scene_set_active_camera, scene_set_world, scene_duplicate_object, scene_parent_object, scene_set_visibility
场景检查：scene_get_render_settings, scene_set_render_settings, scene_get_object_materials, scene_get_world_info, scene_list_all_materials
修改器：scene_add_modifier, scene_set_modifier_param, scene_remove_modifier
集合：scene_manage_collection(action=create/delete/move_object/list)
材质基础：set_material, set_metallic_roughness

着色器节点（核心）：
  创建/删除：shader_create_material, shader_delete_material, shader_assign_material
  查询：shader_list_materials, shader_inspect_nodes, shader_get_node_sockets, shader_get_material_summary, shader_list_available_nodes
  节点操作：shader_add_node, shader_delete_node, shader_set_node_input, shader_set_node_property
  连接：shader_link_nodes, shader_unlink_nodes
  批量操作：shader_batch_add_nodes, shader_batch_link_nodes, shader_clear_nodes
  ColorRamp：shader_colorramp_add_stop, shader_colorramp_remove_stop, shader_colorramp_set_interpolation
  预设：shader_create_procedural_material(preset: wood/marble/metal_scratched/gold/glass/brick/fabric/rubber/concrete/plastic/water/ice/lava/crystal/snow/leather/neon/emissive)
  卡通：shader_create_toon_material, shader_convert_to_toon
  EEVEE：shader_configure_eevee — 透射材质必须调用！
  预览：shader_preview_material

动画：anim_add_uv_scroll, anim_add_uv_rotate, anim_add_uv_scale, anim_add_value_driver, anim_add_keyframe, anim_remove_driver
AI生成：meshy_text_to_3d, meshy_image_to_3d
场景分析：analyze_scene, get_scene_info
渲染：setup_render, render_image
知识库：kb_search, kb_save
联网搜索：web_search, web_fetch, web_search_blender, web_analyze_reference
日志：get_action_log
TODO：get_todo_list, complete_todo

=== 所有 Blender 着色器节点类型 ===
shader_add_node 支持所有 Blender 节点类型，常用的包括：

Shader: ShaderNodeBsdfPrincipled, ShaderNodeBsdfDiffuse, ShaderNodeBsdfGlossy, ShaderNodeBsdfGlass, ShaderNodeBsdfRefraction, ShaderNodeBsdfTransparent, ShaderNodeBsdfTranslucent, ShaderNodeBsdfAnisotropic, ShaderNodeBsdfToon, ShaderNodeBsdfVelvet, ShaderNodeSubsurfaceScattering, ShaderNodeEmission, ShaderNodeBackground, ShaderNodeHoldout, ShaderNodeAddShader, ShaderNodeMixShader, ShaderNodeVolumeAbsorption, ShaderNodeVolumeScatter, ShaderNodeVolumePrincipled
Texture: ShaderNodeTexImage, ShaderNodeTexEnvironment, ShaderNodeTexNoise, ShaderNodeTexVoronoi, ShaderNodeTexWave, ShaderNodeTexMusgrave, ShaderNodeTexGradient, ShaderNodeTexMagic, ShaderNodeTexChecker, ShaderNodeTexBrick, ShaderNodeTexWhiteNoise, ShaderNodeTexSky, ShaderNodeTexIES
Color: ShaderNodeMix, ShaderNodeMixRGB, ShaderNodeRGBCurve, ShaderNodeInvert, ShaderNodeHueSaturation, ShaderNodeBrightContrast, ShaderNodeGamma, ShaderNodeLightFalloff
Vector: ShaderNodeMapping, ShaderNodeNormalMap, ShaderNodeNormal, ShaderNodeBump, ShaderNodeDisplacement, ShaderNodeVectorDisplacement, ShaderNodeVectorCurve, ShaderNodeVectorMath, ShaderNodeVectorRotate, ShaderNodeVectorTransform
Converter: ShaderNodeMath, ShaderNodeMapRange, ShaderNodeClamp, ShaderNodeValToRGB, ShaderNodeRGBToBW, ShaderNodeSeparateXYZ, ShaderNodeCombineXYZ, ShaderNodeSeparateColor, ShaderNodeCombineColor, ShaderNodeShaderToRGB, ShaderNodeBlackbody, ShaderNodeWavelength
Input: ShaderNodeTexCoord, ShaderNodeUVMap, ShaderNodeAttribute, ShaderNodeVertexColor, ShaderNodeObjectInfo, ShaderNodeCameraData, ShaderNodeLightPath, ShaderNodeFresnel, ShaderNodeLayerWeight, ShaderNodeNewGeometry, ShaderNodeWireframe, ShaderNodeTangent, ShaderNodeAmbientOcclusion, ShaderNodeBevel, ShaderNodeValue, ShaderNodeRGB
Output: ShaderNodeOutputMaterial, ShaderNodeOutputWorld, ShaderNodeOutputLight

不确定节点有哪些 socket？用 shader_get_node_sockets 查看！
不确定有哪些节点可用？用 shader_list_available_nodes 查看！

=== 工作流程（必须遵守！）===

收到需求后，严格按以下顺序：

1. 分析需求：理解用户想要什么效果
2. 查参考：如果用户提供了链接，用 web_analyze_reference 分析；如果是复杂材质，用 web_search_blender 搜索教程
3. 查知识库：kb_search 搜索本地是否有相关经验
4. 查现状：scene_get_render_settings / shader_inspect_nodes / scene_get_object_materials 了解当前状态
5. 规划：确定需要哪些节点和连接
6. 执行：用 shader_batch_add_nodes + shader_batch_link_nodes 高效构建节点图
7. 验证：shader_get_material_summary 检查结果 / shader_preview_material 预览
8. 对比：如果有参考效果，对比当前结果与参考的差异
9. 调整：如果效果不对，分析原因并修改（检查连接、参数、渲染设置）
10. 保存：kb_save 保存成功的配方

=== 自我审查规则 ===
- 执行完材质操作后，必须用 shader_get_material_summary 或 shader_inspect_nodes 检查结果
- 如果涉及透射材质，必须检查 scene_get_render_settings 确认 SSR 已开启
- 如果效果不对，不要重复同样的操作，要分析原因后调整
- 不确定参数时，先搜索再操作，绝不猜测

=== 关键知识 ===

Principled BSDF 输入（Blender 5.0）：
  Base Color, Metallic, Roughness, IOR, Alpha,
  Transmission Weight(旧版叫Transmission), Subsurface Weight(旧版叫Subsurface), Subsurface Radius,
  Emission Color, Emission Strength, Normal, Coat Weight, Sheen Weight

透射材质（水/玻璃/冰/水晶）：
  Transmission Weight=1.0, 设置IOR(水1.333/玻璃1.45/冰1.31/钻石2.42)
  EEVEE 必须调用 shader_configure_eevee！否则显示黑色
  水材质：浅蓝色Base Color + Transmission + 低Roughness + Noise→Bump做波纹
  玻璃：白色Base Color + Transmission + IOR 1.45 + 极低Roughness
  冰：浅蓝Base Color + Transmission + IOR 1.31 + Voronoi→Bump做裂纹

复杂材质构建策略：
  1. 用 shader_clear_nodes 清理
  2. 用 shader_batch_add_nodes 一次创建所有节点
  3. 用 shader_batch_link_nodes 一次创建所有连接
  4. 用 shader_set_node_input 微调参数
  5. 用 shader_get_material_summary 验证

卡通渲染：ShaderToRGB → ColorRamp(CONSTANT) → Emission输出
Driver表达式：frame*0.01(线性), sin(frame*0.1)(波动)
二次元工作流：meshy_text_to_3d → shader_list_materials → shader_convert_to_toon

=== 使用规则 ===
- 绝对禁止 execute_python，所有操作用 MCP 工具
- 材质用 shader_ 工具，动画用 anim_ 工具，场景用 scene_ 工具
- 用户提供链接时，先用 web_analyze_reference 分析
- 每次操作后告知结果和可调参数
- 回复简洁"""

    def _get_tools(self):
        from . import tools
        return tools.TOOLS

    def _call_api(self, messages: list, tools: list = None) -> dict:
        if "/v1" in self.api_base:
            url = f"{self.api_base}/messages"
        else:
            url = f"{self.api_base}/v1/messages"

        log_debug(f"API URL: {url}")
        log_debug(f"Model: {self.model}")

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": self.system_prompt,
            "messages": messages,
        }

        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            log_debug("Sending API request...")
            with urllib.request.urlopen(req, timeout=120) as response:
                response_text = response.read().decode("utf-8")
                log_debug(f"API response received, length: {len(response_text)}")
                return json.loads(response_text)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            error_msg = f"API HTTP错误 {e.code}: {error_body}"
            log_error(error_msg)
            raise Exception(error_msg)
        except urllib.error.URLError as e:
            error_msg = f"网络错误: {e.reason}"
            log_error(error_msg)
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            log_error(error_msg)
            raise Exception(error_msg)

    def send_message(self, user_message: str):
        thread = threading.Thread(target=self._process_message, args=(user_message,))
        thread.daemon = True
        thread.start()

    def _process_message(self, user_message: str):
        try:
            from . import action_log
            action_log.start_session(user_message)
            action_log.log_agent_message("user", user_message)

            log_debug(f"Processing message: {user_message[:50]}...")
            self.conversation_history.append({"role": "user", "content": user_message})

            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history * 2:]

            response = self._call_api(
                messages=self.conversation_history, tools=self._get_tools()
            )

            self._handle_response(response)

        except Exception as e:
            error_msg = str(e)
            log_error(f"Process message error: {error_msg}")
            if self.on_error:
                self._safe_callback(self.on_error, error_msg)

    def _handle_response(self, response: dict):
        content_blocks = response.get("content", [])

        text_parts = []
        tool_uses = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_uses.append(block)

        if text_parts:
            full_text = "".join(text_parts)
            if self.on_message:
                self._safe_callback(self.on_message, "assistant", full_text)
            try:
                from . import action_log
                action_log.log_agent_message("assistant", full_text)
            except Exception:
                pass

        if tool_uses:
            self.conversation_history.append(
                {"role": "assistant", "content": content_blocks}
            )
            self._execute_tools(tool_uses)
        else:
            if text_parts:
                self.conversation_history.append(
                    {"role": "assistant", "content": "".join(text_parts)}
                )
            try:
                from . import action_log
                action_log.end_session("".join(text_parts)[:200] if text_parts else "")
            except Exception:
                pass

    def _execute_tools(self, tool_uses: list):
        from . import tools

        tool_results = []

        for tool_use in tool_uses:
            tool_id = tool_use.get("id")
            tool_name = tool_use.get("name")
            tool_input = tool_use.get("input", {})

            log_debug(f"Executing tool: {tool_name}")

            if self.on_tool_call:
                self._safe_callback(self.on_tool_call, tool_name, tool_input)

            result = self._execute_in_main_thread(
                tools.execute_tool, tool_name, tool_input
            )

            try:
                from . import action_log
                action_log.log_tool_call(tool_name, tool_input, result)
            except Exception:
                pass

            if result.get("result") == "NEEDS_CONFIRMATION":
                if self.on_code_confirm:
                    self._safe_callback(
                        self.on_code_confirm,
                        result.get("code"),
                        result.get("description"),
                        lambda approved, tid=tool_id, code=result.get("code"): 
                            self._on_code_confirmed(approved, tid, code),
                    )
                return

            if result.get("result") == "NEEDS_VISION_ANALYSIS":
                self._handle_vision_analysis(
                    tool_id,
                    result.get("image_data"),
                    result.get("scene_info"),
                    result.get("question"),
                )
                return

            if result.get("success"):
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result.get("result"), ensure_ascii=False),
                })
            else:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": f"错误: {result.get('error')}",
                    "is_error": True,
                })

        if tool_results:
            self._continue_with_tool_results(tool_results)

    def _on_code_confirmed(self, approved: bool, tool_id: str, code: str):
        from . import tools

        if approved:
            result = self._execute_in_main_thread(tools.execute_python_code, code)

            if result.get("success"):
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": f"代码执行成功: {result.get('result')}",
                }
            else:
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": f"代码执行失败: {result.get('error')}",
                    "is_error": True,
                }
        else:
            tool_result = {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": "用户拒绝执行此代码",
                "is_error": True,
            }

        self._continue_with_tool_results([tool_result])

    def _handle_vision_analysis(self, tool_id: str, image_data: str, scene_info: dict, question: str):
        try:
            vision_message = {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"这是当前 Blender 场景的截图。\n\n场景信息：{json.dumps(scene_info, ensure_ascii=False, indent=2)}\n\n用户问题：{question}\n\n请分析这个场景并回答用户的问题，给出具体的建议。",
                    },
                ],
            }

            temp_history = self.conversation_history.copy()
            temp_history.append(vision_message)

            response = self._call_api(messages=temp_history, tools=None)

            analysis_text = ""
            for block in response.get("content", []):
                if block.get("type") == "text":
                    analysis_text += block.get("text", "")

            tool_result = {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": analysis_text,
            }

            self._continue_with_tool_results([tool_result])

        except Exception as e:
            log_error(f"Vision analysis error: {str(e)}")
            tool_result = {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": f"场景分析失败: {str(e)}",
                "is_error": True,
            }
            self._continue_with_tool_results([tool_result])

    def _continue_with_tool_results(self, tool_results: list):
        try:
            self.conversation_history.append({"role": "user", "content": tool_results})

            response = self._call_api(
                messages=self.conversation_history, tools=self._get_tools()
            )

            self._handle_response(response)

        except Exception as e:
            log_error(f"Continue with tool results error: {str(e)}")
            if self.on_error:
                self._safe_callback(self.on_error, str(e))

    def _execute_in_main_thread(self, func, *args):
        init_bpy()
        import queue
        result_queue = queue.Queue()

        def do_execute():
            try:
                result = func(*args)
                result_queue.put(result)
            except Exception as e:
                log_error(f"Main thread execution error: {str(e)}")
                result_queue.put({"success": False, "result": None, "error": str(e)})
            return None

        bpy.app.timers.register(do_execute)

        try:
            return result_queue.get(timeout=30.0)
        except:
            return {"success": False, "result": None, "error": "操作超时"}

    def _safe_callback(self, callback, *args):
        init_bpy()

        def do_callback():
            try:
                callback(*args)
            except Exception as e:
                log_error(f"Callback error: {str(e)}")
            return None

        bpy.app.timers.register(do_callback)

    def clear_history(self):
        self.conversation_history = []
        log_debug("Conversation history cleared")
