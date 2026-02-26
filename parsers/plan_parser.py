"""
Plan Parser - 执行计划解析器

从 Planner Agent 的 LLM 输出中提取结构化执行计划。
"""

import json
import re
from dataclasses import dataclass, field


@dataclass
class PlanStep:
    """执行计划中的一步"""
    step: int
    tool: str
    params: dict = field(default_factory=dict)
    description: str = ""
    depends_on: list = field(default_factory=list)

    # 执行状态（由 Orchestrator 填充）
    status: str = "pending"  # pending | running | success | failed | skipped
    result: dict = field(default_factory=dict)
    error: str = ""


@dataclass
class ExecutionPlan:
    """结构化执行计划"""
    steps: list[PlanStep] = field(default_factory=list)
    summary: str = ""
    rollback_hint: str = ""

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == "success")

    @property
    def failed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "failed"]

    @property
    def is_complete(self) -> bool:
        return all(s.status in ("success", "skipped") for s in self.steps)

    def get_next_step(self) -> PlanStep | None:
        """获取下一个待执行的步骤"""
        for step in self.steps:
            if step.status == "pending":
                # 检查依赖是否满足
                deps_met = all(
                    self.steps[d - 1].status == "success"
                    for d in step.depends_on
                    if 0 < d <= len(self.steps)
                )
                if deps_met:
                    return step
        return None


def parse_plan(text: str) -> ExecutionPlan:
    """
    从 LLM 输出解析执行计划

    支持多种格式：
    1. JSON 格式（推荐）
    2. XML 格式
    3. 编号列表格式（回退）
    """
    # 1. 尝试 JSON
    plan = _parse_json_plan(text)
    if plan and plan.steps:
        return plan

    # 2. 尝试 XML
    plan = _parse_xml_plan(text)
    if plan and plan.steps:
        return plan

    # 3. 回退：编号列表
    plan = _parse_numbered_plan(text)
    if plan and plan.steps:
        return plan

    # 4. 最终回退：整个文本作为单步
    return ExecutionPlan(
        steps=[PlanStep(step=1, tool="", description=text[:500])],
        summary="无法解析计划，作为单步执行",
    )


def _parse_json_plan(text: str) -> ExecutionPlan | None:
    """从 JSON 格式解析"""
    # 找 JSON 数组或对象
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',  # markdown code block
        r'\{[\s\S]*"(?:plan|steps)"[\s\S]*\}',  # JSON object with plan/steps
        r'\[[\s\S]*\{[\s\S]*"(?:tool|step)"[\s\S]*\}[\s\S]*\]',  # JSON array
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            data = json.loads(match.group(1) if match.lastindex else match.group())
            return _json_to_plan(data)
        except (json.JSONDecodeError, KeyError, IndexError):
            continue

    return None


def _json_to_plan(data) -> ExecutionPlan:
    """将 JSON 数据转为 ExecutionPlan"""
    steps_data = []
    summary = ""
    rollback = ""

    if isinstance(data, list):
        steps_data = data
    elif isinstance(data, dict):
        steps_data = data.get("plan") or data.get("steps") or []
        summary = data.get("summary", "")
        rollback = data.get("rollback_strategy") or data.get("rollback_hint", "")

    steps = []
    for i, s in enumerate(steps_data):
        if isinstance(s, dict):
            steps.append(PlanStep(
                step=s.get("step", i + 1),
                tool=s.get("tool", s.get("action", "")),
                params=s.get("params", s.get("arguments", {})),
                description=s.get("description", s.get("desc", "")),
                depends_on=s.get("depends_on", []),
            ))

    return ExecutionPlan(steps=steps, summary=summary, rollback_hint=rollback)


def _parse_xml_plan(text: str) -> ExecutionPlan | None:
    """从 XML 格式解析"""
    step_pattern = r'<step[^>]*order="(\d+)"[^>]*tool="([^"]*)"[^>]*>(.*?)</step>'
    matches = re.findall(step_pattern, text, re.DOTALL)

    if not matches:
        # 尝试另一种 XML 格式
        step_pattern = r'<step>(.*?)</step>'
        step_blocks = re.findall(step_pattern, text, re.DOTALL)
        if not step_blocks:
            return None

        steps = []
        for i, block in enumerate(step_blocks):
            tool = _xml_extract(block, "tool", "")
            params_str = _xml_extract(block, "params", "{}")
            desc = _xml_extract(block, "description", "")
            try:
                params = json.loads(params_str)
            except json.JSONDecodeError:
                params = {}
            steps.append(PlanStep(step=i + 1, tool=tool, params=params, description=desc))

        return ExecutionPlan(steps=steps) if steps else None

    steps = []
    for order, tool, body in matches:
        params_str = _xml_extract(body, "params", "{}")
        desc = _xml_extract(body, "description", body.strip())
        try:
            params = json.loads(params_str)
        except json.JSONDecodeError:
            params = {}
        steps.append(PlanStep(
            step=int(order), tool=tool, params=params, description=desc,
        ))

    return ExecutionPlan(steps=steps) if steps else None


def _xml_extract(text: str, tag: str, default: str = "") -> str:
    match = re.search(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
    return match.group(1).strip() if match else default


def _parse_numbered_plan(text: str) -> ExecutionPlan | None:
    """从编号列表解析（最宽松的格式）"""
    # 匹配 "1. xxx" 或 "1) xxx" 或 "步骤1: xxx"
    pattern = r'(?:^|\n)\s*(?:步骤\s*)?(\d+)[.):\s]+(.+?)(?=\n\s*(?:步骤\s*)?\d+[.):\s]|\Z)'
    matches = re.findall(pattern, text, re.DOTALL)

    if not matches:
        return None

    steps = []
    for num, desc in matches:
        desc = desc.strip()
        # 尝试从描述中提取工具名
        tool = _guess_tool_from_description(desc)
        steps.append(PlanStep(step=int(num), tool=tool, description=desc))

    return ExecutionPlan(steps=steps) if steps else None


def _guess_tool_from_description(desc: str) -> str:
    """从描述文本猜测工具名"""
    desc_lower = desc.lower()
    tool_hints = {
        "创建材质": "shader_create_material",
        "create material": "shader_create_material",
        "清除节点": "shader_clear_nodes",
        "添加节点": "shader_batch_add_nodes",
        "连接节点": "shader_batch_link_nodes",
        "创建": "create_primitive",
        "删除": "delete_object",
        "移动": "transform_object",
        "旋转": "transform_object",
        "灯光": "scene_add_light",
        "相机": "scene_add_camera",
        "渲染": "render_image",
        "搜索": "web_search_blender",
    }
    for hint, tool in tool_hints.items():
        if hint in desc_lower:
            return tool
    return ""
