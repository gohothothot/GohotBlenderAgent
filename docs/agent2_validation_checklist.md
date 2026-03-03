# Agent 2.0 集成验证清单

## 0. 基础前提
- Blender Addon 已启用，`MCP Bridge` 启动成功（`127.0.0.1:9876`）。
- Agent 模式切换到 `Plan Orchestrator`。
- API Key 与模型配置可用。
- 可用 Python 解释器（若系统无 python，请设置 `BLENDER_PYTHON`）。

### 推荐测试命令
- PowerShell：`.\scripts\run_backend_tests.ps1`
- 指定解释器：`.\scripts\run_backend_tests.ps1 -PythonPath "C:\path\to\python.exe"`
- 也可先设置环境变量：`$env:BLENDER_PYTHON="C:\path\to\python.exe"`

## 1. 通信与协议回归
- 检查 `GET /health` 返回 `ok=true`。
- 检查 `POST /tool` 仅允许白名单工具。
- 用 `object.create_cube` 做一次最小调用，确认场景中出现对象。
- 确认旧调用字段兼容：`tool/action`、`args/params` 都可识别。

## 2. Mini Rewrite + RAG
- 输入口语化需求（包含单位、材质、渲染）。
- UI 计划区确认出现：
  - `[Mini改写] ...`
  - `[RAG命中] glossary=..., recipe=...`
- 结果应包含标准 Blender 术语（如 `Principled BSDF`, `Cycles`, `Bevel`）。

## 3. 三层记忆与检索
- 连续执行 2~3 个相似任务。
- 下一次任务中观察 `[Memory命中]` 大于 0。
- 检查数据库文件是否生成：`cache/memory/agent_memory.db`。
- 随机抽样验证三表有数据：
  - `episodic_memory`
  - `semantic_memory`
  - `procedural_memory`

## 4. ContextBuilder + TokenOptimizer
- 构造长对话（多轮 + 工具结果）。
- 确认未出现上下文失控报错。
- 当上下文接近阈值时，观察是否触发压缩并保持最近轮次可用。
- 如出现压缩，验证关键约束仍保留：
  - normalized instruction
  - RAG 摘要
  - 计划步骤上下文

## 5. Sleep Reflection + Reward
- 每 5 轮后检查是否触发 Light Sleep（后台，不阻塞交互）。
- 触发一次失败再修复成功的任务，确认：
  - 事件记忆被写入
  - 对应 importance 增强（纠错路径应更高）
- 在压缩前检查是否触发 Deep Sleep（由上下文构建模块回调触发）。

## 6. Plan 执行与重试策略
- 输入含 `check/on_fail` 的复杂任务。
- 人为构造一次参数失败，确认重试触发。
- `revise_args` 场景中，检查参数会被钳制（如负 size、0 segments）。
- 最终输出中确认完成/失败步统计正确。

## 7. 回归项（必须通过）
- Meshy 与 Agent 通道完全隔离（输入、历史、处理中状态不串）。
- Native/Structured 模式仍可独立工作（未启用 orchestrator 时）。
- Addon UI 组件正常显示，无注册失败。
- 未出现 `execute_python` 误调用路径。

## 8. 风险点提示
- 若 `sentence-transformers` 不可用，会自动 fallback 为 n-gram 向量，检索质量下降但链路可用。
- backend 模块导入失败时会回落 legacy 路径；需留意日志中 fallback 提示。
- 生产环境建议加一轮真实场景端到端 smoke（建模+材质+渲染+导出）。

