---
name: yudao-pilot-mcp
description: >
  当用户在芋道、yudao、ruoyi-vue-pro 或若依生态项目中表达“根据数据库表生成代码”“按表生成代码”
  “根据表结构生成前后端”“为某张表生成 CRUD / 管理后台 / 接口 / 页面 / 菜单 / 字典 / SQL”等意图时使用，
  并通过当前 Yudao Pilot MCP 完成表结构检查、代码生成上下文推导、后端与前端代码生成、菜单 SQL、字典 SQL、
  H2 测试 SQL 生成和按配置安全写入。也用于项目识别、.yudao-pilot 配置初始化与校验、数据库配置解析。
---

# Yudao Pilot MCP

这是 Yudao Pilot MCP 的操作型 Skill，用于指导 AI 在芋道 / ruoyi-vue-pro 项目中稳定完成项目识别、配置读取、表结构解析、代码生成、SQL 生成和安全写入。

核心原则：

- 以 `./.yudao-pilot/config.yaml` 为唯一配置事实来源，不绕过配置猜路径。
- 配置代表用户意图，不能为了“安全”擅自改配置。
- 只要用户有“根据表生成代码 / 按表生成 / 表结构生成 CRUD / 表生成前后端”的意图，默认使用当前 skill 调用 Yudao Pilot MCP。
- 只要用户调用 yudao-pilot 做“表生成/代码生成”，默认就按当前配置执行完整生成链路，而不是擅自缩减成“只生成部分代码”。
- 先自己推断可推断的问题，例如目标模块、父菜单、后端 jar 子模块、前端类型。
- 普通代码文件默认不能覆盖已有文件；合并型文件按合并逻辑修改已有文件。
- 菜单/字典是否真实落库只看配置，不看 AI 的临时判断。
- 代码生成必须先由真实数据库识别到目标表结构；本地 SQL 只能用于排查，不能单独放行生成。
- 默认表生成直接写入项目；只有用户明确要求“先预览”时，才调用预览，预览会写入 `.yudao-pilot/previews/` 临时目录。

## 触发意图识别

用户没有显式说“Yudao Pilot MCP”也应触发本 skill，只要同时满足：

- 当前任务位于或指向芋道、yudao、ruoyi-vue-pro、若依生态项目。
- 用户想从数据库表、表名、表结构、DDL、MySQL 表、已有业务表生成代码或 SQL。

这些表达都按“根据表生成代码”处理：

- “根据 `xxx` 表生成代码”
- “按 `xxx` 表生成 CRUD”
- “用这张表生成前后端”
- “根据表结构生成接口和页面”
- “为这张表生成管理后台 / 菜单 / 字典”
- “把这个 DDL 生成到芋道项目”
- “生成某张表的后端、Vue、Vben、uni-app 代码”

触发后不要改用普通代码生成方式；必须先调用当前 Yudao Pilot MCP 的 `load_workspace_config` 和 `validate_workspace_projects`，再进入表生成工作流。

## 渐进式披露模式

先用 MCP 返回的摘要判断下一步，只在需要时读取更深的数据。

### 查看项目与配置

优先调用：

```text
load_workspace_config
validate_workspace_projects
```

如果需要识别单个目录：

```text
inspect_project_path(project_path)
```

如果缺少配置，`load_workspace_config` 会尝试安全初始化，并返回 `config_initialized`。此时必须暂停，向用户说明已创建的配置和识别到的后端/前端路径。

### 查看生成上下文

生成代码前必须调用：

```text
inspect_codegen_context(table_name)
```

关注这些字段：

- `resolved_from_config`：表名到模块、业务名、实体名的解析结果。
- `backend_project.codegen_target`：后端真实落点，尤其是聚合模块下的 jar 子模块。
- `generated_file_plan`：后端和前端生成文件清单。
- `menu_context`：父菜单候选和菜单 SQL 来源。
- `codegen_sql`：`apply_to_database`、`menu_mode`、`dict_mode`。
- `table_schema.columns`：字段、主键、字典、前端控件类型等信息。

### 查看表结构

表结构不清楚时调用：

```text
inspect_table_schema(table_name)
```

