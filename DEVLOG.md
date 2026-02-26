# Blender Agent 开发日志 (DEVLOG)

## 项目概述
Blender AI 助手插件 — 在 Blender 内通过对话操作场景，支持材质编辑、卡通渲染、动画、3D生成等。

---

## v2.1 → v3.0 重构 (2026-02-26)

### 背景
原始 `agent_core.py` 中的 `BlenderAgent` 是单 Agent 架构，直接把所有 75 个工具传给 LLM。
虽然能工作，但存在以下问题：
- 每次请求传 75 个工具，token 消耗大
- 无法按领域筛选工具，LLM 容易产生幻觉
- 单一 system prompt 过长
- 不支持多 LLM Provider（只支持 Anthropic 格式）

### 第一次重构尝试（失败）
创建了 `agents/`, `llm/`, `tools/`, `parsers/`, `context/` 共 20+ 文件的多 Agent 系统。
**失败原因：**
1. `tools/` 包与 `tools.py` 文件命名冲突，Python 导入 `tools/` 包而非 `tools.py`
2. 将 `tools.py` 重命名为 `tool_definitions.py` 后，`_register_all_tools()` 的 `except ImportError: pass` 静默吞掉错误，导致工具注册表为空
3. `_safe_callback` 使用阻塞式 `_execute_in_main_thread`（等待30秒），而旧代码用 `bpy.app.timers.register`（非阻塞），导致死锁
4. 系统 prompt 太弱，没有强制 LLM 使用工具
5. 多层抽象（Registry → ToolDef → get_schemas → _convert_tools）中任何一环断裂都导致 LLM 收不到工具

### 第二次重构（成功 — 当前版本）
回归旧 `BlenderAgent` 的可靠模式，在此基础上加入多 Provider 支持和意图路由。

**新架构：`core/` 目录（4 个文件）**
```
core/
├── llm.py      # 统一 LLM 调用（Anthropic/OpenAI/中转，单类 UnifiedLLM）
├── agent.py    # 主 Agent（继承旧 BlenderAgent 的直接传工具模式）
├── router.py   # 意图路由（纯规则引擎，零 LLM 调用）
└── tools.py    # 工具注册 + 调度（单文件，延迟加载 tool_definitions.py）
```

**关键设计决策：**
- `core/tools.py` 用延迟导入 `from .. import tool_definitions`，失败时有内联工具兜底
- `core/agent.py` 的 `_fire_callback` 用 `bpy.app.timers.register`（非阻塞），和旧代码一致
- `core/agent.py` 的 `_execute_in_main_thread` 用 `queue.Queue` + `bpy.app.timers`（阻塞等结果），和旧代码一致
- 系统 prompt 完整保留旧的"铁律"规则
- 意图路由按关键词筛选工具子集（~15-30 个），减少 token 消耗
- `general` 意图只给常用工具（~30个），避免 payload 过大导致 API 500

**新增功能：**
- 多 LLM Provider 支持（Anthropic / OpenAI / 中转 API）
- 意图路由 → 工具子集筛选（减少 ~60% token）
- 文件系统工具（file_read/write/list/read_project）
- `mcp_tools/` 可扩展工具模块

---

## 文件清单

### 核心文件（新）
| 文件 | 行数 | 说明 |
|------|------|------|
| `core/llm.py` | ~400 | 统一 LLM 客户端，支持 Anthropic/OpenAI/中转 |
| `core/agent.py` | ~340 | 主 Agent，直接传工具给 LLM |
| `core/router.py` | ~90 | 意图路由，纯关键词规则 |
| `core/tools.py` | ~167 | 工具注册表 + 调度器 |
| `mcp_tools/filesystem.py` | ~92 | 文件系统工具 |

### 工具实现文件（保持不变）
| 文件 | 说明 |
|------|------|
| `tool_definitions.py` | 75 个工具定义 + execute_tool 调度器 |
| `shader_tools.py` | 着色器节点操作（23 个函数） |
| `scene_tools.py` | 场景操作（16 个函数） |
| `animation_tools.py` | 动画工具（6 个函数） |
| `toon_tools.py` | 卡通渲染（2 个函数） |
| `web_search.py` | 网络搜索（4 个函数） |
| `knowledge_base.py` | 知识库（2 个函数） |
| `meshy_api.py` | Meshy AI 3D 生成 |

### UI 和插件入口
| 文件 | 说明 |
|------|------|
| `__init__.py` | Blender 插件入口 + MCP Bridge Server |
| `chat_ui.py` | 侧边栏对话 UI + Agent 实例管理 |
| `config.py` | 配置 |

### 旧文件（保留备份，不再使用）
| 文件 | 说明 |
|------|------|
| `agent_core.py` | 旧 BlenderAgent（v2.1） |
| `agents/` | 旧多 Agent 系统（第一次重构） |
| `llm/` | 旧 LLM Provider 抽象 |
| `tools/` | 旧工具注册表 |
| `parsers/` | 旧解析器 |
| `context/` | 旧上下文管理 |

---

