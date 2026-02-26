"""
OpenAI Compatible Provider

支持 OpenAI API 格式，同时兼容大多数中转 API（one-api, new-api 等）。
"""

import json
import urllib.request
import urllib.error
import time
import uuid

from .base import LLMProvider, LLMResponse, LLMConfig, ToolCall
from .anthropic_provider import LLMRequestError


class OpenAIProvider(LLMProvider):
    """OpenAI / OpenAI-compatible API Provider"""

    def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        url = self._build_url()
        payload = self._build_payload(messages, system, tools, tool_choice)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

        data = json.dumps(payload).encode("utf-8")
        raw = self._request_with_retry(url, data, headers)
        return self._parse_response(raw)

    def format_tool_result(self, tool_call_id: str, result: str, is_error: bool = False) -> dict:
        """OpenAI 格式的 tool result"""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }

    def format_assistant_with_tool_calls(self, response: LLMResponse) -> dict:
        """重建 OpenAI 格式的 assistant 消息（含 tool_calls）"""
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

    # ---- internal ----

    def _build_url(self) -> str:
        base = self.config.api_base.rstrip("/")
        # 兼容各种 base URL 格式
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        if "/v1" in base:
            # e.g. https://xxx.com/v1/some/path → append
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _build_payload(self, messages, system, tools, tool_choice) -> dict:
        # OpenAI 把 system 放在 messages 里
        final_messages = []
        if system:
            final_messages.append({"role": "system", "content": system})

        # 转换 messages 格式（Anthropic → OpenAI 兼容）
        for msg in messages:
            converted = self._convert_message(msg)
            if converted:
                if isinstance(converted, list):
                    final_messages.extend(converted)
                else:
                    final_messages.append(converted)

        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": final_messages,
        }

        if tools:
            payload["tools"] = self._convert_tools(tools)
            if tool_choice == "none":
                payload["tool_choice"] = "none"
            elif tool_choice == "any":
                payload["tool_choice"] = "required"
            else:
                payload["tool_choice"] = "auto"

        return payload

    def _convert_message(self, msg: dict) -> dict | list[dict] | None:
        """将统一消息格式转为 OpenAI 格式"""
        role = msg.get("role", "")
        content = msg.get("content", "")

        # 已经是 OpenAI 格式
        if role in ("system", "tool") or (role == "assistant" and "tool_calls" in msg):
            return msg

        # Anthropic 格式的 assistant 消息（content 是 list）
        if role == "assistant" and isinstance(content, list):
            text_parts = []
            tool_calls = []
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                        },
                    })
            result = {"role": "assistant", "content": "".join(text_parts) or None}
            if tool_calls:
                result["tool_calls"] = tool_calls
            return result

        # Anthropic 格式的 user 消息（content 是 tool_result list）
        if role == "user" and isinstance(content, list):
            results = []
            for item in content:
                if item.get("type") == "tool_result":
                    results.append({
                        "role": "tool",
                        "tool_call_id": item.get("tool_use_id", ""),
                        "content": item.get("content", ""),
                    })
                elif item.get("type") == "text":
                    results.append({"role": "user", "content": item.get("text", "")})
                elif item.get("type") == "image":
                    # 简化处理：跳过图片
                    pass
            return results if results else None

        # 普通文本消息
        return {"role": role, "content": str(content)}

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """转换为 OpenAI function calling 格式"""
        result = []
        for t in tools:
            schema = t.get("input_schema") or t.get("parameters", {})
            result.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": schema,
                },
            })
        return result

    def _parse_response(self, raw: dict) -> LLMResponse:
        choices = raw.get("choices", [])
        if not choices:
            return LLMResponse(text="", stop_reason="error", raw=raw)

        message = choices[0].get("message", {})
        text = message.get("content", "") or ""
        tool_calls = []

        for tc in message.get("tool_calls", []):
            func = tc.get("function", {})
            try:
                args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(
                id=tc.get("id", str(uuid.uuid4())),
                name=func.get("name", ""),
                arguments=args,
            ))

        finish = choices[0].get("finish_reason", "")
        stop_map = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}

        usage = raw.get("usage", {})
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_map.get(finish, finish),
            usage={
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
            raw=raw,
        )

    def _request_with_retry(self, url: str, data: bytes, headers: dict) -> dict:
        max_retries = 3
        backoff = [5, 15, 30]

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8")
                if e.code in (500, 502, 503, 529) and attempt < max_retries - 1:
                    time.sleep(backoff[attempt])
                    continue
                msg = self._extract_error_msg(body)
                raise LLMRequestError(f"API {e.code}: {msg}", e.code)

            except urllib.error.URLError as e:
                if attempt < max_retries - 1:
                    time.sleep(backoff[attempt])
                    continue
                raise LLMRequestError(f"网络错误: {e.reason}", 0)

        raise LLMRequestError("API 调用失败（重试耗尽）", 0)

    @staticmethod
    def _extract_error_msg(body: str) -> str:
        try:
            err = json.loads(body)
            return err.get("error", {}).get("message", "") or str(err)[:500]
        except (json.JSONDecodeError, AttributeError):
            return body[:500]