表结构解析规则：

- 如果能从项目本地配置或工作区配置解析出数据库连接，优先以真实数据库为准。
- 继续生成前，必须由真实数据库识别到目标表结构。
- 本地 SQL 只用于排查和辅助理解，不再作为代码生成的放行来源。
- 如果真实数据库里目标表不存在，必须停止；不要生成代码。
- 不要把项目基准 `ruoyi-vue-pro.sql` 当作“新表必须存在”的依据；新表 DDL 本来就可能不在里面。
- 如果没有可用数据库连接，也没有目标表自己的 SQL，再停止并提示用户补充信息。

## 工具列表

| 工具 | 用途 |
| --- | --- |
| `load_workspace_config` | 加载 `.yudao-pilot/config.yaml`，缺失时安全初始化 |
| `init_workspace_config` | 主动初始化工作区配置 |
| `inspect_project_path` | 识别指定目录是否为受支持的后端或前端项目 |
| `validate_workspace_projects` | 校验配置里的项目路径和真实项目指纹是否匹配 |
| `resolve_database_config` | 按配置和后端本地配置解析数据库连接 |
| `infer_codegen_plan` | 根据表名推导模块、业务名、实体名和目标项目 |
| `inspect_codegen_context` | 构建完整代码生成上下文 |
| `inspect_table_schema` | 解析目标表字段 |
| `generate_codegen_scaffold` | 生成后端和前端代码骨架；默认写入，明确预览时写入临时目录 |
| `write_generated_files` | 写入外部生成的文件，走 MCP 路由和安全规则 |
| `write_mysql_migration` | 写入 MySQL 迁移文件 |
| `generate_codegen_sql` | 生成菜单 SQL、字典 SQL、H2 SQL，并按配置决定是否落库 |
| `compare_codegen_reference_projects` | 对比参考项目代码生成实现 |

## 典型工作流

### 默认表生成

当用户说“生成表代码”“按表生成”“调用 yudao-pilot 生成某张表”，默认理解为：

- 按当前 `.yudao-pilot/config.yaml` 执行完整生成链路
- 同时考虑代码、菜单 SQL、字典 SQL、H2 SQL
- 是否写文件、是否写库，全部按配置和工具参数决定
- `generate_codegen_scaffold(write_files=true)` 会一并生成并写入菜单/字典 MySQL 迁移和 H2 测试 SQL，并按配置决定是否真实落库

推荐顺序：

```text
load_workspace_config
validate_workspace_projects
resolve_database_config
inspect_codegen_context(table_name)
generate_codegen_scaffold(table_name, write_files=true)
```

如果只需要单独处理 SQL，可调用 `generate_codegen_sql(table_name, write_files=true)`。默认表生成不需要在 `generate_codegen_scaffold(write_files=true)` 之后再重复调用 SQL 工具。

如果 SQL 生成链路依配置允许落库，就接受这就是配置要求，不要擅自跳过。

同一张表的菜单/字典迁移如果逻辑文件已存在（例如 `*_add_xxx_menus.sql`），不要重复生成第二份；应复用已有逻辑迁移文件，必要时仅在用户允许覆盖时更新它。

### 预览模式

只有用户明确说“先预览”“只看一下”“不要先写入项目代码”时，才调用：

```text
generate_codegen_scaffold(table_name, write_files=false)
```

预览不是纯内存返回。MCP 会把文件镜像写入 `.yudao-pilot/previews/<table>-<timestamp>/`，路径按 `backend|frontend/<target_type>/...` 保留真实相对结构，便于检查 diff，但不会影响后端或前端项目现有代码。

### 仅代码生成

只有在用户明确表达以下意思时，才缩窄为“只生成代码，不跑 SQL 工具”：

- “只要前后端代码”
- “不要菜单 / 不要字典 / 不要 SQL”
- “不要落库”
- “这次先别生成 SQL”

此时才使用：

```text
load_workspace_config
validate_workspace_projects
resolve_database_config
inspect_codegen_context(table_name)
generate_codegen_scaffold(table_name, write_files=true)
```

