# Autopilot Implementation Plan: mcp-skill

## Phase 1 Plan

1. 读取当前 MCP 入口与协议文档，提炼 13 个工具的职责与推荐顺序
2. 设计 Skill 名称、触发描述和正文结构
3. 在 `/Users/woodynew/.codex/skills/yudao-pilot-mcp/` 下创建 `SKILL.md`
4. 在 Skill 中编码：
   - 触发条件
   - 默认主执行链
   - 全量能力分支
   - 停止规则
   - 非目标
   - 成功判据
5. 用只读验证检查 Skill 是否包含：
   - 13 个工具
   - 默认主链
   - 停止规则
   - 非目标
   - 无 MCP 安装说明
6. 若验证通过，更新 autopilot 状态并汇报结果

## QA Strategy

- 使用 `rg` 校验关键段落、关键工具名和禁止项
- 手动审查 Skill 元数据是否满足触发与简洁要求
- 不对仓库源码做行为更改；本轮产物为 Skill 文档
