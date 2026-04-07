# Deep Interview Transcript Summary: codegen-sql-naming

- Profile: standard
- Context type: brownfield
- Final ambiguity: 5%
- Threshold: 20%
- Context snapshot: `.omx/context/codegen-gap-fixes-20260407T051911Z.md`

## Clarity Breakdown

| Dimension | Score |
| --- | ---: |
| Intent | 0.94 |
| Outcome | 0.94 |
| Scope | 0.92 |
| Constraints | 0.97 |
| Success Criteria | 0.86 |
| Brownfield Context | 0.92 |

## Key Q&A

1. SQL default behavior
   - Answer: 默认生成菜单/字典迁移 SQL；是否执行到数据库由显式配置控制。
2. Naming rule precedence
   - Answer: 仍然以原 Java codegen 规则优先。
3. Scope shape
   - Answer: 这次范围包含代码逻辑、测试、README。
4. Config shape
   - Answer: 新增一个总开关配置项，配置优先级最高。
5. Conflict rule
   - Answer: 配置总开关优先，并且移除工具参数 `apply_menu_to_database` 逻辑。

## Pressure Pass Findings

- Earlier “frontend-only” scope is explicitly superseded for this new branch.
- Earlier tentative custom naming-rule ideas remain rejected; even in this new branch, naming still follows original Java codegen precedence.
- The meaningful behavioral change is limited to SQL database-apply control semantics, not SQL generation itself.
