"""
XML 工具调用解析器

从 LLM 纯文本输出中提取结构化工具调用。
LLM 只需生成文本 + XML 标签，工具由本解析器触发。

[DEVLOG]
- 2026-02-26: 初始版本。支持 <tool_call> XML 格式解析。
  支持嵌套 JSON 参数、多工具调用、容错解析。

XML 格式：
  <tool_call name="工具名">
    <param name="参数名">值</param>
    <param name="参数名">{"key": "value"}</param>
  </tool_call>

也支持 JSON 内联格式（兼容某些 LLM 偏好）：
  <tool_call name="工具名">
  {"primitive_type": "cube", "location": [0, 0, 1]}
  </tool_call>
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


def _log(msg: str):
    print(f"[XMLParser] {msg}")


@dataclass
class ParsedToolCall:
    """解析出的工具调用"""
    id: str
    name: str
    arguments: dict

    @staticmethod
    def generate_id() -> str:
        return f"xml_{uuid.uuid4().hex[:12]}"


@dataclass
class ParseResult:
    """解析结果"""
    text: str                           # 去除工具调用后的纯文本
    tool_calls: List[ParsedToolCall]    # 提取出的工具调用
    raw_text: str                       # 原始文本（含 XML）

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


# ========== 主解析函数 ==========

# 匹配 <tool_call name="xxx">...</tool_call>
_TOOL_CALL_PATTERN = re.compile(
    r'<tool_call\s+name=["\']([^"\']+)["\']\s*>(.*?)</tool_call>',
    re.DOTALL
)

# 匹配 <param name="xxx">...</param>
_PARAM_PATTERN = re.compile(
    r'<param\s+name=["\']([^"\']+)["\']\s*>(.*?)</param>',
    re.DOTALL
)


def parse(text: str) -> ParseResult:
    """
    从 LLM 文本输出中解析工具调用。
    
    返回 ParseResult，包含：
    - text: 去除 XML 标签后的纯文本（给用户看）
    - tool_calls: 提取出的工具调用列表
    - raw_text: 原始文本
    """
    if not text or not text.strip():
        return ParseResult(text="", tool_calls=[], raw_text=text or "")

    tool_calls = []
    matches = list(_TOOL_CALL_PATTERN.finditer(text))

    for match in matches:
        tool_name = match.group(1).strip()
        body = match.group(2).strip()

        # 尝试解析参数
        arguments = _parse_body(body)

        tc = ParsedToolCall(
            id=ParsedToolCall.generate_id(),
            name=tool_name,
            arguments=arguments,
        )
        tool_calls.append(tc)
        _log(f"Parsed: {tool_name}({arguments})")

    # 去除 XML 标签，保留纯文本
    clean_text = _TOOL_CALL_PATTERN.sub("", text).strip()
    # 清理多余空行
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)

    return ParseResult(
        text=clean_text,
        tool_calls=tool_calls,
        raw_text=text,
    )


def _parse_body(body: str) -> dict:
    """
    解析 <tool_call> 内部内容。
    
    支持两种格式：
    1. <param> 标签格式
    2. 纯 JSON 格式
    """
    # 先尝试 <param> 标签
    params = list(_PARAM_PATTERN.finditer(body))
    if params:
        return _parse_params(params)

    # 再尝试纯 JSON
    body_stripped = body.strip()
    if body_stripped.startswith("{"):
        try:
            return json.loads(body_stripped)
        except json.JSONDecodeError:
            pass

    # 最后尝试从 body 中提取 JSON（可能有前后文本）
    json_match = re.search(r'\{[^{}]*\}', body_stripped)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # 无法解析，返回空
    if body_stripped:
        _log(f"Warning: could not parse body: {body_stripped[:100]}")
    return {}


def _parse_params(params: list) -> dict:
    """解析 <param> 标签列表为 dict"""
    result = {}
    for match in params:
        name = match.group(1).strip()
        value_str = match.group(2).strip()
        result[name] = _parse_value(value_str)
    return result


def _parse_value(value_str: str):
    """
    智能解析参数值：
    - JSON 对象/数组 → 解析为 dict/list
    - 数字 → int/float
    - true/false → bool
    - 其他 → str
    """
    if not value_str:
        return ""

    # JSON 对象或数组
    if value_str.startswith(("{", "[")):
        try:
            return json.loads(value_str)
        except json.JSONDecodeError:
            pass

    # 布尔
    if value_str.lower() == "true":
        return True
    if value_str.lower() == "false":
        return False

    # null
    if value_str.lower() == "null":
        return None

    # 数字
    try:
        if "." in value_str:
            return float(value_str)
        return int(value_str)
    except ValueError:
        pass

    # 字符串
    return value_str


# ========== 工具目录生成（给 system prompt 用） ==========

def build_tool_catalog(tools: list) -> str:
    """
    将工具定义列表转换为文本目录，嵌入 system prompt。
    
    比传 JSON schema 给 API 省 token，且 LLM 更容易理解。
    """
    if not tools:
        return ""

    lines = ["=== 可用工具 ===", "使用 XML 格式调用工具：", ""]
    lines.append("<tool_call name=\"工具名\">")
    lines.append("  <param name=\"参数名\">值</param>")
    lines.append("</tool_call>")
    lines.append("")

    for t in tools:
        name = t["name"]
        desc = t.get("description", "")
        schema = t.get("input_schema") or t.get("parameters", {})
        props = schema.get("properties", {})
        required = set(schema.get("required", []))

        # 工具签名
        param_strs = []
        for pname, pdef in props.items():
            ptype = pdef.get("type", "string")
            req = "*" if pname in required else ""
            enum = pdef.get("enum")
            if enum:
                ptype = "|".join(str(e) for e in enum)
            param_strs.append(f"{pname}{req}:{ptype}")

        params_line = ", ".join(param_strs) if param_strs else ""
        lines.append(f"- {name}({params_line}): {desc}")

    lines.append("")
    lines.append("参数带 * 为必填。数组用 JSON 格式如 [1,2,3]。")
    lines.append("每次回复必须包含至少一个 <tool_call>。禁止纯文字回复。")

    return "\n".join(lines)


# ========== 验证 ==========

def validate_tool_call(tc: ParsedToolCall, available_tools: list) -> Optional[str]:
    """
    验证工具调用是否合法。
    返回 None 表示合法，返回错误信息表示不合法。
    """
    tool_names = {t["name"] for t in available_tools}
    if tc.name not in tool_names:
        return f"未知工具: {tc.name}"

    # 找到工具定义
    tool_def = next(t for t in available_tools if t["name"] == tc.name)
    schema = tool_def.get("input_schema") or tool_def.get("parameters", {})
    required = set(schema.get("required", []))

    # 检查必填参数
    missing = required - set(tc.arguments.keys())
    if missing:
        return f"缺少必填参数: {', '.join(missing)}"

    return None
