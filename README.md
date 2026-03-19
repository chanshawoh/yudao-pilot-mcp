# Yudao Pilot

Yudao Pilot 是一个面向 yudao 生态的 MCP 智能开发助手，核心目标是让 AI 应用能够理解本地 yudao 工作区、读取后端本地数据库配置，并把生成结果准确落到正确的后端和前端项目里。

## 项目定位

Yudao Pilot 不是一个通用型智能编码助手，而是一个专门服务于 yudao 项目的领域适配层。

第一版只聚焦三件事：

- 识别当前工作目录下是否存在受支持的 yudao 后端和前端项目
- 从工作区配置或后端本地配置中读取数据库连接信息
- 通过 MCP 服务为 AI 应用提供代码生成路由能力，让生成结果写入正确项目结构

## 为什么要做

使用 yudao 的团队通常会遇到这些问题：

- 一张业务表往往需要同时生成后端、管理后台、移动端代码
- 不同 yudao 版本和前端形态的目录结构并不完全一致
- AI 应用虽然能生成代码，但并不知道应该把代码写到哪个模块、哪个项目
- 数据库连接通常放在本地配置中，AI 应用如果没有项目感知能力，很容易猜错

Yudao Pilot 要解决的，就是这个“AI 能写，但不懂 yudao 项目结构”的问题。

## 第一版范围

第一版有意收敛范围，只做最核心的能力。

包含：

- 基于 stdio 的 MCP 服务
- 基于当前目录的工作区识别
- 使用 `./.yudao-pilot/config.yaml` 作为唯一配置入口
- 校验 1 个后端项目和多个不重复前端类型
- 基于 `pom.xml`、`package.json`、依赖和版本的项目指纹识别，不依赖目录名
- 解析后端本地配置中的数据库连接信息
- 基于配置规则的代码生成路由

第一版暂不包含：

- 数据库副本或沙箱
- DDL / DML 同步与合并
- 自动部署流水线
- 报错后自动修复重试的闭环

## 工作区约定

Yudao Pilot 默认以当前目录作为工作区根目录，并要求存在配置文件：

```text
./.yudao-pilot/config.yaml
```

如果配置文件不存在，MCP 服务应该返回初始化模板，由 AI 应用引导用户完成首次配置。

## 配置模型

工作区配置主要声明以下信息：

- 当前使用哪个后端项目
- 当前有哪些前端项目类型
- 数据库连接如何获取
- 表名如何映射到模块、业务名、实体名

示例：

```yaml
version: 1

workspace:
  name: 我的 yudao 工作区

projects:
  backend:
    path: ../yudao-server
    type: ruoyi-vue-pro-jdk17
    config_profile: local

  frontend:
    - type: yudao-ui-admin-vue3
      path: ../yudao-ui-admin-vue3
    - type: yudao-ui-admin-uniapp
      path: ../yudao-ui-admin-uniapp

database:
  mode: auto
  host: "localhost"
  port: 3306
  database: ""
  username: "root"
  password: "123456"

codegen:
  routing:
    mode: manual

  manual_rules:
    - module: member
      table_prefixes:
        - merchant_user
        - merchant
        - member
      table_rules:
        - table: member
          business: member
          entity: Member
        - table: member_user
          business: member_user
          entity: MemberUser
```

### 配置字段说明

#### `version`

- 配置文件版本号
- 第一版固定为 `1`

#### `workspace`

- `name`
  - 当前工作区名称，仅用于标识和展示

#### `projects`

- `backend`
  - 当前工作区唯一的后端项目配置
- `backend.path`
  - 后端项目相对当前工作区根目录的路径
- `backend.type`
  - 后端项目类型
  - 当前支持：`ruoyi-vue-pro`、`ruoyi-vue-pro-jdk17`、`yudao-cloud`
- `backend.config_profile`
  - 读取后端本地配置时使用的环境名
  - 例如 `local`，会优先尝试 `application-local.yaml`、`application-local.yml`

- `frontend`
  - 当前工作区下的前端项目列表
- `frontend[].type`
  - 前端项目类型
  - 当前支持：`yudao-ui-admin-vue3`、`yudao-ui-admin-vben`、`yudao-ui-admin-uniapp`
- `frontend[].path`
  - 前端项目相对当前工作区根目录的路径

#### `database`

- `mode`
  - 数据库连接解析模式
  - `manual`：直接使用配置中填写的数据库连接
  - `auto`：优先读取配置中的连接；如果为空，则继续从后端本地配置中解析
- `host`
  - 数据库主机地址
- `port`
  - 数据库端口，默认 `3306`
- `database`
  - 数据库名
- `username`
  - 数据库用户名
- `password`
  - 数据库密码

#### `codegen`

- `routing`
  - 代码生成路由策略配置
- `routing.mode`
  - 当前支持：`auto`、`ask`、`manual`
  - `auto`：由 MCP 自动分析目标位置，并告诉 AI 先生成代码，再回调 MCP 落盘
  - `ask`：MCP 返回候选位置，由 AI 询问用户确认
  - `manual`：严格按 `manual_rules` 规则解析，不依赖临时追问

- `manual_rules`
  - 手动路由规则列表
