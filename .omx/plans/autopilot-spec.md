# Autopilot Expansion Spec: mcp-skill

## Input

- Primary requirements source: `.omx/specs/deep-interview-mcp-skill.md`
- Context snapshot: `.omx/context/mcp-skill-20260406T151931Z.md`

## Goal

实现一个全局可复用的 Codex Skill，把当前 `yudao-pilot-mcp` 的 MCP 能力封装成执行型入口，让生成型 Yudao 请求默认优先使用该 Skill / MCP 链路，而不是跳过 MCP 自己拼代码。

## Required Deliverables

1. 全局 Skill 目录：
   - `/Users/woodynew/.codex/skills/yudao-pilot-mcp/SKILL.md`
2. 必要时补充轻量参考文件，但默认优先单文件实现
3. 不加入 MCP 安装说明

## Required Behavior

- 覆盖当前 MCP 全能力，而不是只覆盖主链
- 主链路默认顺序：
  - `load_workspace_config`
  - `init_workspace_config`（若缺失）
  - `validate_workspace_projects`
  - `resolve_database_config`
  - `inspect_codegen_context` 或 `inspect_table_schema`
  - `generate_codegen_scaffold` / `generate_codegen_sql`
  - `write_generated_files` / `write_mysql_migration` / 数据库写入（满足条件时）
- 对 `module_name / business_name / entity_name` 允许自动推导
- 对数据库不可连接、表不存在且无迁移来源的情况，必须停止并要求用户处理
- 对无 `write_files` 意图的请求，默认不真实写入
- 对高风险数据库写操作，要求人工确认

## Non-goals

- 不负责联调启动后端 / 前端
- 不负责修改 `.ai/` 协议文件
- 不负责描述 MCP 安装步骤

## Brownfield Sources

- `src/yudao_pilot/server.py`
- `.ai/ai-integration.md`
- `.ai/bootstrap.md`
- `.ai/dev-standards.md`
- `README.md`

## Success Criteria

1. Skill 元数据能让 Codex 在 Yudao 代码生成 / SQL / 表结构分析 / 工作区校验等场景下触发
2. Skill 正文清晰描述所有 13 个 MCP 工具的角色与分支用法
3. Skill 正文明确默认主链、停止规则、非目标、写入边界
4. Skill 内容忠实反映当前仓库能力，不引入虚构工具或安装说明
