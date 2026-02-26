"""
core 包 - 多 Agent 系统核心

模块:
- llm.py: 统一 LLM 客户端 (Anthropic/OpenAI/中转)
- agent.py: 主 Agent (Native tool_use 模式)
- structured_agent.py: 结构化 Agent (XML 解析模式)
- router.py: 意图路由器
- tools.py: 工具注册表 + 调度器
- xml_parser.py: XML 工具调用解析器
"""
