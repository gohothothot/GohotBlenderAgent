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
from .tool_policies import normalize_tool_args
from .shader_read_planner import plan_shader_inspect
from .safety_guard import looks_like_python_script, looks_like_script_output


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
6. 为避免 token 暴涨，读取节点图时必须先摘要后细读：先 shader_get_material_summary(detail_level="basic", include_node_index=true)，需要定位节点时先 shader_search_index，再 shader_inspect_nodes(limit=20~40, compact=true) 分页，最后仅对关键节点开启 include_values。
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
    "shader": "\n[领域提示] 着色器操作。先摘要后分页：shader_get_material_summary(detail_level='basic', include_node_index=true) → shader_search_index(query='...') → shader_inspect_nodes(limit=30, compact=true)。仅在定位关键节点后，才用 include_values=true 精读。复杂材质: shader_clear_nodes→shader_batch_add_nodes→shader_batch_link_nodes。验证: shader_get_material_summary",
    "toon": "\n[领域提示] 卡通渲染。核心: ShaderToRGB→ColorRamp(CONSTANT)→Emission。使用 shader_create_toon_material 或 shader_convert_to_toon",
    "animation": "\n[领域提示] 动画。Driver 表达式可用: frame, sin, cos, abs, min, max, pow, sqrt",
    "scene": "\n[领域提示] 场景操作。操作前先 get_scene_info 确认状态。",
    "render": "\n[领域提示] 渲染。EEVEE 透射需要 SSR + SSR Refraction。",
}

MAX_TOOL_ROUNDS = 8
HISTORY_CHAR_BUDGET = 120000
HISTORY_KEEP_TAIL = 16


