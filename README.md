# Gohot Blender Agent

AI 驱动的 Blender 助手插件，支持 MCP 工具执行、材质/场景自动化、Meshy 3D 生成与性能可观测。

## 功能特性

- 🤖 **工具优先 AI 助手**：自然语言驱动 Blender 操作，优先调用本地 MCP 工具而不是输出脚本
- 🔀 **双通道聊天**：聊天框可切换 `Agent | Meshy`，彻底隔离两套执行链
- 🔁 **Agent 内双引擎**：`Native Tool Use` 与 `Structured XML`，支持无工具调用自动回退
- 🔐 **权限闸门**：高权限默认可用，高风险操作可弹窗确认（一次性授权）
- 🛑 **中止控制**：UI 一键中止当前请求，避免“AI 长时间思考”卡住
- 🎨 **Meshy AI 集成**：文生3D / 图生3D，支持并发任务与自动导入 PBR 贴图
- 🌤️ **水面日光快速配置**：新增 `scene_setup_daylight_water`（天空+太阳+SSR 一键配置）
- 📊 **性能报告**：内置会话摘要、导出 JSON/CSV
- 🎛️ **UI 阅读模式与主题预设**：支持 Catppuccin 风格预设与面板缩放

## 安装

1. 下载本仓库或 Release 的 zip
2. Blender 中打开：`Edit > Preferences > Add-ons > Install`
3. 选择 zip 或插件目录
4. 启用 `Gohot Blender Agent`

## 配置

在 `Edit > Preferences > Add-ons > Gohot Blender Agent` 中配置：

### AI 设置
- **API 地址 / API Key / 模型**
- **对话通道**
  - `Agent`：负责 Blender MCP 操作（材质、场景、修改器、文件等）
  - `Meshy`：负责 Meshy 文生3D/图生3D、自动导入与后处理
- **Agent 模式**
  - `Native Tool Use`：标准工具调用协议
  - `Structured XML`：文本+XML 解析工具调用
- **无工具调用自动回退**：推荐开启

### 权限设置
- **AI 权限级别**：`high / balanced / conservative`
- **高风险工具执行前确认**
- **允许破坏性工具 / 文件写入 / 网络与 Meshy 工具**

### UI 设置
- **阅读模式（大字号）**
- **阅读缩放**
- **主题预设**（System / Catppuccin Latte/Frappe/Macchiato/Mocha）

### Meshy 设置
- **Meshy API Key**（[meshy.ai](https://www.meshy.ai/settings/api)）
- **Meshy 模型版本**

## 使用方法

### AI 对话
1. 在 3D 视图右侧 `Agent` 面板打开聊天
2. 在聊天框顶部选择通道：`Agent` 或 `Meshy`
3. 输入任务（例如创建材质、调整场景、渲染，或 Meshy 生成）
3. 观察状态区：
   - 工具执行状态
   - 当前对话通道（Agent / Meshy）
   - 伪调用兜底命中次数（模型口胡时的自动恢复）

### 双通道边界
- `Agent` 通道：只暴露 MCP 工具，不暴露 `meshy_*` 工具
- `Meshy` 通道：不走 LLM，不触发 `NO_TOOLCALL/WRONG_TOOLSET` 判定
- `Meshy` 通道仅接受文生/图生请求；材质/场景编辑请切换到 `Agent`

### 示例指令
- `给当前选中物体创建真实感水材质并配置日光反射`
- `先检查场景，再把世界环境调成白天户外风格`
- `用 Cycles 渲染，分辨率 1920x1080，128 采样`

### 水面反射推荐流程
- 先调用 `scene_setup_daylight_water`
- 再对水材质做细调（IOR/Transmission/Roughness/法线）

## 故障排查

- `Meshy` 通道提示“仅支持文生/图生”：请求属于 MCP 编辑任务，请切到 `Agent`
- 出现 `[NO_TOOLCALL]`：仅在 `Agent` 通道可能出现，建议切换 Agent 模式或模型后重试
- 出现 `[WRONG_TOOLSET]`：仅在 `Agent` 通道可能出现，表示模型漂移到错误工具环境
- 看到“中间总结”但未结束：这是继续执行阶段，等待状态变为完成或点击“中止”
- 若执行到一半停住：优先检查权限确认弹窗是否在等待你“允许一次/拒绝”

## 系统要求

- Blender 4.0+ / 5.0+
- Python 3.10+（Blender 内置）

## 许可证

MIT License
