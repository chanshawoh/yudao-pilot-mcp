# SQL, Menu, and Dictionary Generation / SQL、菜单与字典生成

[中文](#中文) | [English](#english)

## 中文

Yudao Pilot MCP 可以为代码生成流程补齐 SQL 产物：

- MySQL 菜单迁移 SQL
- 根据字段注释解析出的字典 SQL
- 后端模块 H2 `create_tables.sql`
- 后端模块 H2 `clean.sql`
- 可选的真实数据库菜单和字典写入

默认表生成路径中，`generate_codegen_scaffold(write_files=true)` 会一并处理这些 SQL 产物：写入 MySQL 菜单/字典迁移、合并 H2 `create_tables.sql` 和 `clean.sql`，并在配置允许时执行真实数据库写入。单独调用 `generate_codegen_sql` 适用于只补 SQL 或重跑 SQL 的场景。

当无法从已有 `system_menu` 判断父菜单时，MCP 不会要求 AI 停止等待用户；它会根据 `module_menu_name`、模块名、表注释、菜单名和业务名推断模块根菜单名称，生成幂等 SQL：已有则复用，不存在则自动创建。根菜单使用模块级业务名，例如 `travel` 为“旅游管理”；业务菜单优先翻译业务段，例如 `sim` 为“手机卡”，`travel_sim_sku` 生成“手机卡 SKU管理”。

### 配置开关

| 配置 | SQL 生成行为 | 数据库执行行为 |
| --- | --- | --- |
| `apply_to_database=false` | 仍生成菜单/字典迁移 SQL | 不写库 |
| `apply_to_database=true` | 不影响 SQL 生成 | 仅在对应 SQL mode 为 `auto` 时可写库，已存在则跳过 |
| `menu_sql_mode=disabled` | 不生成菜单 SQL 片段 | 无菜单 SQL 可写 |
| `dict_sql_mode=disabled` | 不生成字典 SQL 片段 | 无字典 SQL 可写 |
| `menu_sql_mode=auto` | 生成菜单 SQL | 是否写库取决于 `apply_to_database` |
| `dict_sql_mode=auto` | 生成字典 SQL | 是否写库取决于 `apply_to_database` |
| `menu_sql_mode=migration_only` | 生成菜单迁移 SQL | 不写库 |
| `dict_sql_mode=migration_only` | 生成字典迁移 SQL | 不写库 |

默认安全模式是 `apply_to_database=false`。如果工作区配置明确设置 `apply_to_database=true` 且对应 SQL mode 为 `auto`，MCP 会按配置直接写入真实数据库；未明确配置时只准备 SQL 产物。

### 常用参数

`generate_codegen_sql` 常用参数：

- `table_name`: 目标表名
- `menu_name`: 业务菜单中文名，例如 `商家用户`
- `module_menu_name`: 模块根菜单中文名，例如 `会员中心`
- `menu_icon`: 业务菜单图标，使用 Iconify 字符串
- `module_menu_icon`: 模块根菜单图标，使用 Iconify 字符串
- `write_files`: 是否真实写入 SQL 文件

### 菜单图标

菜单图标写入后端 `system_menu.icon` 字段，前端直接消费该字符串。

推荐使用 Iconify 格式：

- `ep:shop`
- `ep:avatar`
- `ep:menu`
- `lucide:user`
- `ant-design:message-filled`

优先级：

1. AI 显式传入图标
2. MCP 从已有菜单和业务关键词推断
3. MCP 使用模块默认图标

### 字典 SQL

当表字段注释能解析出枚举语义时，MCP 会生成：

- `system_dict_type`
- `system_dict_data`

字典 SQL 是幂等生成的，适合放入迁移文件。若 `dict_sql_mode=disabled`，迁移文件不包含字典片段。

### H2 测试 SQL

MCP 会定位目标后端模块，并幂等合并：

- `src/test/resources/sql/create_tables.sql`
- `src/test/resources/sql/clean.sql`

H2 测试 SQL 不受 `menu_sql_mode` 和 `dict_sql_mode` 影响。

## English

Yudao Pilot MCP can generate SQL artifacts for the code-generation flow:

- MySQL menu migration SQL
- Dictionary SQL parsed from field comments
- Backend module H2 `create_tables.sql`
- Backend module H2 `clean.sql`
- Optional menu and dictionary writes to a real database

In the default table-generation path, `generate_codegen_scaffold(write_files=true)` also handles these SQL artifacts: it writes the MySQL menu/dictionary migration, merges H2 `create_tables.sql` and `clean.sql`, and applies menu/dictionary data to the real database when the workspace config allows it. Use `generate_codegen_sql` directly when you only need to prepare or rerun SQL.

When an existing parent menu cannot be inferred from `system_menu`, the MCP should not stop and wait for the AI/user. It infers a root menu name from `module_menu_name`, module names, table comments, menu names, and business names, then emits idempotent SQL that reuses an existing menu or creates a new one. Root menus use module-level business names, for example `travel` becomes `旅游管理`; business menus translate business segments first, for example `sim` becomes `手机卡`, so `travel_sim_sku` becomes `手机卡 SKU管理`.

### Config Switches

| Config | SQL generation | Database execution |
| --- | --- | --- |
| `apply_to_database=false` | Still generates menu/dictionary migration SQL | Does not write to DB |
| `apply_to_database=true` | Does not affect SQL generation | May write to DB only when the matching SQL mode is `auto`; skips existing records |
| `menu_sql_mode=disabled` | Omits menu SQL | No menu SQL to apply |
| `dict_sql_mode=disabled` | Omits dictionary SQL | No dictionary SQL to apply |
| `menu_sql_mode=auto` | Generates menu SQL | DB write depends on `apply_to_database` |
| `dict_sql_mode=auto` | Generates dictionary SQL | DB write depends on `apply_to_database` |
| `menu_sql_mode=migration_only` | Generates menu migration SQL | Does not write to DB |
| `dict_sql_mode=migration_only` | Generates dictionary migration SQL | Does not write to DB |

The default safe mode is `apply_to_database=false`. If the workspace config explicitly sets `apply_to_database=true` and the matching SQL mode is `auto`, MCP writes directly to the real database; otherwise it only prepares SQL artifacts.

### Common Parameters

Common `generate_codegen_sql` parameters:

- `table_name`: Target table name
- `menu_name`: Business menu display name
- `module_menu_name`: Root module menu display name
- `menu_icon`: Business menu icon as an Iconify string
- `module_menu_icon`: Module menu icon as an Iconify string
- `write_files`: Whether SQL files should be written

### Menu Icons

Menu icons are written to the backend `system_menu.icon` field and consumed by the frontend.

Use Iconify strings such as:

- `ep:shop`
- `ep:avatar`
- `ep:menu`
- `lucide:user`
- `ant-design:message-filled`

Priority:

1. Explicit icon from the AI client
2. MCP inference from existing menus and business keywords
3. MCP module default icon

### Dictionary SQL

When field comments can be parsed as enum semantics, MCP generates:

- `system_dict_type`
- `system_dict_data`

Dictionary SQL is generated idempotently and is suitable for migration files. If `dict_sql_mode=disabled`, dictionary SQL is omitted.

### H2 Test SQL

MCP locates the target backend module and idempotently merges:

- `src/test/resources/sql/create_tables.sql`
- `src/test/resources/sql/clean.sql`

H2 test SQL is not affected by `menu_sql_mode` or `dict_sql_mode`.