- `manual_rules[].module`
  - 当前规则归属的业务模块，例如 `system`、`member`、`mall`
- `manual_rules[].table_prefixes`
  - 表前缀列表
  - 当 `table_rules` 没有精确命中时，使用这里的前缀做最长优先匹配
- `manual_rules[].table_rules`
  - 针对具体表名的精确规则

- `manual_rules[].table_rules[].table`
  - 数据库表名
- `manual_rules[].table_rules[].business`
  - 业务标识
  - 用于业务目录、菜单、路由等命名
- `manual_rules[].table_rules[].entity`
  - 实体名
  - 用于实体类、VO、DTO、前端类型名等命名

### 配置解析规则

- 一个工作区只能有一个后端项目
- `projects.frontend` 中的 `type` 不能重复
- 所有配置路径都必须存在
- 配置中的项目类型必须和实际识别结果一致，否则校验失败
- `manual_rules.table_rules` 的精确匹配优先级高于 `table_prefixes`
- 表前缀匹配必须按最长优先处理，例如 `merchant_user` 优先于 `merchant`
- 最终生成目标严格按 `projects` 中已经配置的后端和前端项目执行

## 核心规则

- 一个工作区只能配置一个后端项目
- `projects.frontend` 中的 `type` 不能重复
- 配置中的路径如果不存在，校验直接失败
- 配置中的项目类型如果和实际识别结果不一致，校验直接失败
- `manual` 模式下，`table_rules.table` 的精确匹配优先级高于前缀推导
- 表前缀匹配必须采用最长优先，例如 `merchant_user` 优先于 `merchant`

## MCP 职责边界

Yudao Pilot 负责：

- 理解当前工作区
- 校验项目配置和项目类型
- 解析数据库连接信息
- 计算代码生成的目标路由
- 接收 AI 应用生成的代码并写入正确位置

AI 应用负责：

- 和用户交互
- 明确用户想生成什么业务
- 生成代码内容
- 再次调用 Yudao Pilot 完成落盘

## 建议的 MCP 工具

第一版可以围绕这些工具展开：

- `load_workspace_config`
- `init_workspace_config`
- `inspect_project_path`
- `compare_codegen_reference_projects`
- `validate_workspace_projects`
- `resolve_database_config`
- `infer_codegen_plan`
- `inspect_codegen_context`
- `inspect_table_schema`
- `generate_codegen_scaffold`
- `write_generated_files`
- `write_mysql_migration`

其中：

- `compare_codegen_reference_projects` 用来确认 `ruoyi-vue-pro` 和 `ruoyi-vue-pro-jdk17` 的代码生成核心是否可复用
- `inspect_codegen_context` 会补齐模块名、业务名、实体名、权限标识、后端默认 codegen 配置、前端模板类型、菜单父级候选、生成文件计划和迁移文件建议路径
- `inspect_table_schema` 会从后端仓库的 MySQL 结构文件中解析指定表的字段信息，供后续字段级代码生成复用
- `generate_codegen_scaffold` 会基于当前上下文直接生成第一版后端和前端骨架代码，可只预览，也可直接写入工作区
- `write_mysql_migration` 会把新增 SQL 结构写入 `sql/mysql/migrations/`，文件名采用 Laravel 风格时间戳

## 目录结构建议

```text
yudao-pilot-mcp/
├── README.md
├── docs/
│   ├── product.md
│   └── roadmap.md
├── pyproject.toml
└── src/
    └── yudao_pilot/
        ├── server.py
        ├── config.py
        ├── inspector.py
        ├── database.py
        └── writer.py
```

## 相关文档

- 产品与商业说明：[docs/product.md](/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/docs/product.md)
- 路线图文档：[docs/roadmap.md](/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/docs/roadmap.md)

## 开发测试

项目已内置开发期测试能力，推荐直接使用当前 `.venv` 运行：

```bash
./.venv/bin/python -m pytest
```

测试覆盖了这些核心能力：

- 项目类型识别
- 工作区配置校验
- 后端本地数据库配置解析
- MySQL 表结构解析
- 代码生成上下文构建
- 首版骨架代码生成
- 后端目标落盘根目录修正

开发用工作区配置样例已生成在：

- [tests/fixtures/dev-workspace/.yudao-pilot/config.yaml](/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/tests/fixtures/dev-workspace/.yudao-pilot/config.yaml)

如果你要本地联调 MCP 工具，直接把该样例作为工作区根目录即可。

## 当前状态

当前仓库已经完成第一版 MCP 服务骨架，具备以下基础能力：

- 初始化和加载 `./.yudao-pilot/config.yaml`
- 校验后端和前端项目类型是否与配置严格匹配
- 对比 `ruoyi-vue-pro` 与 `ruoyi-vue-pro-jdk17` 的代码生成核心差异
- 从后端本地 `application*.yaml` 解析数据库连接
- 推导表对应的模块、业务名、实体名、前端模板和菜单上下文
- 将新的 MySQL 迁移文件写入 `sql/mysql/migrations/`

当前推荐直接以 `ruoyi-vue-pro-jdk17` 作为第一版参考实现继续开发。
