"""
Validator Agent - 结果验证

大部分验证用规则引擎，复杂场景可选 LLM 语义验证。
"""

import json
from dataclasses import dataclass, field
from ..llm.base import LLMProvider
from ..context.prompts import AgentPrompts


@dataclass
class ValidationResult:
    passed: bool = True
    issues: list = field(default_factory=list)
    suggestion: str = ""


class ValidatorAgent:

    def __init__(self, llm: LLMProvider = None):
        self._llm = llm

    def validate_tool_result(self, tool_name: str, result: dict) -> ValidationResult:
        if not result.get("success"):
            return ValidationResult(
                passed=False,
                issues=[f"{tool_name} 失败: {result.get('error', '未知错误')}"],
                suggestion="检查参数是否正确，或先查询当前状态",
            )
        return ValidationResult(passed=True)

    def validate_plan_execution(
        self,
        original_request: str,
        steps_summary: list[str],
    ) -> ValidationResult:
        failed = [s for s in steps_summary if s.startswith("[FAIL]")]
        if failed:
            return ValidationResult(
                passed=False,
                issues=failed,
                suggestion="部分步骤失败，建议检查失败原因后重试",
            )

        if self._llm:
            return self._validate_with_llm(original_request, steps_summary)

        return ValidationResult(passed=True)

    def _validate_with_llm(
        self, original_request: str, steps_summary: list[str],
    ) -> ValidationResult:
        try:
            content = (
                f"用户需求: {original_request}\n\n"
                f"执行结果:\n" + "\n".join(f"  {s}" for s in steps_summary) +
                "\n\n请验证执行结果是否满足用户需求。"
            )
            response = self._llm.chat(
                messages=[{"role": "user", "content": content}],
                system=AgentPrompts.VALIDATOR,
            )
            return self._parse_validation(response.text)
        except Exception:
            return ValidationResult(passed=True)

    @staticmethod
    def _parse_validation(text: str) -> ValidationResult:
        try:
            import re
            match = re.search(r'\{[^{}]*"passed"[^{}]*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return ValidationResult(
                    passed=data.get("passed", True),
                    issues=data.get("issues", []),
                    suggestion=data.get("suggestion", ""),
                )
        except (json.JSONDecodeError, KeyError):
            pass
        return ValidationResult(passed=True)