如果目标文件已存在，MCP 会返回 `should_stop=true` 和 `next_action_prompt`。必须把覆盖问题交给用户，用户确认后才用 `overwrite=true` 重试。

### SQL、菜单、字典生成

当用户明确提到菜单、字典、迁移、H2、落库，或者默认表生成链路需要执行这些内容时，进入这条流程。

```text
inspect_codegen_context(table_name)
generate_codegen_sql(table_name, parent_menu_id=..., write_files=true|false)
```

注意：

- `generate_codegen_sql(write_files=false)` 只表示不写 SQL 文件。
- `write_files=false` 不是数据库 dry-run。
- 如果 `codegen.apply_to_database=true` 且对应 SQL mode 为 `auto`，SQL 工具可能按设计写入真实数据库。
- 如果用户只要 SQL 文件但当前配置允许落库，必须让用户明确选择：改配置、改 SQL mode，或接受按配置落库。不能由 AI 静默修改配置。

### 外部生成文件写入

当 AI 在 MCP 外部生成了文件内容，使用：

```text
write_generated_files(files)
```

每个文件必须带：

- `target_kind`
- `target_type`
- `relative_path`
- `content`
- `overwrite`，默认应为 `false`

## 硬性规则

### 配置不可被 AI 擅自改写

不要为了规避风险自动修改这些配置：

- `codegen.apply_to_database`
- `codegen.menu_sql_mode`
- `codegen.dict_sql_mode`
- `codegen.routing`
- `manual_rules`

如果配置不符合当前用户目标，先说明冲突，并请求用户明确选择。不要把 `apply_to_database: true` 自动改成 `false`。

不要把“生成表代码”擅自解释成“只跑 scaffold、不跑 SQL”。默认应按配置完整执行；只有用户明确排除 SQL / 落库时，才缩窄范围。

### 数据库落库规则

菜单/字典真实落库必须同时满足：

- `codegen.apply_to_database=true`
- 对应 SQL mode 为 `auto`
- 生成计划判断存在需要创建或更新的数据

`migration_only` 永远只生成或写入迁移文件，不写真实数据库，即使 `apply_to_database=true`。

`disabled` 不生成对应 SQL，也不会落库。

### 文件覆盖规则

普通生成代码文件是“新建型文件”：

- 默认 `overwrite=false`
- 如果目标文件已存在，必须暂停并询问用户是否覆盖
- 用户确认覆盖后，才用 `overwrite=true` 重试

合并型文件是“修改型文件”，不要求目标文件必须不存在：

- 前端 `src/utils/dict.ts` 字典常量
- 后端 `ErrorCodeConstants.java` 错误码常量
- 后续明确由 MCP 合并器处理的类似文件

这些文件按 MCP 合并规则更新已有内容，不要按普通文件覆盖流程处理。

### DO 主键规则

生成 `*DO.java` 时，主键字段必须带 MyBatis-Plus `@TableId`。

典型输出：

```java
@Schema(description = "编号")
@TableId
private Long id;
```

生成后检查：

- `import com.baomidou.mybatisplus.annotation.TableId;` 存在。
- 主键字段有 `@TableId`。
- 非主键字段不能误加 `@TableId`。
- `PageReqVO`、`RespVO`、`SaveReqVO` 等 VO 类不能出现 `@TableId`，否则可能导致编译问题。

### 父菜单推断规则

父菜单无法立即确定时，先推断，不要直接问用户。

推断顺序：

1. 查看 `inspect_codegen_context` 返回的 `menu_context.parent_menu_candidates`。
2. 搜索已有 `system_menu` SQL。
3. 按模块名、菜单名、路由 path、component、permission 前缀匹配。
4. 如果有合理置信度，传 `parent_menu_id` 或 `parent_menu_name` 调用 SQL 工具。
5. 如果没有合理父菜单，继续调用 MCP；MCP 会按业务名/表注释自动生成模块根菜单。
6. 根菜单使用模块级业务名，不直接抄整张表注释；例如 `travel` 应命名为“旅游管理”。
7. 业务菜单优先翻译业务段；例如 `sim` 应命名为“手机卡”，`travel_sim_sku` 应生成“手机卡 SKU管理”。
8. 只有用户明确要求复用某个已有父菜单、但多个候选都合理且无法区分时，才问用户。

