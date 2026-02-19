# Gohot Blender Agent

AI 驱动的 Blender 助手插件，支持对话式操作、Meshy AI 3D 生成、场景分析和渲染助手。

## 功能特性

- 🤖 **AI 对话助手** - 通过自然语言控制 Blender，创建物体、设置材质、执行代码
- 🎨 **Meshy AI 集成** - 文生3D、图生3D，自动导入模型和 PBR 贴图
- 👁️ **场景分析** - AI 可以"看到"你的场景，给出光照、构图、材质优化建议
- 🎬 **渲染助手** - 一句话设置渲染参数并输出图片
- 🔌 **MCP Bridge** - 支持外部 AI 客户端通过 MCP 协议控制 Blender

## 安装

1. 下载本仓库或 Release 中的 zip 文件
2. 在 Blender 中：`Edit > Preferences > Add-ons > Install`
3. 选择下载的文件夹或 zip 文件
4. 启用 "Gohot Blender Agent" 插件

## 配置

安装后在 `Edit > Preferences > Add-ons > Gohot Blender Agent` 中配置：

### Claude API（AI 对话）
- **API 地址**: Claude API 地址（官方或中转）
- **API Key**: 你的 API Key
- **模型**: 选择使用的模型

### Meshy AI（3D 生成）
- **Meshy API Key**: 从 [meshy.ai](https://www.meshy.ai/settings/api) 获取

## 使用方法

### AI 对话
1. 在 3D 视图侧边栏找到 "AI" 标签
2. 点击 "打开对话窗口"
3. 输入指令

### Meshy 3D 生成
- 文生3D: `帮我生成一个机器人 3D 模型`
- 图生3D: `用这张图片生成 3D 模型：https://example.com/image.png`

生成完成后，模型会自动导入场景，包含完整的 PBR 材质。

### 场景分析
- `帮我看看这个场景的光照怎么样`
- `分析一下当前构图有什么问题`

AI 会截取当前视口，分析后给出具体建议。

### 渲染助手
- `用 Cycles 渲染，分辨率 1920x1080，128 采样`
- `渲染当前画面`

## 系统要求

- Blender 4.0+ / 5.0+
- Python 3.10+（Blender 内置）

## 许可证

MIT License
