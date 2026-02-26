"""
Blender Agent — 主 Agent (Native Tool Use 模式)
继承旧 BlenderAgent 的可靠工作模式（直接传工具给 LLM），
在此基础上加入意图路由和工具子集筛选。
核心原则：
1. 工具一定要传给 LLM，不传 = 失败
2. 回调用 bpy.app.timers.register（非阻塞）
3. 工具执行在主线程（bpy 要求）
[DEVLOG]
- 2026-02-26: 初始版本。从旧 agent_core.py 重构，加入意图路由 + 工具子集筛选。
  保留 _execute_in_main_thread + _fire_callback 的可靠模式。
"""

import json
import threading
import traceback
from typing import Callable, Optional

from .llm import UnifiedLLM, LLMConfig, LLMResponse
from .router import route as route_message
from .tools import (
    get_all_tools,
    get_tools_for_intent,
    get_tool_summaries,
    execute_tool,
    truncate_result,
)


def _log(msg: str):
    print(f"[Agent] {msg}")


# ========== System Prompts ==========

SYSTEM_PROMPT = """你是 Blender 场景的唯一操作者，拥有对 Blender 的完全控制权。
=== 铁律 ===
1. 每次回复必须包含至少一个工具调用。纯文字回复 = 失败。
2. 禁止 execute_python，禁止生成 Python 脚本。
3. 禁止说"你可以"、"建议你"、"请手动"。你自己做。
4. 不确定参数？先调用查询工具，不要猜测。
5. 不确定怎么做？先 web_search_blender 或 kb_search。
=== 工作流 ===
1. 理解需求
2. 调研：链接→web_analyze_reference，复杂材质→web_search_blender+kb_search
3. 检查现状：get_scene_info, shader_inspect_nodes
4. 执行：复杂材质用 shader_clear_nodes→shader_batch_add_nodes→shader_batch_link_nodes
5. 验证：shader_get_material_summary
6. 简洁告知结果
=== 关键知识 ===
Principled BSDF 输入名：Base Color, Metallic, Roughness, IOR, Alpha, Transmission Weight, Subsurface Weight, Emission Color, Emission Strength, Normal, Coat Weight, Sheen Weight
透射材质：Transmission Weight=1.0 + IOR(水1.333/玻璃1.45/冰1.31/钻石2.42)
  EEVEE必须 shader_configure_eevee + scene_set_render_settings(use_ssr=true, use_ssr_refraction=true)
卡通渲染：ShaderToRGB→ColorRamp(CONSTANT)→Emission
=== 回复风格 ===
先做后说，中文回复，不要长篇大论。"""

PREFLIGHT = "[系统提醒] 你是 Blender 操作者，必须使用提供的工具执行操作。禁止纯文字回复，禁止生成 Python 脚本。立即调用工具。\n\n"

DOMAIN_HINTS = {
    "shader": "\n[领域提示] 着色器操作。复杂材质: shader_clear_nodes→shader_batch_add_nodes→shader_batch_link_nodes。验证: shader_get_material_summary",
    "toon": "\n[领域提示] 卡通渲染。核心: ShaderToRGB→ColorRamp(CONSTANT)→Emission。使用 shader_create_toon_material 或 shader_convert_to_toon",
    "animation": "\n[领域提示] 动画。Driver 表达式可用: frame, sin, cos, abs, min, max, pow, sqrt",
    "scene": "\n[领域提示] 场景操作。操作前先 get_scene_info 确认状态。",
    "render": "\n[领域提示] 渲染。EEVEE 透射需要 SSR + SSR Refraction。",
}


