CLAUDE_API_BASE = "https://api.anthropic.com"
CLAUDE_API_KEY = ""
CLAUDE_MODEL = "claude-sonnet-4-5"

MAX_HISTORY_TURNS = 20
CODE_EXECUTION_TIMEOUT = 30

AVAILABLE_MODELS = [
    ("claude-sonnet-4-5", "Claude Sonnet 4.5", "平衡性能和速度"),
    ("claude-opus-4-5-20251101", "Claude Opus 4.5", "最强性能"),
    ("claude-opus-4-5-kiro", "Claude Opus 4.5 Kiro", "Kiro 优化版"),
    ("claude-opus-4-5-max", "Claude Opus 4.5 Max", "最大上下文"),
    ("claude-opus-4-6-kiro", "Claude Opus 4.6 Kiro", "最新 Kiro 版"),
    ("claude-haiku-4-5", "Claude Haiku 4.5", "最快速度"),
    ("gpt-5.3-codex", "GPT-5.3 Codex", "400K上下文 代码专精"),
    ("gemini-3-flash-preview", "Gemini 3 Flash", "1M上下文 快速"),
    ("gemini-3-pro-preview", "Gemini 3 Pro", "1M上下文 强性能"),
    ("gemini-3-pro-image-preview", "Gemini 3 Pro Image", "1M上下文 支持图片输出"),
    ("glm-4.7", "GLM 4.7", "智谱 128K上下文"),
]