### 后端模块规则

遇到 Maven `packaging=pom` 聚合模块时，不把 Java 代码写到聚合模块根目录。

必须使用 MCP 推导出的目标：

- `backend_project.codegen_target.module_dir_name`
- `backend_project.codegen_target.package_module_name`

如果用户指定嵌套模块，例如“模块 A -> B -> 新建模块”，传：

- `module_name`：逻辑模块或根菜单模块，例如 `travel`
- `backend_module_dir`：目标 Maven 模块路径，例如 `travel/sim-spu`
- `backend_package_module`：Java package 模块段，例如 `simspu`

写入前检查 `generated_file_plan` 是否包含目标模块的 `pom.xml`。

## 常见处理方式

### 只要代码，不要 SQL

这是显式缩窄场景，不是默认场景。

调用 `generate_codegen_scaffold`，跳过 `generate_codegen_sql`。

不要为了“预览安全”调用 SQL 工具。

### 只要 SQL 文件，不要落库

如果配置当前允许落库，不要擅自改配置。

应该向用户说明：

- 当前配置会让 SQL 工具可能写库。
- 若只要 SQL 文件，需要用户确认调整配置或 SQL mode。

### 用户说“生成表代码”

默认按完整生成链路理解，不要自动脑补成“只生成 Java/Vue 文件”。

执行前先看两点：

- 用户有没有明确排除 SQL、菜单、字典、落库
- 当前配置是否要求 SQL 生成或真实落库

如果用户没有明确排除，就按配置执行。

### 目标文件已存在

把 MCP 的 `next_action_prompt` 原样传达给用户。

不要自行覆盖，不要静默跳过。

### 表结构未解析

先判断是否有数据库连接；有则优先查真实数据库。

真实数据库没有目标表时，再看“目标表自己的迁移 SQL”能否解析字段。

不要因为基准 `ruoyi-vue-pro.sql` 里没有新表就阻塞生成。

如果数据库和目标表 SQL 都不可用，再让用户补充 SQL 或数据库配置。

### 目标路径看起来不对

暂停写入，检查：

- `resolved_from_config`
- `backend_project.codegen_target`
- `generated_file_plan`
- `projects.backend.path`
- `projects.frontend`

不要凭目录名或 Java package 猜真实落点。

## 项目识别规则

Yudao Pilot 通过文件指纹识别项目，不依赖目录名、根项目名、Maven `groupId`、Java base package。

后端识别依据包括：

- `pom.xml`
- `modules`
- `yudao-dependencies`
- `yudao-framework`
- `yudao-server` 或 `*-server`
- `yudao-module-*`
- `yudao-spring-boot-starter-*`
- Spring Boot 2 / 3、Java 8 / 17、Cloud 依赖差异

前端识别依据包括：

- `package.json`
- `element-plus`
- `@vben/*`
- `@dcloudio/uni-app`
- `vite`
- `pinia`
- `vue-router`
- monorepo apps，例如 `apps/web-antd`、`apps/web-ele`

## 前端类型映射

| 代码生成类型 | 前端项目 |
| --- | --- |
| `VUE3_ELEMENT_PLUS` | `yudao-ui-admin-vue3` |
| `VUE3_VBEN5_ANTD_SCHEMA` | `yudao-ui-admin-vben` |
| `VUE3_VBEN5_ANTD_GENERAL` | `yudao-ui-admin-vben` |
| `VUE3_VBEN5_EP_SCHEMA` | `yudao-ui-admin-vben` |
| `VUE3_VBEN5_EP_GENERAL` | `yudao-ui-admin-vben` |
| `VUE3_ADMIN_UNIAPP_WOT` | `yudao-ui-admin-uniapp` |

同一个 `yudao-ui-admin-vben` 路径可以配置多个不同前端类型。生成时按前端类型分别产出到对应子应用。

## MCP Server 配置示例

开发环境：

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/yudao-pilot-mcp",
        "run",
        "yudao-pilot"
      ]
    }
  }
}
```

安装后环境：

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "yudao-pilot",
      "args": []
    }
  }
}
```
