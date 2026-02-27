"""
结构化输出 Agent — XML 解析模式

与 core/agent.py 的 BlenderAgent 并行存在。
区别：不通过 API 的 tool_use 传工具，而是：
1. 把工具目录写进 system prompt（纯文本）
2. LLM 生成文本 + XML <tool_call> 标签
3. 外部解析器（xml_parser.py）提取工具调用
4. 执行工具，将结果以文本形式追加到对话

优势：
- 减少 API payload 大小（不传 tool schemas JSON）
- 兼容不支持 tool_use 的 LLM / 中转 API
- 减少幻觉（LLM 只需写 XML 标签，不需理解 tool_use 协议）
- 工具验证在解析层完成，不依赖 LLM

[DEVLOG]
- 2026-02-26: 初始版本。基于 BlenderAgent 模式，替换 tool_use 为 XML 解析。
"""

import json
import threading
import traceback
from types import SimpleNamespace
from typing import Callable, Optional

from .llm import UnifiedLLM, LLMConfig, LLMResponse
from .router import route as route_message
from .tools import (
    get_all_tools,
    get_tools_for_intent,
    execute_tool,
    truncate_result,
)
from .xml_parser import parse as parse_xml, build_tool_catalog, validate_tool_call
from .tool_policies import normalize_tool_args
from .shader_read_planner import plan_shader_inspect
from .safety_guard import (
    looks_like_python_script,
    looks_like_script_output,
    references_foreign_toolset,
    looks_like_final_summary,
)
from .pseudo_tool_parser import extract_pseudo_tool_calls


def _log(msg: str):
    print(f"[StructuredAgent] {msg}")


# ========== System Prompt（XML 模式） ==========

