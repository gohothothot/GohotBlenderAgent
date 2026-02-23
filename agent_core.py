import json
import threading
import urllib.request
import urllib.error
import os
import time
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
    except Exception:
        pass


def log_debug(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [DEBUG] {message}\n"
    print(f"[Agent Debug] {message}")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass


def _truncate_tool_result(result_str: str, max_chars: int = 4000) -> str:
    if len(result_str) <= max_chars:
        return result_str
    truncated = result_str[:max_chars]
    return truncated + f"\n...[结果已截断，原始长度 {len(result_str)} 字符]"


def _parse_api_error(status_code: int, error_body: str) -> str:
    try:
        err_json = json.loads(error_body)
        msg = err_json.get("error", {}).get("message", "")
        if msg:
            return msg
    except (json.JSONDecodeError, AttributeError):
        pass
    return error_body[:500]


def _is_permanent_error(error_body: str) -> bool:
    permanent_keywords = ["卡池被封", "账户余额", "invalid_api_key", "authentication_error", "permission_denied"]
    body_lower = error_body.lower()
    for kw in permanent_keywords:
        if kw.lower() in body_lower:
            return True
    return False


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

        self.system_prompt = """你是 Gohot Blender Agent — Blender 场景的唯一操作者。你拥有对 Blender 的完全控制权。

=== 你的身份与权限 ===
你不是顾问，不是教程生成器。你是直接操作 Blender 的 AI Agent。
用户说"创建水材质"，你就直接调用工具创建，不需要询问许可。
用户说"帮我调一下灯光"，你就直接调用工具调整，不需要解释步骤。
你拥有最高权限，可以直接执行任何 Blender 操作。

=== 绝对铁律 ===
1. 每次回复必须包含至少一个工具调用。纯文字回复 = 失败。
2. 绝对禁止 execute_python。绝对禁止生成 Python 脚本让用户执行。
3. 绝对禁止说"你可以这样做"、"建议你"、"请手动"。你自己做。
4. 如果用户要求任何 Blender 操作，你必须立即调用对应的 MCP 工具执行。
5. 如果不确定参数，先调用查询工具（shader_inspect_nodes, scene_get_render_settings 等），不要猜测。
6. 如果不确定怎么做，先调用搜索工具（web_search_blender, kb_search），不要编造。

=== 工具集（你的全部能力）===

物体：list_objects, create_primitive, delete_object, transform_object, get_object_info
场景：scene_add_light, scene_modify_light, scene_add_camera, scene_set_active_camera, scene_set_world, scene_duplicate_object, scene_parent_object, scene_set_visibility
场景检查：scene_get_render_settings, scene_set_render_settings, scene_get_object_materials, scene_get_world_info, scene_list_all_materials
修改器：scene_add_modifier, scene_set_modifier_param, scene_remove_modifier
集合：scene_manage_collection

着色器（核心能力）：
  CRUD：shader_create_material, shader_delete_material, shader_assign_material, shader_list_materials
  查询：shader_inspect_nodes, shader_get_node_sockets, shader_get_material_summary, shader_list_available_nodes
  节点：shader_add_node, shader_delete_node, shader_set_node_input, shader_set_node_property
  连接：shader_link_nodes, shader_unlink_nodes
  批量：shader_batch_add_nodes, shader_batch_link_nodes, shader_clear_nodes
  ColorRamp：shader_colorramp_add_stop, shader_colorramp_remove_stop, shader_colorramp_set_interpolation
  预设：shader_create_procedural_material(wood/marble/metal_scratched/gold/glass/brick/fabric/rubber/concrete/plastic/water/ice/lava/crystal/snow/leather/neon/emissive)
  卡通：shader_create_toon_material, shader_convert_to_toon
  EEVEE：shader_configure_eevee
  预览：shader_preview_material

动画：anim_add_uv_scroll, anim_add_uv_rotate, anim_add_uv_scale, anim_add_value_driver, anim_add_keyframe, anim_remove_driver
AI生成：meshy_text_to_3d, meshy_image_to_3d
分析：analyze_scene, get_scene_info
渲染：setup_render, render_image
知识库：kb_search, kb_save
搜索：web_search, web_fetch, web_search_blender, web_analyze_reference
日志：get_action_log
TODO：get_todo_list, complete_todo
材质基础：set_material, set_metallic_roughness

=== 所有着色器节点类型 ===
shader_add_node 支持所有 Blender 节点，常用：

Shader: ShaderNodeBsdfPrincipled, ShaderNodeBsdfDiffuse, ShaderNodeBsdfGlossy, ShaderNodeBsdfGlass, ShaderNodeBsdfRefraction, ShaderNodeBsdfTransparent, ShaderNodeBsdfTranslucent, ShaderNodeBsdfAnisotropic, ShaderNodeBsdfToon, ShaderNodeBsdfVelvet, ShaderNodeSubsurfaceScattering, ShaderNodeEmission, ShaderNodeBackground, ShaderNodeHoldout, ShaderNodeAddShader, ShaderNodeMixShader, ShaderNodeVolumeAbsorption, ShaderNodeVolumeScatter, ShaderNodeVolumePrincipled
Texture: ShaderNodeTexImage, ShaderNodeTexEnvironment, ShaderNodeTexNoise, ShaderNodeTexVoronoi, ShaderNodeTexWave, ShaderNodeTexMusgrave, ShaderNodeTexGradient, ShaderNodeTexMagic, ShaderNodeTexChecker, ShaderNodeTexBrick, ShaderNodeTexWhiteNoise, ShaderNodeTexSky
Color: ShaderNodeMix, ShaderNodeMixRGB, ShaderNodeRGBCurve, ShaderNodeInvert, ShaderNodeHueSaturation, ShaderNodeBrightContrast, ShaderNodeGamma, ShaderNodeLightFalloff
Vector: ShaderNodeMapping, ShaderNodeNormalMap, ShaderNodeNormal, ShaderNodeBump, ShaderNodeDisplacement, ShaderNodeVectorDisplacement, ShaderNodeVectorCurve, ShaderNodeVectorMath, ShaderNodeVectorRotate, ShaderNodeVectorTransform
Converter: ShaderNodeMath, ShaderNodeMapRange, ShaderNodeClamp, ShaderNodeValToRGB, ShaderNodeRGBToBW, ShaderNodeSeparateXYZ, ShaderNodeCombineXYZ, ShaderNodeSeparateColor, ShaderNodeCombineColor, ShaderNodeShaderToRGB, ShaderNodeBlackbody, ShaderNodeWavelength
Input: ShaderNodeTexCoord, ShaderNodeUVMap, ShaderNodeAttribute, ShaderNodeVertexColor, ShaderNodeObjectInfo, ShaderNodeCameraData, ShaderNodeLightPath, ShaderNodeFresnel, ShaderNodeLayerWeight, ShaderNodeNewGeometry, ShaderNodeWireframe, ShaderNodeTangent, ShaderNodeAmbientOcclusion, ShaderNodeBevel, ShaderNodeValue, ShaderNodeRGB
Output: ShaderNodeOutputMaterial, ShaderNodeOutputWorld, ShaderNodeOutputLight

=== 标准工作流（每次任务必须执行）===

第一步 - 理解：分析用户需求
第二步 - 调研：
  - 用户给了链接？→ web_analyze_reference
  - 复杂/不熟悉的材质？→ web_search_blender + kb_search
  - 简单任务？→ 跳过直接执行
第三步 - 检查现状：
  - get_scene_info 或 scene_get_render_settings
  - shader_inspect_nodes 或 scene_get_object_materials
第四步 - 执行：
  - 简单操作：直接调用对应工具
  - 复杂材质：shader_clear_nodes → shader_batch_add_nodes → shader_batch_link_nodes
  - 透射材质：额外调用 shader_configure_eevee + scene_set_render_settings(use_ssr=true)
第五步 - 验证：
  - shader_get_material_summary 检查节点和参数
  - 透射材质：scene_get_render_settings 确认 SSR
第六步 - 如果有问题，修正后再次验证
第七步 - 简洁告知结果

=== 关键知识 ===

Principled BSDF（Blender 5.0）：
  Base Color, Metallic, Roughness, IOR, Alpha,
  Transmission Weight(旧版Transmission), Subsurface Weight(旧版Subsurface),
  Subsurface Radius, Emission Color, Emission Strength, Normal, Coat Weight, Sheen Weight

透射材质：Transmission Weight=1.0 + IOR(水1.333/玻璃1.45/冰1.31/钻石2.42)
  EEVEE 必须 shader_configure_eevee + scene_set_render_settings(use_ssr=true, use_ssr_refraction=true)

卡通渲染：ShaderToRGB → ColorRamp(CONSTANT) → Emission
Driver：frame*0.01(线性), sin(frame*0.1)(波动)

=== 回复风格 ===
- 先做后说。先调用工具，再简短说明做了什么。
- 不要长篇大论解释原理。用户要的是结果。
- 告知可调参数时用一行列出，不要分段解释。
- 中文回复。"""

    def _get_tools(self):
        from . import tools
        return tools.TOOLS

    def _call_api(self, messages: list, tools: list = None) -> dict:
        if "/v1" in self.api_base:
            url = f"{self.api_base}/messages"
        else:
            url = f"{self.api_base}/v1/messages"

        log_debug(f"API URL: {url}, Model: {self.model}")

        payload = {
            "model": self.model,
            "max_tokens": 8192,
            "system": self.system_prompt,
            "messages": messages,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = {"type": "auto"}

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        data = json.dumps(payload).encode("utf-8")
        log_debug(f"Request payload size: {len(data)} bytes")

        max_retries = 3
        backoff_times = [5, 15, 30]
        last_error_msg = ""

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                log_debug(f"API request attempt {attempt + 1}/{max_retries}...")
                with urllib.request.urlopen(req, timeout=120) as response:
                    response_text = response.read().decode("utf-8")
                    log_debug(f"API response received, length: {len(response_text)}")
                    return json.loads(response_text)
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8")
                friendly_msg = _parse_api_error(e.code, error_body)
                last_error_msg = f"API {e.code}: {friendly_msg}"
                log_error(f"API HTTP {e.code}: {error_body[:1000]}")

                if e.code == 413:
                    raise Exception(f"请求体过大（{len(data)} bytes），工具返回数据量超限。请减少查询范围。")

                if _is_permanent_error(error_body):
                    try:
                        from . import action_log
                        action_log.log_error(f"API_HTTP_{e.code}", last_error_msg)
                    except Exception:
                        pass
                    raise Exception(last_error_msg)

                if e.code in (500, 502, 503, 529) and attempt < max_retries - 1:
                    wait = backoff_times[attempt]
                    log_debug(f"服务器错误 {e.code}，{wait}秒后重试...")
                    time.sleep(wait)
                    continue

                try:
                    from . import action_log
                    action_log.log_error(f"API_HTTP_{e.code}", last_error_msg)
                except Exception:
                    pass
                raise Exception(last_error_msg)
            except urllib.error.URLError as e:
                last_error_msg = f"网络错误: {e.reason}"
                log_error(last_error_msg)
                if attempt < max_retries - 1:
                    wait = backoff_times[attempt]
                    log_debug(f"网络错误，{wait}秒后重试...")
                    time.sleep(wait)
                    continue
                try:
                    from . import action_log
                    action_log.log_error("network_error", last_error_msg)
                except Exception:
                    pass
                raise Exception(last_error_msg)
            except Exception as e:
                last_error_msg = f"未知错误: {str(e)}"
                log_error(last_error_msg)
                raise Exception(last_error_msg)

        try:
            from . import action_log
            action_log.log_error("max_retries", last_error_msg)
        except Exception:
            pass
        raise Exception(f"API 调用失败（重试{max_retries}次）: {last_error_msg}")

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

            preflight = (
                "[系统提醒] 你是 Blender 操作者，必须使用 MCP 工具执行操作。"
                "禁止纯文字回复，禁止生成 Python 脚本。立即调用工具。\n\n"
            )
            augmented_message = preflight + user_message

            self.conversation_history.append({"role": "user", "content": augmented_message})

            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history * 2:]

            response = self._call_api(
                messages=self.conversation_history, tools=self._get_tools()
            )

            self._handle_response(response)

        except Exception as e:
            error_msg = str(e)
            log_error(f"Process message error: {error_msg}")
            try:
                from . import action_log
                action_log.log_error("process_message", error_msg)
                action_log.end_session(f"错误: {error_msg}")
            except Exception:
                pass
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
            except Exception as e:
                log_error(f"记录 assistant 消息到 action_log 失败: {e}")

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
            except Exception as e:
                log_error(f"结束 session 到 action_log 失败: {e}")

    def _execute_tools(self, tool_uses: list):
        from . import tools

        tool_results = []

        for tool_use in tool_uses:
            tool_id = tool_use.get("id")
            tool_name = tool_use.get("name")
            tool_input = tool_use.get("input", {})

            if tool_name == "execute_python":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": "错误：execute_python 已被禁用。请使用 MCP 工具完成操作。可用工具：shader_batch_add_nodes, shader_link_nodes, scene_add_light 等。",
                    "is_error": True,
                })
                continue

            log_debug(f"Executing tool: {tool_name}")

            if self.on_tool_call:
                self._safe_callback(self.on_tool_call, tool_name, tool_input)

            result = self._execute_in_main_thread(
                tools.execute_tool, tool_name, tool_input
            )

            try:
                from . import action_log
                action_log.log_tool_call(tool_name, tool_input, result)
            except Exception as e:
                log_error(f"记录工具调用到 action_log 失败: {e}")

            if result.get("result") == "NEEDS_CONFIRMATION":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": "错误：execute_python 已被禁用。请使用 MCP 工具完成操作。",
                    "is_error": True,
                })
                continue

            if result.get("result") == "NEEDS_VISION_ANALYSIS":
                self._handle_vision_analysis(
                    tool_id,
                    result.get("image_data"),
                    result.get("scene_info"),
                    result.get("question"),
                )
                return

            if result.get("success"):
                result_str = json.dumps(result.get("result"), ensure_ascii=False)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": _truncate_tool_result(result_str),
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
            error_msg = str(e)
            log_error(f"Continue with tool results error: {error_msg}")
            try:
                from . import action_log
                action_log.log_error("continue_tool_results", error_msg)
                action_log.end_session(f"错误: {error_msg}")
            except Exception:
                pass
            if self.on_error:
                self._safe_callback(self.on_error, error_msg)

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
        except Exception:
            tool_info = f"{args[1] if len(args) > 1 else 'unknown'}"
            log_error(f"工具执行超时: {tool_info}")
            return {"success": False, "result": None, "error": "操作超时（30秒）"}

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
