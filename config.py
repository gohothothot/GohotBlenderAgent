CLAUDE_API_BASE = "https://api.anthropic.com"
CLAUDE_API_KEY = ""
CLAUDE_MODEL = "claude-sonnet-4-5"

MAX_HISTORY_TURNS = 20
CODE_EXECUTION_TIMEOUT = 30

AVAILABLE_MODELS = [
    ("claude-sonnet-4-5", "Claude Sonnet 4.5", "平衡性能和速度"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6", "最新 Sonnet"),
    ("claude-sonnet-4-5-kiro", "Claude Sonnet 4.5 Kiro", "Kiro 优化版"),
    ("claude-opus-4-5-kiro", "Claude Opus 4.5 Kiro", "Opus Kiro"),
    ("claude-opus-4-6-kiro", "Claude Opus 4.6 Kiro", "最新 Opus Kiro"),
    ("claude-opus-4-5-gemini", "Claude Opus 4.5 Gemini", "Opus Gemini 混合"),
    ("claude-haiku-4-5", "Claude Haiku 4.5", "最快速度"),
    ("gpt-5.2-codex", "GPT-5.2 Codex", "代码专精"),
    ("gpt-5.3-codex", "GPT-5.3 Codex", "400K上下文 代码专精"),
    ("gemini-3-flash-preview", "Gemini 3 Flash", "1M上下文 快速"),
    ("gemini-3-pro-preview", "Gemini 3 Pro", "1M上下文 强性能"),
    ("gemini-3-pro-image-preview", "Gemini 3 Pro Image", "支持图片输出"),
    ("glm-5", "GLM-5", "智谱最新"),
]
