# Deep Interview Spec: mcp-skill

## Metadata

- Profile: `standard`
- Rounds: `5`
- Final Ambiguity: `12.5%`
- Threshold: `20%`
- Context Type: `brownfield`
- Context Snapshot: `.omx/context/mcp-skill-20260406T151931Z.md`
- Transcript: `.omx/interviews/mcp-skill-20260407T022129Z.md`

## Clarity Breakdown

| Dimension | Score |
|---|---:|
| Intent Clarity | 0.86 |
| Outcome Clarity | 0.86 |
| Scope Clarity | 0.95 |
| Constraint Clarity | 0.92 |
| Success Criteria Clarity | 0.84 |
| Context Clarity | 0.78 |

## Intent

把当前 `yudao-pilot-mcp` 的真实 MCP 能力封装成一个“执行型 Skill”。

这个 Skill 的目标不是解释项目，而是让安装了它的 AI/开发者，在遇到 Yudao 代码生成类请求时，默认优先走当前 MCP 的能力链路，而不是跳过 MCP 自己拼代码。

## Desired Outcome

产出一个可安装、可复用的 Skill，具备以下行为：

- 生成型请求默认优先走该 Skill
- Skill 使用当前 MCP 的真实工具能力作为执行入口
- 在输入只有 `table_name` 时，能自动驱动主链路
- 对于不可安全继续的场景，会明确停止，而不是静默降级到猜测式执行

## In Scope

第一版范围为 `C`：纳入当前 MCP 的全部能力，而不是只封装主链路。

应覆盖的能力包括：

1. `load_workspace_config_tool`
2. `init_workspace_config_tool`
3. `inspect_project_path_tool`
4. `compare_codegen_reference_projects_tool`
5. `validate_workspace_projects_tool`
6. `resolve_database_config_tool`
7. `infer_codegen_plan_tool`
8. `inspect_codegen_context_tool`
9. `inspect_table_schema_tool`
10. `generate_codegen_scaffold_tool`
11. `write_generated_files_tool`
12. `write_mysql_migration_tool`
13. `generate_codegen_sql_tool`

Skill 中需要把这些工具组织成清晰的执行分支，至少包括：

- 默认主执行链
- 仅读分析链
- SQL 生成链
- 脚手架生成链
- 写入链
- 项目识别 / 参考差异分析等辅助入口

## Out-of-Scope / Non-goals

- 不负责联调启动后端 / 前端
- 不负责修改 `.ai/` 协议文件
- 不在没有 `write_files` 意图时真实写入
- 不替代人工确认高风险数据库写操作
- 当前阶段不在 Skill 中加入 MCP 安装说明

## Decision Boundaries

### Skill 可自动决定

- 配置缺失时，自动初始化默认可用配置，不需要用户确认
- `module_name / business_name / entity_name` 可以自动推导，不必确认
- 生成型请求默认优先使用该 Skill / MCP 链路

### Skill 必须停止并要求用户处理

- 数据库无法连接时，直接停止运行，并要求用户配置数据库连接
- 数据库表不存在，且找不到迁移文件时，直接停止运行，并要求用户先创建表
- 高风险数据库写操作，不替代人工确认

## Constraints

- Skill 必须忠实反映当前 MCP 的真实能力边界，不能虚构不存在的工具或安装流程
- Skill 要以 `src/yudao_pilot/server.py` 和 `.ai/ai-integration.md` 的实际能力/顺序为基础
- Skill 是执行入口，不是单纯操作文档
- 但它仍然要尊重显式的停止规则，不能为了“自动”而越界执行

## Testable Acceptance Criteria

1. 当开发者只提供 `table_name` 时，Skill 能自动完成：
   `load_config/init -> validate -> resolve_db -> inspect/generate`

2. 当数据库无法连接时，Skill 会直接停止并要求用户配置数据库，不会继续误写入

3. 当目标表不存在，且仓库内找不到对应迁移文件或可用结构来源时，Skill 会直接停止并要求用户创建表

4. 对于生成型请求，Skill 默认优先走 MCP，而不是跳过 MCP 自己拼代码

5. 对于没有 `write_files` 意图的请求，Skill 不会进行真实写入

6. 高风险数据库写操作仍要求人工确认，不由 Skill 擅自执行

## Assumptions Exposed + Resolutions

| Assumption | Resolution |
|---|---|
| “执行型 Skill” 应该尽量全自动 | 不是绝对全自动；在数据库不可连接、表不存在且无迁移文件等场景必须停止 |
| 只封装主链路就够了 | 否。第一版明确要求覆盖当前 MCP 全能力 |
| 自动执行意味着可以跳过 MCP | 否。Skill 的价值恰恰是强制优先使用 MCP |
| 数据库异常时可以降级只读分析 | 被新规则覆盖：数据库不可连接时直接停止 |

## Pressure-pass Findings

- Revisiting: “安装了 Skill 就必定要用这个能力”
- Deeper challenge: 这件事为什么成立？最小成功证据是什么？
- Resolution:
  - 用户把这个主张转化成了可验收标准，而不只是偏好表达
  - 成功标准落在“自动走主链路”“数据库异常不误写”“默认优先 MCP”三个方面

## Brownfield Evidence vs Inference

### Evidence

- `src/yudao_pilot/server.py` 中实际注册了 13 个 MCP 工具
- `.ai/ai-integration.md` 中已存在推荐调用顺序
- `.ai/bootstrap.md` / `.ai/dev-standards.md` 已定义了工作区、数据库、写入和联调等边界

### Inference

- Skill 的最佳结构应当围绕 MCP 执行链和条件分支来组织，而不是按文档章节组织
- 因为用户强调“安装后必定要用”，Skill 很可能需要在文案中写出“生成型请求默认优先调用该能力”的强约束

## Technical Context Findings

- MCP 服务名：`Yudao Pilot`
- 代码入口：`src/yudao_pilot/server.py`
- 当前能力集中在：
  - 工作区配置
  - 项目识别
  - 数据库配置解析
  - 表结构 / codegen 上下文分析
  - 脚手架生成
  - SQL 生成
  - 文件 / 迁移写入

## Recommended Implementation Shape

Skill 至少应包含以下章节：

1. 适用场景：什么时候必须优先使用该 Skill
2. 默认执行原则：生成型请求优先 MCP，不能跳过
3. 主执行链：`load/init -> validate -> resolve_db -> inspect/generate`
4. 分支规则：
   - SQL
   - scaffold
   - write
   - inspect-only
   - compare / inspect-project-path
5. 停止规则
6. 非目标
7. 成功标准

## Handoff Contract

后续实现该 Skill 时，必须保持以下要求不变：

- “执行型”定位不能退化成“说明书”
- 默认优先 MCP 不能变成“可选建议”
- 数据库不可连接 / 表不存在且无迁移文件时，必须停止
- 不得擅自补入 MCP 安装说明
