# Test Spec: Frontend TODO Fill Aligned to Upstream Codegen

## Scope

Verify only the frontend generator TODO-completion work described in:
- `/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/.omx/plans/prd-codegen-frontend-todo-fill.md`

## Test Principles

1. Assert generated behavior shape, not incidental formatting.
2. Use representative tables with resolved schema fixtures.
3. Prevent scope creep by asserting unchanged backend/SQL behavior where relevant.
4. Do not require rewrites for frontend targets that do not currently emit TODO placeholders.

## Targeted Tests

### Vue3 Element Plus

1. Generated `src/api/.../index.ts` includes:
   - list/page query
   - get detail
   - create
   - update
   - delete
   - export
2. Generated `src/views/.../index.vue` includes:
   - query model
   - `getList` or equivalent list-loading flow
   - query/reset handlers
   - create/edit trigger
   - delete handler
   - export handler
   - form modal/component wiring
3. Generated form component includes:
   - open/create/update flow
   - detail fetch on edit
   - submit handler
   - reset behavior
   - field-derived validation hooks where schema permits

### Non-Vue3 Scope Guards

1. If Vben outputs are untouched because they do not emit TODO placeholders, existing Vben assertions remain green.
2. If Uniapp outputs are untouched because they do not emit TODO placeholders, existing Uniapp assertions remain green.
3. If any non-Vue3 output is touched, add a targeted regression proving it previously emitted a TODO-backed placeholder and now emits concrete behavior.

### Scope Guard Tests

1. Existing backend controller generation assertions remain green without modification to expected backend behavior.
2. Existing SQL generation tests remain green.
3. Existing naming/path behavior assertions remain green unless a touched frontend TODO path necessarily depends on current behavior.

## Verification Commands

1. `uv run pytest tests/test_mcp_tools.py -k 'frontend or vue3 or vben or uniapp'`
2. `uv run pytest`

## Manual Review Checklist

1. Compare one representative Vue3 generated output to upstream `vue3` templates.
2. Compare any touched non-Vue3 generated output to the corresponding upstream template.
3. Confirm no backend generation diff is required to satisfy the frontend-only scope.
4. Confirm no untouched frontend target was rewritten merely for parity.

## Exit Criteria

1. Targeted frontend generation tests pass.
2. Full pytest passes.
3. Generated outputs contain no remaining TODO placeholders in the scoped frontend renderers.
4. No out-of-scope backend/SQL/naming changes were introduced.
5. No non-TODO frontend targets were rewritten without explicit evidence.
