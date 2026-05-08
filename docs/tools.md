# MCP Tools and Workflow / MCP 工具与工作流

[中文](#中文) | [English](#english)

## 中文

### 推荐工作流

首次进入一个 yudao 工作区：

```text
load_workspace_config
validate_workspace_projects
```

默认直接写入项目：

```text
inspect_codegen_context
inspect_table_schema
generate_codegen_scaffold(write_files=true)
```

只有用户明确要求“先预览”时，才调用：

```text
generate_codegen_scaffold(write_files=false)
```

此时 MCP 会把预览产物写入 `.yudao-pilot/previews/` 下的临时目录，保留 `generated_files` 内容，同时不修改真实项目代码。

菜单/字典是否写入真实数据库只按配置决定，不按“是否先预览”强制绑定：

- 默认 `codegen.apply_to_database=false`，不写库。
- 只有 `codegen.apply_to_database=true` 且对应 `menu_sql_mode` / `dict_sql_mode` 为 `auto` 时，才会写入数据库。
- `migration_only` 只生成或写入迁移文件，不写真实数据库。

### 停止条件

如果 MCP 返回 `should_stop=true`，AI 客户端应暂停当前生成流程，并按 `next_action_prompt` 询问用户或修复配置。

常见停止码：

- `workspace_root_required`: 无法确认真实项目工作区
- `config_initialized`: 已生成配置，需要用户确认
- `config_invalid`: 配置校验失败
- `workspace_project_validation_failed`: 配置项目与实际项目不匹配
- `table_schema_unresolved`: 表结构无法解析
- `database_table_missing`: 已连接真实数据库，但未识别到目标表
- `database_config_unresolved`: 数据库连接无法解析

### 工具清单

`load_workspace_config`

- 加载 `.yudao-pilot/config.yaml`
- 缺失时尝试安全初始化
- 初始化后要求 AI 停止并让用户确认

`init_workspace_config`

- 主动初始化配置
- 不会在文件系统根目录或无项目指纹目录中写配置

`inspect_project_path`

- 根据 `pom.xml`、`package.json`、依赖和版本识别项目类型
- 不依赖目录名、Maven `groupId` 或 Java 基础包名

`validate_workspace_projects`

- 校验配置中的后端和前端路径是否存在
- 校验配置类型是否与项目指纹匹配

`resolve_database_config`

- 按配置解析数据库连接
- `auto` 模式下会从后端本地配置补齐空字段

`infer_codegen_plan`

- 根据表名和配置规则推导模块、业务名、实体名和目标项目

`inspect_codegen_context`

- 构建代码生成上下文
- 包含模块、权限标识、前端模板、菜单候选、生成文件计划和 SQL 路径建议

`inspect_table_schema`

- 优先从真实数据库解析字段
- 必须从真实数据库识别到目标表后才能继续生成
- 本地 SQL 不再作为代码生成的放行来源

`generate_codegen_scaffold`

- 生成后端和前端骨架代码
- 默认写入工作区
- `write_files=false` 仅用于用户明确要求预览时；预览结果写入 `.yudao-pilot/previews/` 临时目录
- `write_files=true` 时一并写入菜单/字典 MySQL 迁移和 H2 测试 SQL，并按配置决定是否落库

`generate_codegen_sql`

- 生成菜单 SQL、字典 SQL、H2 建表和清理 SQL
- 可按配置写入迁移文件或真实数据库

`write_generated_files`

- 将 AI 外部生成的文件按 MCP 路由结果安全写入

`write_mysql_migration`

- 将新的 MySQL 迁移 SQL 写入 `sql/mysql/migrations/`

`compare_codegen_reference_projects`

- 对比 `ruoyi-vue-pro` 与 `ruoyi-vue-pro-jdk17` 的代码生成核心实现差异

## English

### Recommended Workflow

When entering a yudao workspace for the first time:

```text
load_workspace_config
validate_workspace_projects
```

By default, write directly to the project:

```text
inspect_codegen_context
inspect_table_schema
generate_codegen_scaffold(write_files=true)
```

Only call preview when the user explicitly asks to preview first:

```text
generate_codegen_scaffold(write_files=false)
```

In preview mode, MCP writes artifacts under `.yudao-pilot/previews/`, keeps `generated_files` in the response, and does not modify real project code.

Writes to a real database for menu/dictionary data are config-driven rather than forced by a preview step:

- The default `codegen.apply_to_database=false` does not write to the DB.
- DB writes only happen when `codegen.apply_to_database=true` and the matching `menu_sql_mode` / `dict_sql_mode` is `auto`.
- `migration_only` only generates or writes migration files and never writes to the real DB.

### Stop Conditions

When MCP returns `should_stop=true`, the AI client should pause the current generation flow and follow `next_action_prompt`.

Common stop codes:

- `workspace_root_required`: The real project workspace is unknown
- `config_initialized`: Config was created and needs user confirmation
- `config_invalid`: Config validation failed
- `workspace_project_validation_failed`: Configured projects do not match detected projects
- `table_schema_unresolved`: Table schema cannot be resolved
- `database_table_missing`: The real database was reached, but the target table was not found
- `database_config_unresolved`: Database connection cannot be resolved

### Tool List

`load_workspace_config`

- Loads `.yudao-pilot/config.yaml`
- Safely initializes missing config when possible
- Requires the AI to stop and ask for confirmation after initialization

`init_workspace_config`

- Explicitly initializes config
- Refuses filesystem roots and directories without supported project fingerprints

`inspect_project_path`

- Detects project type from `pom.xml`, `package.json`, dependencies, and versions
- Does not rely on directory names, Maven `groupId`, or Java base package names

`validate_workspace_projects`

- Validates configured backend and frontend paths
- Ensures configured types match detected fingerprints

`resolve_database_config`

- Resolves database connection from workspace config
- In `auto` mode, fills missing fields from backend local config

`infer_codegen_plan`

- Infers module, business name, entity name, and targets from table name and config rules

`inspect_codegen_context`

- Builds code-generation context
- Includes module info, permissions, frontend templates, menu candidates, file plans, and SQL paths

`inspect_table_schema`

- Prefers the real database for field metadata
- Requires the target table to be recognized in the real database before generation can continue
- Local SQL no longer acts as the gate for code generation

`generate_codegen_scaffold`

- Generates backend and frontend scaffold files
- Writes to the project by default
- `write_files=false` is only for explicit preview requests; preview files are written under `.yudao-pilot/previews/`

`generate_codegen_sql`

- Generates menu SQL, dictionary SQL, H2 create-table SQL, and H2 clean SQL
- Can write migration files or apply database changes when enabled

`write_generated_files`

- Safely writes externally generated AI files according to MCP routing

`write_mysql_migration`

- Writes new MySQL migration SQL into `sql/mysql/migrations/`

`compare_codegen_reference_projects`

- Compares code-generation internals between `ruoyi-vue-pro` and `ruoyi-vue-pro-jdk17`