class BlenderAgent:
    """
    主 Agent — 直接传工具给 LLM，保证可靠性。
    """

    def __init__(self, config: LLMConfig):
        self.llm = UnifiedLLM(config)
        self.conversation_history = []
        self.max_history = 200  # 取消对话历史限制，保留足够上下文
        self._tool_rounds = 0
        self._request_counter = 0
        self._active_request_id = 0
        self._cancel_event = threading.Event()
        self._state_lock = threading.Lock()

        # UI 回调
        self.on_message: Optional[Callable] = None
        self.on_tool_call: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_plan: Optional[Callable] = None
        self.on_permission_request: Optional[Callable] = None

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
        with self._state_lock:
            self._request_counter += 1
            request_id = self._request_counter
            self._active_request_id = request_id
            self._cancel_event.clear()
        thread = threading.Thread(target=self._process, args=(user_message, request_id))
        thread.daemon = True
        thread.start()

    def cancel_current_request(self):
        """请求取消当前进行中的任务（网络调用返回后生效）"""
        self._cancel_event.set()
        _log("Cancel requested")

    def _is_request_cancelled(self, request_id: int) -> bool:
        with self._state_lock:
            active = self._active_request_id
        return self._cancel_event.is_set() or request_id != active

    def _process(self, user_message: str, request_id: int):
        """处理用户消息 — 主流程"""
        try:
            if self._is_request_cancelled(request_id):
                return
            self._tool_rounds = 0
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
            self._compact_history_if_needed()

            # 调用 LLM
            response = self.llm.chat(
                messages=self.conversation_history,
                system=SYSTEM_PROMPT,
                tools=tools,
            )
            if self._is_request_cancelled(request_id):
                _log("Request cancelled after LLM response; dropping output")
                return

            # 处理响应
            self._handle_response(response, tools, request_id)

        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"{type(e).__name__}: {e}"
            _log(f"ERROR:\n{tb}")
            self._log_action("error", error_msg)
            self._fire_callback(self.on_error, error_msg)

    def _handle_response(self, response: LLMResponse, tools: list, request_id: int, allow_repair: bool = True):
        """处理 LLM 响应"""
        if self._is_request_cancelled(request_id):
            return
        # 文本部分：若本轮包含工具调用，则不展示中间文本，避免“伪代码步骤”污染 UI
        if response.text and (not response.has_tool_calls):
            self._fire_callback(self.on_message, "assistant", response.text)
            self._log_action("message", response.text)

        # 工具调用
        if response.has_tool_calls:
            self.conversation_history.append(
                self.llm.format_assistant_message(response)
            )
            self._execute_tools(response.tool_calls, tools, request_id)
        else:
            # 无工具调用 — 记录并结束
            if response.text and (looks_like_python_script(response.text) or looks_like_script_output(response.text)):
                if allow_repair:
                    _log("Detected script-like output without tools, forcing tool retry")
                    self._force_tool_retry(request_id, tools)
                    return
                err = "检测到模型返回脚本/伪代码内容，已拦截。请重试（系统将强制使用 MCP 工具）。"
                self._fire_callback(self.on_error, err)
                self._log_action("error", err)
                return
            if allow_repair:
                _log("No tool calls returned, forcing tool retry")
                self._force_tool_retry(request_id, tools)
                return
            err = "模型未返回任何工具调用，任务未执行。建议切换模型或改用 Structured XML 模式后重试。"
            self._fire_callback(self.on_error, err)
            self._log_action("error", err)
            self._log_action("end", err)

    def _execute_tools(self, tool_calls: list, tools: list, request_id: int):
        """执行工具调用"""
        tool_results = []

        for tc in tool_calls:
            if self._is_request_cancelled(request_id):
                _log("Request cancelled before tool execution loop finished")
                return
            if tc.name == "execute_python":
                tool_results.append(self.llm.format_tool_result(
                    tc.id, "错误：execute_python 已被禁用。请使用 MCP 工具。", is_error=True,
                ))
                continue

            raw_args = tc.arguments or {}
            normalized_args = normalize_tool_args(tc.name, raw_args)
            normalized_args = self._maybe_expand_shader_inspect_args(tc.name, raw_args, normalized_args)
            _log(f"Executing: {tc.name}")
            self._fire_callback(self.on_tool_call, tc.name, normalized_args)

            # 在主线程执行
            result = self._execute_in_main_thread(execute_tool, tc.name, normalized_args)
            if self._is_request_cancelled(request_id):
                _log("Request cancelled after tool execution; dropping result")
                return
            self._log_action("tool", tc.name, normalized_args, result)

            # 特殊处理
            if result.get("result") == "NEEDS_CONFIRMATION":
                tool_results.append(self.llm.format_tool_result(
                    tc.id, "错误：execute_python 已被禁用。", is_error=True,
                ))
                continue
            if result.get("result") == "NEEDS_PERMISSION_CONFIRMATION":
                self._fire_callback(
                    self.on_permission_request,
                    result.get("tool_name", tc.name),
                    result.get("arguments", normalized_args),
                    result.get("risk", "high"),
                    result.get("reason", "需要权限确认"),
                )
                self._log_action(
                    "permission_wait",
                    result.get("tool_name", tc.name),
                    result.get("arguments", normalized_args),
                    result.get("reason", "需要权限确认"),
                )
                return

            if result.get("result") == "NEEDS_VISION_ANALYSIS":
                self._handle_vision(tc.id, result, request_id)
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
            self._continue_with_results(tool_results, tools, request_id)

    def _maybe_expand_shader_inspect_args(self, tool_name: str, raw_args: dict, normalized_args: dict) -> dict:
        """
        当模型请求 inspect 且想看值但没有指定节点时：
        先自动做一次 shader_search_index，再把候选 node_names 注入 inspect。
        """
        try:
            if tool_name != "shader_inspect_nodes":
                return normalized_args

            plan = plan_shader_inspect(raw_args, normalized_args)
            self._log_action("metric", {
                "name": "shader_read_plan",
                "tool": tool_name,
                "reason": plan.get("reason"),
                "cost": plan.get("cost", {}),
                "material_name": normalized_args.get("material_name") or raw_args.get("material_name"),
            })
            if not plan.get("auto_search"):
                return normalized_args

            search_args = plan.get("search_args") or {}

            self._fire_callback(self.on_tool_call, "shader_search_index", search_args)
            search_result = self._execute_in_main_thread(execute_tool, "shader_search_index", search_args)
            self._log_action("tool", "shader_search_index", search_args, search_result)
            result_payload = search_result.get("result") or {}
            self._log_action("metric", {
                "name": "shader_search_index_result",
                "success": bool(search_result.get("success")),
                "material_name": search_args.get("material_name"),
                "query": search_args.get("query"),
                "candidate_count": int(result_payload.get("candidate_count", 0)) if isinstance(result_payload, dict) else 0,
            })

            if not search_result.get("success"):
                return normalized_args
            payload = result_payload
            candidates = payload.get("candidates") or []
            node_names = [c.get("node_name") for c in candidates if isinstance(c, dict) and c.get("node_name")]
            if not node_names:
                return normalized_args

            expanded = dict(normalized_args)
            expanded["node_names"] = node_names[:8]
            expanded["include_values"] = True
            expanded["compact"] = False
            expanded["limit"] = min(max(len(expanded["node_names"]), int(expanded.get("limit", 30))), 80)
            return expanded
        except Exception as e:
            _log(f"auto-search expand failed: {e}")
            return normalized_args

    def _continue_with_results(self, tool_results: list, tools: list, request_id: int):
        """将工具结果发回 LLM 继续对话"""
        try:
            if self._is_request_cancelled(request_id):
                return
            self._tool_rounds += 1
            if self._tool_rounds > MAX_TOOL_ROUNDS:
                stop_msg = (
                    f"工具调用已达到上限（{MAX_TOOL_ROUNDS} 轮）。"
                    "为避免无限循环，我先停止继续调用工具并总结当前结果。"
                )
                self._fire_callback(self.on_message, "assistant", stop_msg)
                self._log_action("message", stop_msg)
                self._log_action("end", stop_msg)
                return

            result_messages = self.llm.format_tool_results(tool_results)
            self.conversation_history.extend(
                result_messages if isinstance(result_messages, list) else [result_messages]
            )
            self._compact_history_if_needed()

            response = self.llm.chat(
                messages=self.conversation_history,
                system=SYSTEM_PROMPT,
                tools=tools,
            )
            if self._is_request_cancelled(request_id):
                _log("Request cancelled after continue-call response; dropping output")
                return
            self._handle_response(response, tools, request_id)

        except Exception as e:
            error_msg = str(e)
            _log(f"Continue error: {error_msg}")
            self._log_action("error", error_msg)
            self._fire_callback(self.on_error, error_msg)

    def _handle_vision(self, tool_id: str, result: dict, request_id: int):
        """处理视觉分析请求"""
        try:
            if self._is_request_cancelled(request_id):
                return
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
            temp_history = self._compact_history(temp_history)

            response = self.llm.chat(messages=temp_history, system=SYSTEM_PROMPT)
            if self._is_request_cancelled(request_id):
                return

            analysis = response.text
            tool_result = self.llm.format_tool_result(tool_id, analysis)
            self._continue_with_results([tool_result], self._tools, request_id)

        except Exception as e:
            _log(f"Vision error: {e}")
            tool_result = self.llm.format_tool_result(
                tool_id, f"场景分析失败: {e}", is_error=True,
            )
            self._continue_with_results([tool_result], self._tools, request_id)

    def _force_tool_retry(self, request_id: int, tools: list):
        if self._is_request_cancelled(request_id):
            return
        try:
            repair_msg = (
                "[系统纠偏] 你刚刚没有正确调用工具（或输出了脚本/伪代码），这是被禁止的。"
                "必须改为调用 MCP 工具完成任务；禁止任何 Python 代码块、函数调用示例、代码围栏。"
                "现在请立即输出 tool calls。"
            )
            self.conversation_history.append({"role": "user", "content": repair_msg})
            response = self.llm.chat(
                messages=self.conversation_history,
                system=SYSTEM_PROMPT,
                tools=tools,
            )
            if self._is_request_cancelled(request_id):
                return
            self._handle_response(response, tools, request_id, allow_repair=False)
        except Exception as e:
            self._fire_callback(self.on_error, f"纠偏重试失败: {e}")

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

    def _history_chars(self, messages: list = None) -> int:
        total = 0
        items = messages if messages is not None else self.conversation_history
        for msg in items:
            content = msg.get("content")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total += len(json.dumps(block, ensure_ascii=False))
                    else:
                        total += len(str(block))
            elif content is not None:
                total += len(str(content))
        return total

    def _compact_history_if_needed(self):
        if self._history_chars() <= HISTORY_CHAR_BUDGET:
            return
        self.conversation_history = self._compact_history(self.conversation_history)

    def _compact_history(self, history: list) -> list:
        if len(history) <= HISTORY_KEEP_TAIL + 1:
            return history

        head = history[:-HISTORY_KEEP_TAIL]
        tail = history[-HISTORY_KEEP_TAIL:]

        summary_lines = ["[历史压缩摘要] 以下为较早轮次的关键信息："]
        for msg in head[-40:]:
            role = msg.get("role", "unknown")
            content = msg.get("content")
            if isinstance(content, str):
                snippet = content.replace("\n", " ")[:180]
                summary_lines.append(f"- {role}: {snippet}")
            elif isinstance(content, list):
                tool_events = 0
                for block in content:
                    if isinstance(block, dict) and block.get("type") in ("tool_use", "tool_result"):
                        tool_events += 1
                summary_lines.append(f"- {role}: 结构化内容 {len(content)} 块（工具相关 {tool_events}）")
            else:
                summary_lines.append(f"- {role}: {str(content)[:120]}")

        compacted = [{"role": "system", "content": "\n".join(summary_lines)}]
        compacted.extend(tail)
        _log(f"History compacted: {len(history)} -> {len(compacted)}, chars={self._history_chars(compacted)}")
        return compacted

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
            elif action_type == "metric":
                payload = args[0] if args else {}
                metric_name = payload.get("name", "unknown_metric")
                action_log.log_metric(metric_name, payload)
        except Exception:
            pass

    def clear_history(self):
        self.conversation_history = []
        _log("History cleared")
