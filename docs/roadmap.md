# Yudao Pilot 路线图

## 路线图策略

路线图从最小但真正有价值的流程开始：识别工作区、理解配置、解析数据库信息、把生成结果路由到正确位置。

后续能力都应该建立在这条主线之上。

## 第一阶段：工作区 MVP

目标：让 MCP 服务能够理解一个 yudao-pilot 工作区。

交付内容：

- 基于 stdio 的 MCP 服务
- 加载并校验 `./.yudao-pilot/config.yaml`
- 配置缺失时在安全工作区内初始化配置，并在不可信目录返回结构化停止响应
- 校验 1 个后端项目和多个不重复前端类型
- 对不支持的项目结构返回结构化错误

成功标准：

- AI 应用进入一个目录后，能够立即知道它是不是一个有效的 Yudao Pilot 工作区
- 只有在配置缺失或配置错误时，用户才需要补充信息

## 第二阶段：数据库解析

目标：让后端本地数据库配置的获取变得稳定、可预测。

交付内容：

- 支持 `database.mode = manual | auto`
- 根据 `projects.backend.config_profile` 解析后端本地配置
- 当工作区配置未填写数据库连接时，从后端本地配置中自动补齐
- 支持把解析出的结果回填到工作区配置

成功标准：

- AI 应用在需要数据库上下文时，不必反复向用户询问连接信息

## 第三阶段：生成路由

目标：把表名稳定地转换成生成规划。

交付内容：

- 基于 `module`、`table_prefixes`、`table_rules` 的手动路由
- 精确表规则匹配
- 最长前缀优先的兜底匹配
- 返回结构化生成规划，告诉 AI 应用后端和前端分别应该生成什么

成功标准：

- 给定一张表名后，MCP 服务能够无歧义地给出模块、业务名、实体名和目标项目

## 第四阶段：代码落盘

目标：让 AI 应用可以安全地把生成结果写回项目。

交付内容：

- 面向生成结果的文件写入接口
- 严格的目标路径校验
- 明确的覆盖策略
- 针对后端和前端的结构化落盘结果

成功标准：

- AI 应用可以在外部完成代码生成，再依赖 Yudao Pilot 完成准确落盘

## 第五阶段：分发与生态接入

目标：降低安装和接入门槛。

交付内容：

- `pyproject.toml` 打包配置
- `yudao-pilot` 这样的 CLI 入口
- 发布到 PyPI
- 提供 Cursor、VS Code、Trae 等编辑器的接入文档

成功标准：

- 开发者可以通过全局安装快速接入 Yudao Pilot，并连接到 AI 应用中使用

## 早期版本明确不做的事情

这些能力不进入第一版主线：

- 数据库副本和沙箱管理
- DDL / DML 同步与合并
- 自动热重启修复闭环
- 多环境发布编排

这些能力可以等基础工作区模型验证成功后再评估是否扩展。

## 里程碑视图

近期：

- 完成配置规范
- 搭建 MCP 服务骨架
- 实现工作区校验

中期：

- 实现数据库解析
- 实现生成规划
- 实现文件落盘

后期：

- 完成打包与发布
- 补齐编辑器集成文档
- 评估更高级的商业化工作流能力

---

# Roadmap

## Strategy

The roadmap starts with the smallest workflow that is still valuable: recognize the workspace, load configuration, resolve database context, infer generation targets, and write results safely.

## Phase 1: Workspace MVP

Goal: make the MCP service understand a yudao-pilot workspace.

Deliverables:

- stdio-based MCP server
- `.yudao-pilot/config.yaml` loading and validation
- safe config initialization when the workspace can be trusted
- one backend project and multiple unique frontend targets
- structured errors for unsupported or unclear project structures

Success criteria:

- An AI client can quickly know whether the current directory is a valid Yudao Pilot workspace
- Users only need to provide information when configuration is missing, invalid, or unsafe to infer

## Phase 2: Database Resolution

Goal: make backend local database configuration stable and predictable.

Deliverables:

- `database.mode = manual | auto`
- backend local config resolution based on `projects.backend.config_profile`
- fallback from empty workspace config fields to backend local config

Success criteria:

- AI clients do not need to repeatedly ask users for database connection details

## Phase 3: Generation Routing

Goal: turn a table name into a deterministic generation plan.

Deliverables:

- manual routing based on `module`, `table_prefixes`, and `table_rules`
- exact table matching
- longest-prefix fallback matching
- structured plans for backend and frontend targets

Success criteria:

- Given a table name, MCP can return module, business name, entity name, and target projects without ambiguity

## Phase 4: Safe Writing

Goal: let AI clients write generated results safely.

Deliverables:

- generated-file write API
- strict target path validation
- explicit overwrite policy
- structured write results

Success criteria:

- AI clients can generate code externally and rely on Yudao Pilot for accurate placement

## Phase 5: Distribution and Integrations

Goal: lower adoption cost.

Deliverables:

- package metadata
- `yudao-pilot` command
- distribution channel
- Cursor, VS Code, Trae, and other MCP client docs

Success criteria:

- Developers can install Yudao Pilot globally and connect it to AI clients quickly