_BASE_PROMPT = """你是 Blender 场景的唯一操作者，拥有对 Blender 的完全控制权。

=== 铁律 ===
1. 每次回复必须包含至少一个 <tool_call>。纯文字回复 = 失败。
2. 禁止 execute_python，禁止生成 Python 脚本。
3. 禁止说"你可以"、"建议你"、"请手动"。你自己做。
4. 不确定参数？先调用查询工具，不要猜测。
5. 不确定怎么做？先 web_search_blender 或 kb_search。
6. 为避免 token 暴涨，读取节点图必须先摘要后细读：先 shader_get_material_summary(detail_level="basic", include_node_index=true)，需要定位节点时先 shader_search_index，再 shader_inspect_nodes(limit=20~40, compact=true) 分页，最后仅对关键节点开启 include_values。

=== 工具调用格式 ===
使用 XML 标签调用工具，可以在文字中间或末尾插入：

<tool_call name="工具名">
  <param name="参数名">值</param>
</tool_call>

数组参数用 JSON 格式：<param name="location">[1, 2, 3]</param>
对象参数用 JSON 格式：<param name="color">[0.8, 0.2, 0.1, 1.0]</param>

可以在一次回复中调用多个工具，按顺序执行。

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

_DOMAIN_HINTS = {
    "shader": "\n[领域提示] 着色器操作。先摘要后分页：shader_get_material_summary(detail_level='basic', include_node_index=true) → shader_search_index(query='...') → shader_inspect_nodes(limit=30, compact=true)。仅在定位关键节点后，才用 include_values=true 精读。复杂材质: shader_clear_nodes→shader_batch_add_nodes→shader_batch_link_nodes。验证: shader_get_material_summary",
    "toon": "\n[领域提示] 卡通渲染。核心: ShaderToRGB→ColorRamp(CONSTANT)→Emission。使用 shader_create_toon_material 或 shader_convert_to_toon",
    "animation": "\n[领域提示] 动画。Driver 表达式可用: frame, sin, cos, abs, min, max, pow, sqrt",
    "scene": "\n[领域提示] 场景操作。操作前先 get_scene_info 确认状态。",
    "render": "\n[领域提示] 渲染。EEVEE 透射需要 SSR + SSR Refraction。",
}

_PREFLIGHT = "[系统提醒] 你必须使用 <tool_call> XML 标签调用工具。禁止纯文字回复。\n\n"

# 工具结果反馈模板
_TOOL_RESULT_TEMPLATE = """[工具执行结果]
{results}
[继续操作或总结结果]"""


class StructuredAgent:
    """
    结构化输出 Agent — XML 解析模式。
    
    与 BlenderAgent 接口一致（send_message, on_message, on_tool_call, on_error, clear_history）。
    """

    MAX_TOOL_ROUNDS = 5  # 最大工具调用轮数（防止无限循环）

    def __init__(self, config: LLMConfig):
        self.llm = UnifiedLLM(config)
        self.conversation_history = []
        self.max_history = 200  # 取消对话历史限制，保留足够上下文
        self._request_counter = 0
        self._active_request_id = 0
        self._cancel_event = threading.Event()
        self._state_lock = threading.Lock()

        # UI 回调（与 BlenderAgent 一致）
        self.on_message: Optional[Callable] = None
        self.on_tool_call: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_plan: Optional[Callable] = None
        self.on_permission_request: Optional[Callable] = None

        # 工具
        self._tools = None
        self._load_tools()

    def _load_tools(self):
        self._tools = get_all_tools()
        _log(f"Loaded {len(self._tools)} tools")

    def _get_tools(self, intent: str = "general") -> list:
        if not self._tools:
            self._load_tools()
        tools = get_tools_for_intent(intent)
        if not tools:
            tools = self._tools
        _log(f"Tools for intent '{intent}': {len(tools)}")
        return tools

    def send_message(self, user_message: str):
        """发送消息（后台线程）"""
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
        """主流程"""
        try:
            if self._is_request_cancelled(request_id):
                return
            self._log_action("start", user_message)

            # 路由
            r = route_message(user_message)
            _log(f"Route: intent={r.intent}, domain={r.domain}, complexity={r.complexity}")

            # 获取工具子集
            tools = self._get_tools(r.intent)

            # 构建 system prompt（含工具目录）
            tool_catalog = build_tool_catalog(tools)
            system = _BASE_PROMPT + "\n\n" + tool_catalog
            domain_hint = _DOMAIN_HINTS.get(r.domain, "")

            # 用户消息
            augmented = _PREFLIGHT + user_message + domain_hint
            self.conversation_history.append({"role": "user", "content": augmented})

            # 裁剪历史
            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history * 2:]

            # 调用 LLM（不传 tools 参数！工具在 system prompt 里）
            response = self.llm.chat(
                messages=self.conversation_history,
                system=system,
                tools=None,
            )
            if self._is_request_cancelled(request_id):
                _log("Request cancelled after LLM response; dropping output")
                return

            # XML 解析 + 执行
            self._handle_structured_response(
                response,
                tools,
                system,
                rounds=0,
                request_id=request_id,
                had_tool_activity=False,
            )

        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"{type(e).__name__}: {e}"
            _log(f"ERROR:\n{tb}")
            self._log_action("error", error_msg)
            self._fire_callback(self.on_error, error_msg)

    def _handle_structured_response(
        self,
        response: LLMResponse,
        tools: list,
        system: str,
        rounds: int,
        request_id: int,
        allow_repair: bool = True,
        had_tool_activity: bool = False,
    ):
        """解析 LLM 文本输出，提取并执行工具调用"""
        if self._is_request_cancelled(request_id):
            return
        raw_text = response.text or ""

        # XML 解析
        parsed = parse_xml(raw_text)
        _log(f"Parsed: text={len(parsed.text)} chars, tool_calls={len(parsed.tool_calls)}")
        effective_tool_calls = list(parsed.tool_calls)
        if (not effective_tool_calls) and raw_text:
            available_names = {t.get("name") for t in (tools or []) if isinstance(t, dict)}
            pseudo_calls = extract_pseudo_tool_calls(raw_text, available_names)
            if pseudo_calls:
                effective_tool_calls = [
                    SimpleNamespace(name=pc.get("name", ""), arguments=pc.get("arguments") or {})
                    for pc in pseudo_calls
                ]
                _log(f"Recovered pseudo tool calls from text: {len(effective_tool_calls)}")
                for tc in effective_tool_calls:
                    self._fire_callback(
                        self.on_tool_call,
                        f"__pseudo_recovered__:{tc.name}",
                        tc.arguments,
                    )

        # 显示纯文本部分：有工具调用时不展示中间文本；
        # 对“无工具调用且仍可纠偏”的场景也不展示，避免先说后做。
        if parsed.text and (not effective_tool_calls) and (not allow_repair):
            self._fire_callback(self.on_message, "assistant", parsed.text)

        if not effective_tool_calls:
            if raw_text and references_foreign_toolset(raw_text):
                if allow_repair:
                    _log("Detected foreign toolset response, forcing retry with local MCP tools")
                    self._force_tool_retry(request_id, tools, system, rounds, had_tool_activity=had_tool_activity)
                    return
                err = "[WRONG_TOOLSET] 当前模型未使用 Blender MCP 工具集。请切换模型后重试。"
                self._fire_callback(self.on_error, err)
                self._log_action("error", err)
                self._log_action("end", err)
                return
            if had_tool_activity:
                # 本请求已经执行过工具：允许正常纯文本收尾，不再按 NO_TOOLCALL 失败
                if raw_text:
                    if not looks_like_final_summary(raw_text):
                        _log("Post-tool text does not look final, forcing continuation")
                        self._force_tool_retry(
                            request_id, tools, system, rounds, had_tool_activity=had_tool_activity
                        )
                        return
                    self.conversation_history.append({"role": "assistant", "content": raw_text})
                    self._log_action("end", (parsed.text or raw_text)[:200])
                    return
                err = "[NO_TOOLCALL] 工具执行后未返回有效总结文本。"
                self._fire_callback(self.on_error, err)
                self._log_action("error", err)
                self._log_action("end", err)
                return

            if not allow_repair:
                # 工具轮后的最终收尾允许纯文本总结（无需再输出 XML）
                if raw_text:
                    self.conversation_history.append({"role": "assistant", "content": raw_text})
                    self._log_action("end", (parsed.text or raw_text)[:200])
                    return
                err = "[NO_TOOLCALL] 工具执行后未返回有效总结文本。"
                self._fire_callback(self.on_error, err)
                self._log_action("error", err)
                self._log_action("end", err)
                return

            if raw_text and (looks_like_python_script(raw_text) or looks_like_script_output(raw_text)):
                if allow_repair:
                    _log("Detected script-like output without XML tool_call, forcing retry")
                    self._force_tool_retry(request_id, tools, system, rounds, had_tool_activity=had_tool_activity)
                    return
                err = "[NO_TOOLCALL] 检测到模型返回脚本/伪代码内容，已拦截。请重试（系统将强制使用 MCP 工具）。"
                self._fire_callback(self.on_error, err)
                self._log_action("error", err)
                return
            if allow_repair:
                _log("No XML tool_call found, forcing retry")
                self._force_tool_retry(request_id, tools, system, rounds, had_tool_activity=had_tool_activity)
                return
            err = "[NO_TOOLCALL] 模型未返回任何 XML 工具调用，任务未执行。建议切换模型或改用 Native Tool Use 模式后重试。"
            self._fire_callback(self.on_error, err)
            self._log_action("error", err)
            self._log_action("end", err)
            return

        # 记录 assistant 原始输出（含 XML）
        self.conversation_history.append({"role": "assistant", "content": raw_text})

        # 执行工具
        result_parts = []
        next_had_tool_activity = had_tool_activity
        for tc in effective_tool_calls:
            if self._is_request_cancelled(request_id):
                return
            # 验证
            error = validate_tool_call(tc, tools)
            if error:
                _log(f"Validation failed: {tc.name} — {error}")
                result_parts.append(f"❌ {tc.name}: {error}")
                continue

            if tc.name == "execute_python":
                result_parts.append(f"❌ {tc.name}: execute_python 已被禁用")
                continue

            raw_args = tc.arguments or {}
            normalized_args = normalize_tool_args(tc.name, raw_args)
            normalized_args = self._maybe_expand_shader_inspect_args(tc.name, raw_args, normalized_args)
            _log(f"Executing: {tc.name}({normalized_args})")
            next_had_tool_activity = True
            self._fire_callback(self.on_tool_call, tc.name, normalized_args)

            # 主线程执行
            result = self._execute_in_main_thread(execute_tool, tc.name, normalized_args)
            if self._is_request_cancelled(request_id):
                return
            self._log_action("tool", tc.name, normalized_args, result)

            if result.get("success"):
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
                result_str = json.dumps(result.get("result"), ensure_ascii=False)
                result_parts.append(f"✅ {tc.name}: {truncate_result(result_str)}")
            else:
                result_parts.append(f"❌ {tc.name}: {result.get('error', '未知错误')}")

        # 将结果作为 user 消息追加（让 LLM 继续）
        results_text = _TOOL_RESULT_TEMPLATE.format(results="\n".join(result_parts))

        # 防止无限循环
        if rounds >= self.MAX_TOOL_ROUNDS:
            _log(f"Max tool rounds ({self.MAX_TOOL_ROUNDS}) reached, stopping")
            self.conversation_history.append({"role": "user", "content": results_text + "\n[已达最大工具调用轮数，请总结结果]"})
            final = self.llm.chat(messages=self.conversation_history, system=system, tools=None)
            if self._is_request_cancelled(request_id):
                return
            if final.text:
                self._fire_callback(self.on_message, "assistant", final.text)
                self.conversation_history.append({"role": "assistant", "content": final.text})
            self._log_action("end", "max rounds reached")
            return

        # 继续对话
        self.conversation_history.append({"role": "user", "content": results_text})

        next_response = self.llm.chat(
            messages=self.conversation_history,
            system=system,
            tools=None,
        )
        if self._is_request_cancelled(request_id):
            return

        # 递归处理（可能还有工具调用）
        # 工具轮之后允许模型直接给最终文本总结，不再强制继续输出 XML tool_call
        self._handle_structured_response(
            next_response,
            tools,
            system,
            rounds + 1,
            request_id=request_id,
            allow_repair=False,
            had_tool_activity=next_had_tool_activity,
        )

    def _force_tool_retry(
        self,
        request_id: int,
        tools: list,
        system: str,
        rounds: int,
        had_tool_activity: bool = False,
    ):
        if self._is_request_cancelled(request_id):
            return
        try:
            tool_names = [t.get("name") for t in (tools or []) if isinstance(t, dict) and t.get("name")]
            tool_hint = ", ".join(tool_names[:40])
            repair_msg = (
                "[系统纠偏] 你刚刚没有正确调用工具（或输出了脚本/伪代码），这是被禁止的。"
                "必须改为使用 <tool_call> 调用 MCP 工具；禁止任何 Python 代码块、函数调用示例、代码围栏。"
                "你只能使用以下本地 Blender 工具集，不可使用 bash_tool/str_replace 等外部工具："
                f"{tool_hint}。现在请立即输出至少一个 <tool_call>。"
            )
            self.conversation_history.append({"role": "user", "content": repair_msg})
            response = self.llm.chat(
                messages=self.conversation_history,
                system=system,
                tools=None,
            )
            if self._is_request_cancelled(request_id):
                return
            self._handle_structured_response(
                response,
                tools,
                system,
                rounds=rounds,
                request_id=request_id,
                allow_repair=False,
                had_tool_activity=had_tool_activity,
            )
        except Exception as e:
            self._fire_callback(self.on_error, f"纠偏重试失败: {e}")

    def _maybe_expand_shader_inspect_args(self, tool_name: str, raw_args: dict, normalized_args: dict) -> dict:
        """Structured 模式下的 inspect 自动检索扩展"""
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

    def _execute_in_main_thread(self, func, *args) -> dict:
        """在 Blender 主线程执行"""
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
        except Exception:
            return func(*args)

    def _fire_callback(self, callback, *args):
        """非阻塞 UI 回调"""
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
            elif action_type == "metric":
                payload = args[0] if args else {}
                metric_name = payload.get("name", "unknown_metric")
                action_log.log_metric(metric_name, payload)
        except Exception:
            pass

    def clear_history(self):
        self.conversation_history = []
        _log("History cleared")
