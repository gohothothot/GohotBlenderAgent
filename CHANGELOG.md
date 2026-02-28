# Changelog

All notable changes to this project are documented in this file.

## 2026-02-27

### Added
- 新增 `scene_setup_daylight_water` 工具（`scene_tools.py`）：
  - 自动配置 Nishita Sky、SUN 灯、EEVEE SSR/Refraction
  - 用于提升水面/玻璃在日光场景下的反射表现
- 新增权限策略模块 `permission_guard.py`：
  - 工具风险分级
  - 一次性授权机制
  - 可按类别控制（破坏性/写文件/网络与 Meshy）
- 新增脚本/伪调用守卫：
  - `core/safety_guard.py`
  - `core/pseudo_tool_parser.py`
- UI 新增可观测字段：
  - 工具执行状态
  - 伪调用兜底命中次数
  - 处理中提醒与确认提醒

### Changed
- `core/agent.py` 与 `core/structured_agent.py`：
  - 强化“工具优先”执行链路，减少纯文本替代执行
  - 增加 `NO_TOOLCALL` / `WRONG_TOOLSET` 识别与纠偏
  - 支持从文本恢复伪工具调用并继续执行（函数调用格式与 JSON 伪调用）
- `chat_ui.py`：
  - 新增权限确认 UI（允许一次/拒绝）
  - 新增无工具调用自动回退（native <-> structured）
  - 增加阅读模式、阅读缩放、主题预设（Catppuccin 风格）
  - Mocha 风格分区布局优化（会话/输入/操作）
- `tool_definitions.py` / `core/tools.py`：
  - 注册并暴露新工具 `scene_setup_daylight_water`
  - 调整工具组覆盖，减少“可用工具不在列表”问题
- `README.md`：
  - 完整同步当前功能与故障排查说明

### Fixed
- 修复工具执行后误报 `[NO_TOOLCALL]` 导致流程中断的问题
- 修复“模型口胡但不执行”场景：
  - 识别并执行 `tool_name(...)` 文本伪调用
  - 识别并执行 `{"tool_name": {...}}` JSON 伪调用
- 修复部分回退与收尾判定导致的“执行到一半停住”问题（保守放宽收尾判定）

### Notes
- 本次更新以“稳定性优先”为目标，MCP 主框架不做破坏性改动。
- 本地变更缓存位于 `.agent-cache/`，并通过 `.git/info/exclude` 排除上传。
