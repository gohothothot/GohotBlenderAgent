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

        self.system_prompt = """你是一个 Blender 3D 建模助手，运行在 Blender 内部。

你的能力：
1. 创建和操作 3D 物体（立方体、球体、圆柱等）
2. 设置材质颜色、金属度、粗糙度
3. 执行自定义 Python/bpy 代码来完成复杂任务

使用规则：
- 对于简单操作，使用对应的工具
- 对于复杂操作（如建模、动画），使用 execute_python 工具
- 执行代码前，先用 description 参数说明代码功能
- 回复要简洁，操作完成后告知结果

当前场景信息会在对话中提供。"""

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
