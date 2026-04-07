# Test Spec: SQL Apply Control and Naming Precedence

## Scope

Verify only the SQL-control and naming-precedence changes described in:
- `/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/.omx/plans/prd-codegen-sql-naming.md`

## Test Principles

1. Separate generation assertions from database-apply assertions.
2. Prove config precedence explicitly.
3. Guard naming behavior from accidental drift.

## Targeted Tests

### Config / Apply Control

1. New workspace config field `codegen.apply_to_database` is parsed and exposed correctly.
2. Default config still produces menu/dict SQL bundles.
3. When DB-apply config is disabled, `generate_codegen_sql_tool()` does not attempt menu/dict DB writes even when write conditions otherwise match.
4. Existing response payload clearly reports the skip as config-driven.
5. Any behavior formerly tied to `apply_menu_to_database` is removed or ignored according to the new contract.
6. `menu_sql_mode` / `dict_sql_mode` do not independently veto DB apply; they only decide whether the corresponding SQL fragment exists.

### SQL Generation Semantics

1. `menu_sql_mode` / `dict_sql_mode` still control whether SQL fragments are generated into migration output.
2. Default configuration still generates both menu and dict migration SQL when applicable.
3. `disabled` still suppresses the corresponding fragment without relying on DB-apply control.
4. When a fragment is absent because a side is `disabled`, there is no DB apply attempt for that side because nothing was generated.

### Naming No-Regression

1. Existing tests for `derive_business_name()` / route/path outcomes remain green.
2. Permission-prefix derivation remains unchanged.
3. No frontend/backend file-plan naming behavior changes as a side effect of this branch.

### Documentation Sync

1. README examples and semantics table reflect:
   - generation default still on
   - DB apply controlled by config
   - no `apply_menu_to_database` behavior path

## Verification Commands

1. `uv run pytest tests/test_mcp_tools.py -k 'codegen_sql or database or business_name or permission_prefix'`
2. `uv run pytest`

## Manual Review Checklist

1. Inspect config template and README side by side.
2. Confirm no remaining user-facing docs claim parameter-driven DB apply.
3. Confirm touched code does not alter naming derivation helpers.

## Exit Criteria

1. Targeted SQL-control and naming no-regression tests pass.
2. Full `uv run pytest` passes.
3. README and config template match actual runtime behavior.
4. No accidental naming-rule changes were introduced.
5. `codegen.apply_to_database` is the only documented DB-apply authority.
