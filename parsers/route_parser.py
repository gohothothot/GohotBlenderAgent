"""
Route Parser - 路由决策解析器

从 Router Agent 的输出中提取意图分类。
支持规则引擎（零 LLM）和 LLM 输出解析两种模式。
"""

import json
import re
from dataclasses import dataclass


@dataclass
class RouteDecision:
    """路由决策结果"""
    intent: str  # create | modify | query | delete | render | generate_3d | search | shader_complex | toon | animation
    domain: str  # scene | shader | animation | toon | meshy | render | general
    complexity: str  # simple | complex
    confidence: float = 1.0

    @property
    def is_complex(self) -> bool:
        return self.complexity == "complex"


# ========== 规则引擎（推荐，零幻觉） ==========

# 关键词 → (intent, domain) 映射
_KEYWORD_RULES = [
    # Meshy / 3D 生成
    (["meshy", "文生3d", "图生3d", "生成3d", "生成模型", "text to 3d", "image to 3d"],
     "generate_3d", "meshy"),

    # 卡通/NPR
    (["卡通", "二次元", "toon", "npr", "anime", "漫画风"],
     "toon", "toon"),

    # 动画
    (["动画", "animation", "driver", "关键帧", "keyframe", "uv滚动", "uv旋转"],
     "animation", "animation"),

    # 渲染
    (["渲染", "render", "采样", "samples", "分辨率", "resolution", "eevee", "cycles"],
     "render", "render"),

    # 搜索/查询知识
    (["搜索", "search", "查找", "参考", "教程", "tutorial"],
     "search", "general"),

    # 复杂着色器
    (["程序化材质", "procedural", "节点", "node", "shader", "着色器",
      "colorramp", "noise", "voronoi", "bump", "normal map",
      "水材质", "冰材质", "熔岩", "水晶", "大理石", "木纹"],
     "shader_complex", "shader"),

    # 材质（简单）
    (["材质", "material", "颜色", "color", "金属", "metallic", "粗糙", "roughness",
      "玻璃", "glass", "金", "gold", "塑料", "plastic"],
     "modify", "shader"),

    # 场景修改
    (["移动", "旋转", "缩放", "transform", "修改", "调整", "修改器", "modifier",
      "灯光", "light", "相机", "camera", "环境", "world", "hdri",
      "复制", "duplicate", "父级", "parent", "可见", "visibility"],
     "modify", "scene"),

    # 创建
    (["创建", "添加", "新建", "create", "add", "生成",
      "立方体", "球体", "圆柱", "平面", "cube", "sphere", "cylinder", "plane"],
     "create", "scene"),

    # 删除
    (["删除", "移除", "清除", "delete", "remove", "clear"],
     "modify", "scene"),

    # 查询
    (["查看", "获取", "列出", "信息", "inspect", "list", "get", "info",
      "有哪些", "是什么", "怎么样", "当前"],
     "query", "general"),
]

# 复杂任务关键词
_COMPLEX_KEYWORDS = [
    "场景", "完整", "整个", "所有", "批量", "多个",
    "程序化", "procedural", "复杂", "高级",
    "从零开始", "从头", "重新创建",
    "参考这个", "照着", "模仿",
    "并且", "然后", "接着", "同时", "以及",
]


def parse_route(user_message: str) -> RouteDecision:
    """
    规则引擎路由 — 零 LLM 调用，零幻觉

    通过关键词匹配确定意图和领域。
    """
    msg_lower = user_message.lower()

    # 匹配意图和领域
    intent = "general"
    domain = "general"
    best_score = 0

    for keywords, kw_intent, kw_domain in _KEYWORD_RULES:
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > best_score:
            best_score = score
            intent = kw_intent
            domain = kw_domain

    # 判断复杂度
    complexity = "simple"
    complex_score = sum(1 for kw in _COMPLEX_KEYWORDS if kw in msg_lower)
    # 消息长度也是复杂度信号
    if complex_score >= 2 or len(user_message) > 100:
        complexity = "complex"

    # 特殊规则：某些意图总是 complex
    if intent in ("shader_complex", "toon", "generate_3d"):
        complexity = "complex"

    return RouteDecision(
        intent=intent,
        domain=domain,
        complexity=complexity,
        confidence=min(best_score / 3.0, 1.0) if best_score > 0 else 0.5,
    )


def parse_route_from_llm(text: str) -> RouteDecision:
    """
    从 LLM 输出解析路由决策（备用方案）

    期望 LLM 输出 JSON 或 XML 格式。
    """
    # 尝试 JSON
    try:
        # 提取 JSON block
        json_match = re.search(r'\{[^{}]*"intent"[^{}]*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return RouteDecision(
                intent=data.get("intent", "general"),
                domain=data.get("domain", "general"),
                complexity=data.get("complexity", "simple"),
            )
    except (json.JSONDecodeError, KeyError):
        pass

    # 尝试 XML
    intent_match = re.search(r'<intent>(.*?)</intent>', text)
    domain_match = re.search(r'<domain>(.*?)</domain>', text)
    complexity_match = re.search(r'<complexity>(.*?)</complexity>', text)

    if intent_match:
        return RouteDecision(
            intent=intent_match.group(1).strip(),
            domain=domain_match.group(1).strip() if domain_match else "general",
            complexity=complexity_match.group(1).strip() if complexity_match else "simple",
        )

    # 回退到规则引擎
    return parse_route(text)
