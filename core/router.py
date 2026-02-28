"""
意图路由器 — 纯规则引擎，零 LLM 调用
根据关键词匹配确定用户意图和领域，决定使用哪些工具子集。
[DEVLOG]
- 2026-02-26: 初始版本。纯关键词匹配，支持中英文关键词。
  复杂度判断基于关键词计数 + 消息长度。
"""

from dataclasses import dataclass


@dataclass
class Route:
    intent: str      # create|modify|delete|query|shader|toon|animation|render|search|generate_3d|general
    domain: str      # scene|shader|animation|toon|meshy|render|general
    complexity: str   # simple|complex

    @property
    def is_complex(self) -> bool:
        return self.complexity == "complex"


# 关键词 → (intent, domain)
_KEYWORD_MAP = {
    # 着色器
    "材质": ("shader", "shader"), "着色器": ("shader", "shader"), "shader": ("shader", "shader"),
    "节点": ("shader", "shader"), "pbr": ("shader", "shader"), "bsdf": ("shader", "shader"),
    "纹理": ("shader", "shader"), "贴图": ("shader", "shader"), "uv": ("shader", "shader"),
    "透明": ("shader", "shader"), "玻璃": ("shader", "shader"), "金属": ("shader", "shader"),
    "发光": ("shader", "shader"), "emission": ("shader", "shader"),
    "水": ("shader", "shader"), "冰": ("shader", "shader"),
    # 卡通
    "卡通": ("toon", "toon"), "toon": ("toon", "toon"), "二次元": ("toon", "toon"),
    "npr": ("toon", "toon"), "cartoon": ("toon", "toon"), "描边": ("toon", "toon"),
    # 动画
    "动画": ("animation", "animation"), "关键帧": ("animation", "animation"),
    "driver": ("animation", "animation"), "驱动器": ("animation", "animation"),
    "滚动": ("animation", "animation"), "旋转动画": ("animation", "animation"),
    # 场景
    "灯光": ("modify", "scene"), "相机": ("modify", "scene"), "摄像机": ("modify", "scene"),
    "修改器": ("modify", "scene"), "集合": ("modify", "scene"), "世界": ("modify", "scene"),
    "环境": ("modify", "scene"), "hdri": ("modify", "scene"),
    # 创建
    "创建": ("create", "scene"), "添加": ("create", "scene"), "新建": ("create", "scene"),
    "生成": ("create", "scene"), "做一个": ("create", "scene"), "做个": ("create", "scene"),
    # 删除
    "删除": ("delete", "scene"), "移除": ("delete", "scene"), "清除": ("delete", "scene"),
    # 查询
    "查看": ("query", "general"), "列出": ("query", "general"), "获取": ("query", "general"),
    "信息": ("query", "general"), "检查": ("query", "general"), "状态": ("query", "general"),
    # 渲染
    "渲染": ("render", "render"), "render": ("render", "render"), "输出": ("render", "render"),
    # 搜索
    "搜索": ("search", "general"), "search": ("search", "general"), "查找": ("search", "general"),
    "参考": ("search", "general"), "教程": ("search", "general"),
    # 3D 生成
    "meshy": ("generate_3d", "meshy"), "文生3d": ("generate_3d", "meshy"),
    "图生3d": ("generate_3d", "meshy"), "ai生成": ("generate_3d", "meshy"),
}

# 复杂任务关键词
_COMPLEX_KEYWORDS = [
    "场景", "完整", "整个", "所有", "批量", "多个",
    "程序化", "procedural", "复杂", "高级",
    "从零开始", "从头", "重新创建",
    "参考这个", "照着", "模仿",
    "并且", "然后", "接着", "同时", "以及",
]


def route(message: str) -> Route:
    """根据用户消息路由到合适的意图和领域"""
    msg = message.lower()

    # 优先识别 Meshy/3D 生成意图，避免被通用“生成/创建”关键词提前截获
    meshy_markers = ("meshy", "文生3d", "图生3d", "ai生成", "text to 3d", "image to 3d")
    if any(k in msg for k in meshy_markers):
        intent = "generate_3d"
        domain = "meshy"
    else:
        # 关键词匹配
        intent = "general"
        domain = "general"
        for keyword, (kw_intent, kw_domain) in _KEYWORD_MAP.items():
            if keyword in msg:
                intent = kw_intent
                domain = kw_domain
                break

    # 复杂度判断
    complex_score = sum(1 for kw in _COMPLEX_KEYWORDS if kw in msg)
    if complex_score >= 2 or len(message) > 150:
        complexity = "complex"
    else:
        complexity = "simple"

    return Route(intent=intent, domain=domain, complexity=complexity)
