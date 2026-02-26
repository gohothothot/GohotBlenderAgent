"""
Anthropic Claude Provider

支持 Claude 的 tool_use 格式，兼容官方 API 和中转 API。
"""

import json
import urllib.request
import urllib.error
import time
from typing import Optional

from .base import LLMProvider, LLMResponse, LLMConfig, ToolCall


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API Provider"""

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
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
        }

        data = json.dumps(payload).encode("utf-8")
        raw = self._request_with_retry(url, data, headers)
        return self._parse_response(raw)

    def format_tool_result(self, tool_call_id: str, result: str, is_error: bool = False) -> dict:
        """Anthropic 格式的 tool result"""
        return {
            "type": "tool_result",
            "tool_use_id": tool_call_id,
            "content": result,
            **({"is_error": True} if is_error else {}),
        }

    def format_assistant_with_tool_calls(self, response: LLMResponse) -> dict:
        """重建 Anthropic 格式的 assistant 消息（含 tool_use blocks）"""
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

    def format_tool_results_as_messages(self, tool_results: list[dict]) -> list[dict]:
        """Anthropic: 所有 tool_result 包装在一个 user 消息的 content 数组中"""
        return [{"role": "user", "content": tool_results}]

    # ---- internal ----

    def _build_url(self) -> str:
        base = self.config.api_base.rstrip("/")
        if "/v1" in base:
            return f"{base}/messages"
        return f"{base}/v1/messages"

    def _build_payload(self, messages, system, tools, tool_choice) -> dict:
        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = self._convert_tools(tools)
            tc_map = {"auto": {"type": "auto"}, "any": {"type": "any"}, "none": {"type": "none"}}
            payload["tool_choice"] = tc_map.get(tool_choice, {"type": "auto"})
        return payload

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """确保工具定义符合 Anthropic 格式"""
        result = []
        for t in tools:
            tool = {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema") or t.get("parameters", {}),
            }
            result.append(tool)
        return result

    def _parse_response(self, raw: dict) -> LLMResponse:
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
            usage={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
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
                if e.code == 413:
                    raise LLMRequestError(f"请求体过大（{len(data)} bytes）", e.code)
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
            return json.loads(body).get("error", {}).get("message", body[:500])
        except (json.JSONDecodeError, AttributeError):
            return body[:500]


class LLMRequestError(Exception):
    """LLM API 请求错误"""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code
