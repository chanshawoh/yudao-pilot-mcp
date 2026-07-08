# Configuration / 配置指南

[中文](#中文) | [English](#english)

## 中文

工作区配置文件固定为：

```text
.yudao-pilot/config.yaml
```

它是 Yudao Pilot MCP 的路由事实来源。AI 不应该绕过它猜路径。

### 安全初始化规则

如果配置文件不存在，MCP 会尝试在明确的工作区根目录下初始化配置。

以下情况不会写入配置文件，而是返回 `workspace_root_required`：

- MCP 服务进程工作目录是文件系统根目录
- 传入的 `workspace_root` 指向文件系统根目录
- 当前目录下没有识别到受支持的 yudao 后端或前端项目

AI 客户端收到该响应后，应先询问用户真实项目工作目录，再带上 `workspace_root` 重试。

### 示例配置

```yaml
version: 1

workspace:
  name: my-yudao-workspace

projects:
  backend:
    path: ../yudao-server
    type: ruoyi-vue-pro-jdk17
    config_profile: local

  frontend:
    - type: VUE3_ELEMENT_PLUS
      path: ../yudao-ui-admin-vue3
    - type: VUE3_VBEN5_ANTD_SCHEMA
      path: ../yudao-ui-admin-vben
    - type: VUE3_ADMIN_UNIAPP_WOT
      path: ../yudao-ui-admin-uniapp

database:
  mode: auto
  host: ""
  port: 3306
  database: ""
  username: ""
  password: ""

codegen:
  apply_to_database: false
  menu_sql_mode: auto
  dict_sql_mode: auto

  routing:
    mode: manual

  manual_rules:
    - module: member
      table_prefixes:
        - merchant_user
        - merchant
        - member
      table_rules:
        - table: member_user
          business: member_user
          entity: MemberUser
```

### 字段说明

`projects.backend`

- `path`: 后端项目路径，可为相对工作区路径或绝对路径
- `type`: 当前支持 `ruoyi-vue-pro`、`ruoyi-vue-pro-jdk17`、`yudao-cloud`
- `config_profile`: 读取后端本地配置时使用的环境名，例如 `local`

`projects.frontend`

- `type`: 前端模板类型
- `path`: 前端项目路径
- `type` 不能重复
- 同一个 Vben 项目路径可以配置多个不同模板类型

当前支持的前端类型：

- `VUE3_ELEMENT_PLUS`
- `VUE3_VBEN5_ANTD_SCHEMA`
- `VUE3_VBEN5_ANTD_GENERAL`
- `VUE3_VBEN5_EP_SCHEMA`
- `VUE3_VBEN5_EP_GENERAL`
- `VUE3_ADMIN_UNIAPP_WOT`

`database`

- `mode=manual`: 直接使用配置文件里的数据库连接
- `mode=auto`: 优先使用配置文件字段；空字段再从后端本地配置解析

`codegen`

- `apply_to_database`: 是否允许菜单/字典 SQL 写入真实数据库；默认 `false`，只生成 SQL 产物不落库
- `menu_sql_mode`: 菜单 SQL 模式，支持 `auto`、`migration_only`、`disabled`
- `dict_sql_mode`: 字典 SQL 模式，支持 `auto`、`migration_only`、`disabled`
- `auto`: 生成对应 SQL；当 `apply_to_database=true` 时允许写入数据库
- `migration_only`: 只生成迁移 SQL，不写数据库，即使 `apply_to_database=true`
- `disabled`: 不生成对应 SQL，也不会写数据库

`codegen.routing.mode`

- `manual`: 按 `manual_rules` 解析，适合稳定团队项目
- `ask`: MCP 返回候选位置，由 AI 询问用户确认
- `auto`: MCP 自动分析目标位置并返回生成计划

`manual_rules`

- 精确表规则 `table_rules[].table` 优先
- 前缀规则 `table_prefixes` 兜底
- 前缀匹配按最长优先，例如 `merchant_user` 优先于 `merchant`

### 校验规则

- 一个工作区只能配置一个后端项目
- 前端 `type` 不能重复
- 配置路径必须存在
- 配置类型必须和项目指纹识别结果一致
- 生成目标严格以 `projects` 配置为准

## English

The workspace configuration file is always:

```text
.yudao-pilot/config.yaml
```

It is the routing source of truth for Yudao Pilot MCP. AI clients should not bypass it and guess paths.

### Safe Initialization Rules

When the config file is missing, MCP initializes it only if the workspace root is trustworthy.

The server returns `workspace_root_required` and writes nothing when:

- The MCP process working directory is the filesystem root
- The provided `workspace_root` is the filesystem root
- No supported yudao backend or frontend project is detected

When this happens, the AI client should ask the user for the real project workspace directory and retry with `workspace_root`.

### Example

```yaml
version: 1

workspace:
  name: my-yudao-workspace

projects:
  backend:
    path: ../yudao-server
    type: ruoyi-vue-pro-jdk17
    config_profile: local

  frontend:
    - type: VUE3_ELEMENT_PLUS
      path: ../yudao-ui-admin-vue3
    - type: VUE3_VBEN5_ANTD_SCHEMA
      path: ../yudao-ui-admin-vben
    - type: VUE3_ADMIN_UNIAPP_WOT
      path: ../yudao-ui-admin-uniapp

database:
  mode: auto
  host: ""
  port: 3306
  database: ""
  username: ""
  password: ""

codegen:
  apply_to_database: false
  menu_sql_mode: auto
  dict_sql_mode: auto

  routing:
    mode: manual

  manual_rules:
    - module: member
      table_prefixes:
        - merchant_user
        - merchant
        - member
      table_rules:
        - table: member_user
          business: member_user
          entity: MemberUser
```

### Fields

`projects.backend`

- `path`: Backend project path, relative to the workspace or absolute
- `type`: `ruoyi-vue-pro`, `ruoyi-vue-pro-jdk17`, or `yudao-cloud`
- `config_profile`: Backend local config profile, for example `local`

`projects.frontend`

- `type`: Frontend template type
- `path`: Frontend project path
- `type` values must be unique
- A single Vben project path may be reused by multiple Vben template types

Supported frontend types:

- `VUE3_ELEMENT_PLUS`
- `VUE3_VBEN5_ANTD_SCHEMA`
- `VUE3_VBEN5_ANTD_GENERAL`
- `VUE3_VBEN5_EP_SCHEMA`
- `VUE3_VBEN5_EP_GENERAL`
- `VUE3_ADMIN_UNIAPP_WOT`

`database`

- `mode=manual`: Use the connection fields from this config file
- `mode=auto`: Use config fields first, then resolve missing fields from backend local config

`codegen`

- `apply_to_database`: Whether menu/dictionary SQL may be written to the real database; defaults to `false`, which only generates SQL artifacts
- `menu_sql_mode`: Menu SQL mode; supports `auto`, `migration_only`, and `disabled`
- `dict_sql_mode`: Dictionary SQL mode; supports `auto`, `migration_only`, and `disabled`
- `auto`: Generates the matching SQL; allows DB writes when `apply_to_database=true`
- `migration_only`: Generates migration SQL only and never writes to the DB, even when `apply_to_database=true`
- `disabled`: Omits the matching SQL and never writes to the DB

`codegen.routing.mode`

- `manual`: Resolve routes from `manual_rules`
- `ask`: Return candidates and let the AI ask the user
- `auto`: Analyze targets automatically and return a generation plan

`manual_rules`

- Exact `table_rules[].table` matches win first
- `table_prefixes` are used as fallback
- Prefix matching uses longest-first ordering, for example `merchant_user` before `merchant`

### Validation Rules

- One backend project per workspace
- Frontend `type` values must be unique
- Configured paths must exist
- Configured project types must match detected fingerprints
- Generation targets always follow the `projects` config
