# Overview / 项目概览

[中文](#中文) | [English](#english)

## 中文

Yudao Pilot MCP 是一个专门服务 yudao / ruoyi-vue-pro 项目的 MCP 领域适配层。它不替代 AI 编码工具，而是为 AI 工具补上确定性的项目理解能力。

### 为什么需要它

通用 AI 编码工具在 yudao 项目里通常会遇到这些问题：

- 不知道当前目录是不是合法的 yudao 工作区
- 不知道后端、Vue3 管理后台、Vben、Uniapp 分别在哪里
- 不知道一张业务表应该生成到哪个模块、哪个前端项目
- 不知道数据库连接应该从工作区配置读取，还是从后端本地配置解析
- 在目录不明确时，容易把配置或生成物写到错误位置

Yudao Pilot MCP 的目标是让 AI “能写代码”之前先“知道写到哪里”。

### 第一版范围

已支持：

- 基于 stdio 的 MCP 服务
- 使用 `.yudao-pilot/config.yaml` 作为工作区配置入口
- 识别并校验 1 个后端项目和多个前端项目
- 基于 `pom.xml`、`package.json`、依赖和版本的项目指纹识别
- 解析后端本地 `application*.yaml` 中的数据库连接
- 推导表名对应的模块、业务名、实体名和生成目标
- 生成菜单 SQL、字典 SQL、H2 测试 SQL 和前后端骨架代码
- 在工作区不明确时返回 `workspace_root_required`，阻止把配置写到系统根目录

暂不包含：

- 数据库副本或沙箱
- DDL / DML 自动同步与合并
- 自动部署流水线
- 报错后自动修复重试的完整闭环

### 职责边界

Yudao Pilot MCP 负责：

- 理解当前工作区
- 校验项目路径和项目类型
- 解析数据库连接信息
- 计算代码生成目标
- 安全写入 AI 生成的文件和 SQL

AI 应用负责：

- 与用户交互
- 明确业务需求
- 根据 MCP 返回的上下文生成代码内容
- 在需要人工确认时暂停并询问用户

## English

Yudao Pilot MCP is a domain-specific MCP adapter for yudao / ruoyi-vue-pro projects. It does not replace AI coding tools. It gives them deterministic workspace awareness before they generate or write code.

### Why It Exists

Generic AI coding tools often struggle with yudao projects because they do not know:

- Whether the current directory is a valid yudao workspace
- Where the backend, Vue3 admin, Vben apps, and Uniapp projects live
- Which module and frontend target a business table belongs to
- Whether database credentials should come from workspace config or backend local config
- Whether it is safe to initialize config in the current directory

Yudao Pilot MCP helps AI tools answer “where should this code go?” before they write anything.

### Version 1 Scope

Supported today:

- stdio-based MCP server
- `.yudao-pilot/config.yaml` as the workspace entry point
- Validation for one backend project and multiple frontend targets
- Project detection from `pom.xml`, `package.json`, dependencies, and versions
- Database resolution from backend `application*.yaml`
- Code-generation routing from table name to module, business name, entity name, and targets
- Menu SQL, dictionary SQL, H2 test SQL, and backend/frontend scaffold generation
- `workspace_root_required` safety response when the workspace is unknown

Out of scope for now:

- Database clones or sandboxes
- Automatic DDL / DML synchronization
- Deployment pipelines
- Full self-healing retry loops

### Responsibility Boundary

Yudao Pilot MCP handles:

- Workspace understanding
- Project path and type validation
- Database connection resolution
- Code-generation target planning
- Safe file and SQL writing

The AI client handles:

- User conversation
- Business requirement clarification
- Code content generation
- Asking the user when MCP returns a stop/confirmation response
