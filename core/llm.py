"""
统一 LLM 调用层

支持 Anthropic / OpenAI / 中转 API，自动检测格式。
保留旧 BlenderAgent._call_api 的可靠性，加入多 Provider 支持。

[DEVLOG]
- 2026-02-26: 初始版本。合并 anthropic_provider.py + openai_provider.py 为单文件 UnifiedLLM。
  支持自动检测 provider（根据 URL/模型名），重试逻辑，消息格式转换。
"""

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    max_tokens: int = 64000  # 取消输出限制，设为模型最大值
    timeout: int = 120

    def detect_provider(self) -> str:
        base = self.api_base.lower()
        if "anthropic" in base:
            return "anthropic"
        if "openai" in base:
            return "openai"
        model = self.model.lower()
        if "claude" in model:
            return "anthropic"
        if "gpt" in model or "codex" in model:
            return "openai"
        # 默认 OpenAI 兼容（大多数中转 API）
        return "openai"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list = field(default_factory=list)
    stop_reason: str = ""
    usage: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


def _log(msg: str):
    print(f"[LLM] {msg}")


class UnifiedLLM:
    """
    统一 LLM 客户端。
    
    核心设计：一个类处理所有 Provider，不需要继承/工厂模式。
    保留旧 BlenderAgent._call_api 的重试逻辑和错误处理。
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self.provider = config.detect_provider()
        _log(f"Provider: {self.provider}, Model: {config.model}")

    def chat(
        self,
        messages: list,
        system: str = "",
        tools: list = None,
    ) -> LLMResponse:
        """发送对话请求，自动适配 Provider 格式"""
        url = self._build_url()
        payload = self._build_payload(messages, system, tools)
        headers = self._build_headers()

        data = json.dumps(payload).encode("utf-8")
        _log(f"Request: {url}, payload={len(data)} bytes, tools={len(tools) if tools else 0}")

        raw = self._request_with_retry(url, data, headers)
        response = self._parse_response(raw)
        _log(f"Response: text={len(response.text)}, tool_calls={len(response.tool_calls)}, stop={response.stop_reason}")
        return response

    def format_tool_results(self, tool_results: list) -> list:
        """将工具执行结果格式化为可追加到 messages 的消息"""
        if self.provider == "anthropic":
            return [{"role": "user", "content": tool_results}]
        else:
            return tool_results

    def format_assistant_message(self, response: LLMResponse) -> dict:
        """将 LLM 响应格式化为 assistant 消息（用于多轮对话）"""
        if self.provider == "anthropic":
            content = []
            if response.text:
                content.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            return {"role": "assistant", "content": content}
        else:
            msg = {"role": "assistant", "content": response.text or None}
            if response.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]
            return msg

    def format_tool_result(self, tool_call_id: str, result: str, is_error: bool = False) -> dict:
        """格式化单个工具结果"""
        if self.provider == "anthropic":
            msg = {
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": result,
            }
            if is_error:
                msg["is_error"] = True
            return msg
        else:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result,
            }

    # ========== 内部方法 ==========

    def _build_url(self) -> str:
        base = self.config.api_base.rstrip("/")
        if self.provider == "anthropic":
            if "/v1" in base:
                return f"{base}/messages"
            return f"{base}/v1/messages"
        else:
            if base.endswith("/chat/completions"):
                return base
            if base.endswith("/v1"):
                return f"{base}/chat/completions"
            if "/v1" in base:
                return f"{base}/chat/completions"
            return f"{base}/v1/chat/completions"

    def _build_headers(self) -> dict:
        if self.provider == "anthropic":
            return {
                "Content-Type": "application/json",
                "x-api-key": self.config.api_key,
                "anthropic-version": "2023-06-01",
            }
        else:
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            return headers

    def _build_payload(self, messages: list, system: str, tools: list) -> dict:
        if self.provider == "anthropic":
            return self._build_anthropic_payload(messages, system, tools)
        else:
            return self._build_openai_payload(messages, system, tools)

    def _build_anthropic_payload(self, messages, system, tools) -> dict:
        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = self._convert_tools_anthropic(tools)
            payload["tool_choice"] = {"type": "auto"}
        return payload

    def _build_openai_payload(self, messages, system, tools) -> dict:
        final_messages = []
        if system:
            final_messages.append({"role": "system", "content": system})
        for msg in messages:
            converted = self._convert_msg_to_openai(msg)
            if isinstance(converted, list):
                final_messages.extend(converted)
            elif converted:
                final_messages.append(converted)

        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": final_messages,
        }
        if tools:
            payload["tools"] = self._convert_tools_openai(tools)
            payload["tool_choice"] = "auto"
        return payload

    def _convert_tools_anthropic(self, tools: list) -> list:
        result = []
        for t in tools:
            result.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema") or t.get("parameters", {}),
            })
        return result

    def _convert_tools_openai(self, tools: list) -> list:
        result = []
        for t in tools:
            result.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema") or t.get("parameters", {}),
                },
            })
        return result

    def _convert_msg_to_openai(self, msg: dict):
        """Anthropic 消息格式 → OpenAI 格式"""
        role = msg.get("role", "")
        content = msg.get("content", "")

        # 已经是 OpenAI 格式
        if role in ("system", "tool") or (role == "assistant" and "tool_calls" in msg):
            return msg

        # Anthropic tool_result 数组 → OpenAI tool messages
        if role == "user" and isinstance(content, list):
            results = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    results.append({
                        "role": "tool",
                        "tool_call_id": item.get("tool_use_id", ""),
                        "content": item.get("content", ""),
                    })
            return results if results else msg

        # Anthropic assistant content 数组 → OpenAI
        if role == "assistant" and isinstance(content, list):
            text_parts = []
            tool_calls = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                            },
                        })
            result = {"role": "assistant", "content": "".join(text_parts) or None}
            if tool_calls:
                result["tool_calls"] = tool_calls
            return result

        return msg

    def _parse_response(self, raw: dict) -> LLMResponse:
        if self.provider == "anthropic":
            return self._parse_anthropic(raw)
        else:
            return self._parse_openai(raw)

    def _parse_anthropic(self, raw: dict) -> LLMResponse:
        text_parts = []
        tool_calls = []
        for block in raw.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=block.get("input", {}),
                ))
        usage = raw.get("usage", {})
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=raw.get("stop_reason", ""),
            usage={"input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)},
            raw=raw,
        )

    def _parse_openai(self, raw: dict) -> LLMResponse:
        choice = raw.get("choices", [{}])[0]
        msg = choice.get("message", {})
        tool_calls = []
        for tc in msg.get("tool_calls", []):
            func = tc.get("function", {})
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(
                id=tc.get("id", ""),
                name=func.get("name", ""),
                arguments=args,
            ))
        usage = raw.get("usage", {})
        return LLMResponse(
            text=msg.get("content", "") or "",
            tool_calls=tool_calls,
            stop_reason=choice.get("finish_reason", ""),
            usage={"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0)},
            raw=raw,
        )

    def _request_with_retry(self, url: str, data: bytes, headers: dict) -> dict:
        max_retries = 3
        backoff = [5, 15, 30]
        last_error = ""

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                _log(f"Attempt {attempt + 1}/{max_retries}...")
                with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)

            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8")
                friendly = self._extract_error(error_body)
                last_error = f"API {e.code}: {friendly}"
                _log(f"HTTP {e.code}: {error_body[:500]}")

                if e.code == 413:
                    raise LLMError(f"请求体过大（{len(data)} bytes）", e.code)
                if self._is_permanent_error(error_body):
                    raise LLMError(last_error, e.code)
                if e.code in (500, 502, 503, 529) and attempt < max_retries - 1:
                    time.sleep(backoff[attempt])
                    continue
                raise LLMError(last_error, e.code)

            except urllib.error.URLError as e:
                last_error = f"网络错误: {e.reason}"
                _log(last_error)
                if attempt < max_retries - 1:
                    time.sleep(backoff[attempt])
                    continue
                raise LLMError(last_error, 0)

            except LLMError:
                raise
            except Exception as e:
                raise LLMError(f"未知错误: {e}", 0)

        raise LLMError(f"API 调用失败（重试{max_retries}次）: {last_error}", 0)

    @staticmethod
    def _extract_error(body: str) -> str:
        try:
            return json.loads(body).get("error", {}).get("message", body[:500])
        except (json.JSONDecodeError, AttributeError):
            return body[:500]

    @staticmethod
    def _is_permanent_error(body: str) -> bool:
        keywords = ["invalid_api_key", "authentication_error", "permission_denied", "卡池被封", "账户余额"]
        lower = body.lower()
        return any(k.lower() in lower for k in keywords)


class LLMError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code