## 工具清单（75 个）

### 基础操作 (6)
list_objects, create_primitive, delete_object, transform_object, get_object_info, get_scene_info

### 材质 (6)
set_material, set_metallic_roughness, shader_create_material, shader_delete_material, shader_list_materials, shader_assign_material

### 着色器节点 (19)
shader_inspect_nodes, shader_add_node, shader_delete_node, shader_set_node_input, shader_set_node_property, shader_link_nodes, shader_unlink_nodes, shader_colorramp_add_stop, shader_colorramp_remove_stop, shader_colorramp_set_interpolation, shader_batch_add_nodes, shader_batch_link_nodes, shader_clear_nodes, shader_get_material_summary, shader_get_node_sockets, shader_list_available_nodes, shader_create_procedural_material, shader_preview_material, shader_configure_eevee

### 卡通渲染 (2)
shader_create_toon_material, shader_convert_to_toon

### 场景 (17)
scene_add_light, scene_modify_light, scene_add_camera, scene_set_active_camera, scene_add_modifier, scene_set_modifier_param, scene_remove_modifier, scene_manage_collection, scene_set_world, scene_duplicate_object, scene_parent_object, scene_set_visibility, scene_get_render_settings, scene_set_render_settings, scene_get_object_materials, scene_get_world_info, scene_list_all_materials

### 动画 (6)
anim_add_uv_scroll, anim_add_uv_rotate, anim_add_uv_scale, anim_add_value_driver, anim_add_keyframe, anim_remove_driver

### 渲染 (2)
setup_render, render_image

### 3D 生成 (2)
meshy_text_to_3d, meshy_image_to_3d

### 搜索 (6)
web_search, web_fetch, web_search_blender, web_analyze_reference, kb_search, kb_save

### 文件 (4)
file_read, file_write, file_list, file_read_project

### 元数据 (5)
get_action_log, get_todo_list, complete_todo, analyze_scene, execute_python(禁用)

---

## 后续可添加的工具
- `file_search` — 文件内容搜索（grep）
- `file_delete` — 删除文件
- `screenshot_viewport` — 截取视口截图
- `import_model` — 导入外部模型（FBX/OBJ/GLB）
- `export_model` — 导出模型
- `get_addon_list` — 列出已安装插件
- `set_object_constraint` — 设置物体约束
- `batch_transform` — 批量变换物体
- `create_node_group` — 创建节点组
- `apply_modifier` — 应用修改器

---

## v3.1 结构化 XML 输出解析 (2026-02-26)

### 背景
原始用户需求："让LLM只是生成文本，工具由外部解析器触发"。
v3.0 使用 API 原生 tool_use 传工具，虽然可靠但：
- 每次请求传完整 tool JSON schema，payload 大
- 不支持没有 tool_use 功能的 LLM / 中转 API
- LLM 需要理解 tool_use 协议，增加幻觉风险

### 实现
新增两个文件，与现有 Native 模式并行存在：

**`core/xml_parser.py`** (~230 行)
- 从 LLM 纯文本输出中提取 `<tool_call>` XML 标签
- 支持 `<param>` 标签格式和纯 JSON 内联格式
- 智能值解析（JSON 对象/数组、数字、布尔、字符串）
- `build_tool_catalog()` 将工具定义转为文本目录嵌入 system prompt
- `validate_tool_call()` 验证工具名和必填参数

**`core/structured_agent.py`** (~280 行)
- 与 BlenderAgent 接口一致（send_message, on_message, on_tool_call, on_error）
- 不通过 API tools 参数传工具，而是写进 system prompt
- LLM 生成文本 + XML 标签 → xml_parser 提取 → 执行 → 结果以文本追加
- MAX_TOOL_ROUNDS=5 防止无限循环
- 递归处理多轮工具调用

**`chat_ui.py` 修改**
- 新增 `agent_mode` 偏好设置（native / structured）
- `get_agent()` 根据模式创建 BlenderAgent 或 StructuredAgent
- 偏好 UI 显示模式选择和说明

### XML 格式
```xml
<tool_call name="create_primitive">
  <param name="primitive_type">cube</param>
  <param name="location">[0, 0, 1]</param>
</tool_call>
```

### 两种模式对比
| | Native Tool Use | Structured XML |
|---|---|---|
| 工具传递 | API tools 参数（JSON schema） | system prompt 文本目录 |
| LLM 输出 | tool_use 结构化块 | 纯文本 + XML 标签 |
| 解析 | API 自动解析 | xml_parser.py 正则提取 |
| Token 消耗 | 较高（完整 schema） | 较低（压缩文本目录） |
| 兼容性 | 需要 API 支持 tool_use | 任何 LLM 都可用 |
| 可靠性 | 高（API 保证格式） | 中（依赖 LLM 遵循 XML 格式） |

### 文件清单更新
| 文件 | 行数 | 说明 |
|------|------|------|
| `core/xml_parser.py` | ~230 | XML 工具调用解析器 |
| `core/structured_agent.py` | ~280 | 结构化输出 Agent |
