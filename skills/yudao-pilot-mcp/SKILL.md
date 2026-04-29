---
name: yudao-pilot-mcp
description: >
  Use when working on a yudao / ruoyi-vue-pro / 芋道项目 and the user wants AI-assisted code generation,
  project detection, database config discovery, table schema inspection, menu/dict SQL generation,
  or safe writing of generated backend/frontend files through the Yudao Pilot MCP server. Also use for Chinese
  requests such as 芋道代码生成, 若依代码生成, 生成菜单SQL, 生成前后端代码, 初始化 .yudao-pilot 配置.
---

# Yudao Pilot MCP

Use this skill before calling the Yudao Pilot MCP server or when deciding whether the MCP is appropriate.

## 中文说明（给人类）

这个 skill 是给 AI 使用 Yudao Pilot MCP 的操作说明，也方便中文用户快速判断“什么时候该让 AI 调 MCP”。

适合使用的场景：

- 你在芋道 / ruoyi-vue-pro / 若依生态项目里开发
- 想让 AI 根据数据库表生成后端、管理后台、uni-app 等代码
- 想让 AI 自动识别当前项目里的后端、前端目录
- 想生成菜单 SQL、字典 SQL、H2 测试 SQL
- 想让 AI 把生成结果写到正确模块，而不是凭目录名乱猜

不适合使用的场景：

- 普通 Java / Vue 代码修改
- 和芋道代码生成无关的重构
- 只想让 AI 解释代码或做普通 bug 修复
- 还没确认要生成哪张表、哪个业务模块、哪些前端目标

使用边界：

- `./.yudao-pilot/config.yaml` 是路由依据，AI 不应该绕过它猜路径
- MCP 第一次自动生成 yaml 后，AI 必须告诉用户已写入哪些项目目录，并询问是继续还是先人工审阅
- 遇到 `packaging=pom` 的聚合模块时，AI 不应该把代码写到聚合模块根目录，而要使用 MCP 推导出的 jar 子模块目标
- 写库操作只有在 `codegen.apply_to_database=true` 时才允许执行

## When To Use

Use Yudao Pilot MCP when the user is in a yudao / ruoyi-vue-pro workspace and asks to:

- detect backend/frontend project layout
- initialize or inspect `./.yudao-pilot/config.yaml`
- resolve local database settings from yudao backend config
- inspect a MySQL table schema for code generation
- infer module/business/entity routing for a table
- generate backend/frontend scaffold files for yudao codegen
- generate menu/dict SQL and H2 test SQL
- safely write generated files into configured backend/frontend projects

Do not use it for general coding, arbitrary refactors, UI-only edits unrelated to yudao codegen, or when the user has not asked for yudao project-aware generation.

## MCP Server Location