class BlenderAgent:
    """
    主 Agent — 直接传工具给 LLM，保证可靠性。
    """

    def __init__(self, config: LLMConfig):
        self.llm = UnifiedLLM(config)
        self.conversation_history = []
        self.max_history = 200  # 取消对话历史限制，保留足够上下文

        # UI 回调
        self.on_message: Optional[Callable] = None
        self.on_tool_call: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_plan: Optional[Callable] = None

        # 工具加载
        self._tools = None
        self._load_tools()

    def _load_tools(self):
        """加载工具定义"""
        self._tools = get_all_tools()
        _log(f"Loaded {len(self._tools)} tools")
        if not self._tools:
            _log("WARNING: No tools loaded!")

    def _get_tools(self, intent: str = "general") -> list:
        """获取工具列表（按意图筛选，保底返回全部）"""
        if not self._tools:
            self._load_tools()

        tools = get_tools_for_intent(intent)
        if not tools:
            _log(f"Intent '{intent}' returned 0 tools, using all {len(self._tools)}")
            tools = self._tools

        _log(f"Tools for intent '{intent}': {len(tools)}")
        return tools

    def send_message(self, user_message: str):
        """发送消息（在后台线程处理）"""
        thread = threading.Thread(target=self._process, args=(user_message,))
        thread.daemon = True
        thread.start()

    def _process(self, user_message: str):
        """处理用户消息 — 主流程"""
        try:
            # 日志
            self._log_action("start", user_message)

            # 路由
            r = route_message(user_message)
            _log(f"Route: intent={r.intent}, domain={r.domain}, complexity={r.complexity}")

            # 获取工具子集
            tools = self._get_tools(r.intent)

            # 构建消息
            domain_hint = DOMAIN_HINTS.get(r.domain, "")
            augmented = PREFLIGHT + user_message + domain_hint
            self.conversation_history.append({"role": "user", "content": augmented})

            # 裁剪历史
            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history * 2:]

            # 调用 LLM
            response = self.llm.chat(
                messages=self.conversation_history,
                system=SYSTEM_PROMPT,
                tools=tools,
            )

            # 处理响应
            self._handle_response(response, tools)

        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"{type(e).__name__}: {e}"
            _log(f"ERROR:\n{tb}")
            self._log_action("error", error_msg)
            self._fire_callback(self.on_error, error_msg)

    def _handle_response(self, response: LLMResponse, tools: list):
        """处理 LLM 响应"""
        # 文本部分
        if response.text:
            self._fire_callback(self.on_message, "assistant", response.text)
            self._log_action("message", response.text)

        # 工具调用
        if response.has_tool_calls:
            self.conversation_history.append(
                self.llm.format_assistant_message(response)
            )
            self._execute_tools(response.tool_calls, tools)
        else:
            # 无工具调用 — 记录并结束
            if response.text:
                self.conversation_history.append(
                    {"role": "assistant", "content": response.text}
                )
            self._log_action("end", response.text[:200] if response.text else "")

    def _execute_tools(self, tool_calls: list, tools: list):
        """执行工具调用"""
        tool_results = []

        for tc in tool_calls:
            if tc.name == "execute_python":
                tool_results.append(self.llm.format_tool_result(
                    tc.id, "错误：execute_python 已被禁用。请使用 MCP 工具。", is_error=True,
                ))
                continue

            _log(f"Executing: {tc.name}")
            self._fire_callback(self.on_tool_call, tc.name, tc.arguments)

            # 在主线程执行
            result = self._execute_in_main_thread(execute_tool, tc.name, tc.arguments)
            self._log_action("tool", tc.name, tc.arguments, result)

            # 特殊处理
            if result.get("result") == "NEEDS_CONFIRMATION":
                tool_results.append(self.llm.format_tool_result(
                    tc.id, "错误：execute_python 已被禁用。", is_error=True,
                ))
                continue

            if result.get("result") == "NEEDS_VISION_ANALYSIS":
                self._handle_vision(tc.id, result)
                return

            # 格式化结果
            if result.get("success"):
                result_str = json.dumps(result.get("result"), ensure_ascii=False)
                tool_results.append(self.llm.format_tool_result(
                    tc.id, truncate_result(result_str),
                ))
            else:
                tool_results.append(self.llm.format_tool_result(
                    tc.id, f"错误: {result.get('error')}", is_error=True,
                ))

        if tool_results:
            self._continue_with_results(tool_results, tools)

    def _continue_with_results(self, tool_results: list, tools: list):
        """将工具结果发回 LLM 继续对话"""
        try:
            result_messages = self.llm.format_tool_results(tool_results)
            self.conversation_history.extend(
                result_messages if isinstance(result_messages, list) else [result_messages]
            )

            response = self.llm.chat(
                messages=self.conversation_history,
                system=SYSTEM_PROMPT,
                tools=tools,
            )
            self._handle_response(response, tools)

        except Exception as e:
            error_msg = str(e)
            _log(f"Continue error: {error_msg}")
            self._log_action("error", error_msg)
            self._fire_callback(self.on_error, error_msg)

    def _handle_vision(self, tool_id: str, result: dict):
        """处理视觉分析请求"""
        try:
            vision_msg = {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": result.get("image_data"),
                        },
                    },
                    {
                        "type": "text",
                        "text": f"场景信息：{json.dumps(result.get('scene_info', {}), ensure_ascii=False)}\n问题：{result.get('question', '')}",
                    },
                ],
            }
            temp_history = self.conversation_history.copy()
            temp_history.append(vision_msg)

            response = self.llm.chat(messages=temp_history, system=SYSTEM_PROMPT)

            analysis = response.text
            tool_result = self.llm.format_tool_result(tool_id, analysis)
            self._continue_with_results([tool_result], self._tools)

        except Exception as e:
            _log(f"Vision error: {e}")
            tool_result = self.llm.format_tool_result(
                tool_id, f"场景分析失败: {e}", is_error=True,
            )
            self._continue_with_results([tool_result], self._tools)

    def _execute_in_main_thread(self, func, *args) -> dict:
        """在 Blender 主线程执行函数"""
        try:
            import bpy
            import queue
            result_queue = queue.Queue()

            def do_execute():
                try:
                    result = func(*args)
                    result_queue.put(result)
                except Exception as e:
                    _log(f"Main thread error: {e}")
                    result_queue.put({"success": False, "result": None, "error": str(e)})
                return None

            bpy.app.timers.register(do_execute)

            try:
                return result_queue.get(timeout=30.0)
            except Exception:
                return {"success": False, "result": None, "error": "操作超时（30秒）"}
        except Exception as e:
            # bpy 不可用时直接调用
            return func(*args)

    def _fire_callback(self, callback, *args):
        """非阻塞地在主线程执行 UI 回调"""
        if not callback:
            return
        try:
            import bpy

            def do_callback():
                try:
                    callback(*args)
                except Exception as e:
                    _log(f"Callback error: {e}")
                return None

            bpy.app.timers.register(do_callback)
        except Exception:
            try:
                callback(*args)
            except Exception:
                pass

    def _log_action(self, action_type: str, *args):
        """记录操作日志"""
        try:
            from .. import action_log
            if action_type == "start":
                action_log.start_session(args[0])
                action_log.log_agent_message("user", args[0])
            elif action_type == "message":
                action_log.log_agent_message("assistant", args[0])
            elif action_type == "tool":
                action_log.log_tool_call(args[0], args[1], args[2])
            elif action_type == "error":
                action_log.log_error("agent", args[0])
                action_log.end_session(f"错误: {args[0][:200]}")
            elif action_type == "end":
                action_log.end_session(args[0] if args else "")
        except Exception:
            pass

    def clear_history(self):
        self.conversation_history = []
        _log("History cleared")