Development checkout:

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/woodynew/.codex/worktrees/1583/yudao-pilot-mcp",
        "run",
        "yudao-pilot"
      ]
    }
  }
}
```

Installed user environment:

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

If the current MCP client has no `yudao-pilot` server configured, add it to the MCP client config first. Prefer the installed `yudao-pilot` command in normal user environments; use the development checkout path only for local development of this MCP package.

## Required Workflow

1. Treat the MCP client's current project root as the workspace root.
2. Call `load_workspace_config` first.
3. If the response has `error_code=config_initialized`, stop the current generation flow. Tell the user the YAML was created, list the detected backend/frontend paths from `config_summary`, and ask whether to continue or stop so they can manually review/edit `./.yudao-pilot/config.yaml`.
4. If config exists, call `validate_workspace_projects`.
5. For code generation, call `inspect_codegen_context` before generating files.
6. If table schema is unresolved, stop and follow the MCP response: create/provide migration SQL or fix DB config before continuing.
7. Preview generated output with `generate_codegen_scaffold(write_files=false)` unless the user explicitly requested direct writing.
8. Only call write-enabled tools (`generate_codegen_scaffold(write_files=true)`, `generate_codegen_sql(write_files=true)`, `write_generated_files`, `write_mysql_migration`) when the target paths and generated content are clear.

## Boundaries And Safety

- Respect `./.yudao-pilot/config.yaml` as the routing source of truth.
- Do not guess backend/frontend paths by directory names alone; rely on MCP project detection and validation.
- For aggregator Maven modules with `packaging=pom`, do not write Java code into the aggregator itself. Use the MCP-generated backend target, which may select an existing child jar module or propose a new child module path.
- Do not write menu/dict SQL to a real database unless `codegen.apply_to_database=true`.
- If MCP returns `should_stop=true`, pause the current generation and report the requested user decision.
- If generated target paths look wrong, stop and inspect `resolved_from_config`, `backend_project.codegen_target`, and `generated_file_plan` before writing.

## Common Tool Order

For a typical table codegen request:

```text
load_workspace_config
validate_workspace_projects
resolve_database_config
inspect_codegen_context(table_name)
generate_codegen_sql(table_name, write_files=false)
generate_codegen_scaffold(table_name, write_files=false)
generate_codegen_sql(table_name, write_files=true)        # only after confirmation
generate_codegen_scaffold(table_name, write_files=true)   # only after confirmation
```

Use `inspect_project_path` when the user asks whether a specific path is a supported yudao backend/frontend project.

## Framework Detection

Yudao Pilot detects project type by parsing file fingerprints (`pom.xml`, `package.json`), not by directory names, root project names, Maven `groupId` / `artifactId`, or Java base package names. Users commonly rename the business project and Java package, so those values must never be required signals.

### Backend Detection

Target repository: [YunaiV/ruoyi-vue-pro](https://github.com/YunaiV/ruoyi-vue-pro)

Prerequisite: `pom.xml` exists at the project root.

**Step 1: yudao fingerprint scoring (total score ≥ 5 required)**

| Fingerprint | Score | Notes |
|-------------|-------|-------|
| Root `pom.xml` has `groupId=cn.iocoder.boot` + `artifactId=yudao` | +2 | Official root POM coordinates; optional evidence only |
| Current POM is a backend startup module such as `yudao-server` or `*-server` | +2 | Supports renamed business server modules |
| `modules` contains `yudao-dependencies`, `yudao-framework`, `yudao-server`, `yudao-module-system`, or `yudao-module-infra` | +1 each | Stable framework layout markers |
| `modules` contains one or more `yudao-module-*` entries | +1 to +2 | Business/module layout marker |
| `modules` contains both `yudao-framework` and `yudao-module-*` | +2 | Strong multi-module yudao layout signal |
| `dependencyManagement` imports `cn.iocoder.boot:yudao-dependencies` | +3 | Strongest signal — BOM import |
| Dependencies contain `yudao-spring-boot-starter-protection` | +2 | Core yudao security dependency |
| Dependencies contain `yudao-module-system` | +1 | System module |
| Dependencies contain `yudao-module-infra` | +1 | Infrastructure module |
| `packaging=pom` | +1 | Aggregator module marker |

Do not fail detection only because the root Maven coordinates were renamed, for example `com.example.safe:safe-voyage-parent`, or because the Java base package changed from `cn.iocoder.yudao` to a company-specific package.

**Step 2: Distinguish three backend variants**

| Type | Identification criteria |
|------|------------------------|
| `yudao-cloud` | Imports `spring-cloud-dependencies` / `spring-cloud-alibaba-dependencies`, or dependencies contain `spring-cloud-starter-*` (gateway, openfeign, nacos, sentinel, etc.), cloud score ≥ 2 |
| `ruoyi-vue-pro-jdk17` | `spring.boot.version` is 3.x, `java.version` ≥ 17, dependencies contain Boot3-only packages (`mybatis-plus-spring-boot3-starter`, `knife4j-openapi3-jakarta-*`, etc.), boot3 score > boot2 score and ≥ 3 |
| `ruoyi-vue-pro` | `spring.boot.version` is 2.x, `java.version` = 8, dependencies contain Boot2-only packages (`mybatis-plus-boot-starter`, `knife4j-openapi3-spring-boot-starter`, etc.), boot2 score ≥ 3 |

**Typical root POM structure**:

```xml
<groupId>cn.iocoder.boot</groupId>
<artifactId>yudao</artifactId>
<packaging>pom</packaging>
<modules>
    <module>yudao-dependencies</module>
    <module>yudao-framework</module>
    <module>yudao-server</module>
    <module>yudao-module-system</module>
    <module>yudao-module-infra</module>
    <!-- more yudao-module-* modules -->
</modules>
```

### Frontend Detection

Prerequisite: `package.json` exists at the project root.

| Project type | Identification criteria |
|-------------|------------------------|
| `yudao-ui-admin-vue3` | Dependencies contain `element-plus` (+4), `vue` major version is 3 (+2), `@vitejs/plugin-vue` (+2), `vite` (+1), `pinia` + `vue-router` (+1), total score ≥ 4 |
| `yudao-ui-admin-vben` | Dependencies contain `@vben/*` workspace packages (+4), scripts contain `turbo` (+2), devDependencies contain `workspace:*` (+1), total score ≥ 4 |
| `yudao-ui-admin-uniapp` | Dependencies contain `@dcloudio/uni-app` (+4), multiple `@dcloudio/uni-*` packages (+2), devDependencies contain `@dcloudio/vite-plugin-uni` (+2), `@uni-helper/*` ecosystem (+1), total score ≥ 4 |

### Frontend Codegen Type Mapping

| Codegen template type | Frontend project |
|-----------------------|-----------------|
| `VUE3_ELEMENT_PLUS` | `yudao-ui-admin-vue3` |
| `VUE3_VBEN5_ANTD_SCHEMA` / `ANTD_GENERAL` / `EP_SCHEMA` / `EP_GENERAL` | `yudao-ui-admin-vben` |
| `VUE3_ADMIN_UNIAPP_WOT` | `yudao-ui-admin-uniapp` |

### Auto Discovery

`init_workspace_config` scans up to 3 directory levels deep from the workspace root to auto-detect and recommend backend and frontend project paths. It skips `.git`, `node_modules`, `target`, `.venv`, and other non-project directories.
