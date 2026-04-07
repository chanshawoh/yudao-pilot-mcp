# PRD: SQL Apply Control and Naming Precedence

## Metadata

- Source spec: `/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/.omx/specs/deep-interview-codegen-sql-naming.md`
- Context snapshot: `/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/.omx/context/codegen-sql-naming-20260407T082138Z.md`
- Planning mode: `ralplan`
- Scope: menu/dict SQL apply control + naming-rule preservation
- Status: approved for execution

## RALPLAN-DR Summary

### Principles

1. Generate-by-default, apply-by-permission: menu/dict SQL should still be generated automatically, but DB application must be explicitly allowed by workspace config.
2. Config beats invocation: runtime/tool inputs must never bypass the workspace-level DB-apply permission switch.
3. Preserve naming authority: original Java codegen naming precedence remains the source of truth.
4. Change semantics once, document everywhere: config model, tool flow, tests, and README must move together.

### Decision Drivers

1. The user explicitly wants menu/dict migration SQL to keep generating by default.
2. The user explicitly wants DB execution controlled by configuration with highest priority and no `apply_menu_to_database` logic remaining.
3. The user explicitly rejected reintroducing custom naming rules and kept original Java codegen precedence.

### Viable Options

#### Option 1: Reinterpret `menu_sql_mode` / `dict_sql_mode` only

- Pros: smallest surface-area change, no new config field.
- Cons: overloads generation-vs-apply semantics, keeps behavior implicit, harder to document clearly, weaker precedence story.

#### Option 2: Add a single workspace config apply switch

- Pros: matches user request exactly, clean precedence model, simple docs and tests, keeps generation semantics separate from DB-apply permission.
- Cons: requires config schema/template/README/test updates and server-flow refactor.

#### Option 3: Add separate menu/dict DB-apply switches

- Pros: more granular future control.
- Cons: user explicitly chose one total switch, more complexity than needed now.

### Recommendation

Adopt Option 2. It is the only option that matches the clarified requirement set without semantic ambiguity or extra policy surface.

## Problem Statement

Current codegen behavior mixes SQL generation semantics and database-application semantics:
- `menu_sql_mode` / `dict_sql_mode` default to `auto`
- `generate_codegen_sql_tool()` still accepts and uses `apply_menu_to_database`
- README documents parameter-driven DB writes

This makes “default generate SQL, but only apply to DB when workspace config allows it” impossible to express cleanly.

## Goals

1. Keep menu/dict migration SQL generation on by default.
2. Introduce one workspace config switch controlling whether menu/dict SQL may be applied to the database.
3. Remove `apply_menu_to_database` as a runtime control path.
4. Preserve original Java codegen naming precedence.
5. Update README and tests so behavior is explicit and stable.

## Non-goals

1. Do not redesign naming rules beyond preserving existing Java-codegen precedence.
2. Do not stop generating menu/dict migration SQL by default.
3. Do not change unrelated frontend/backend scaffold behavior.
4. Do not add separate per-menu/per-dict DB-apply switches in this round.

## Brownfield Facts

1. `src/yudao_pilot/config.py` currently defaults `menu_sql_mode` and `dict_sql_mode` to `auto`.
2. `src/yudao_pilot/server.py` still exposes `apply_menu_to_database` and gates DB execution through it.
3. `README.md` still teaches parameter-driven DB apply semantics.
4. Naming precedence currently comes from `derive_business_name()` and `build_frontend_business_path()`, and the user wants that authority preserved rather than replaced.

## ADR

### Decision

Add one workspace-level config switch for DB apply permission, remove `apply_menu_to_database` flow logic, and keep existing naming precedence unchanged.

### Drivers

- Config priority must be absolute.
- SQL generation must remain default-on.
- Naming behavior should not be reopened in this branch.

### Alternatives Considered

- Reuse existing modes for both generation and apply: rejected for semantic overload.
- Separate menu/dict apply switches: rejected as extra complexity against explicit user choice.

### Why Chosen

This cleanly separates “whether SQL is generated” from “whether DB apply is allowed” and keeps the user’s chosen precedence model explicit.

### Consequences

- Config schema/template changes are required.
- Tool signature / tool docs must be updated to stop advertising `apply_menu_to_database`.
- Tests must be updated to validate config precedence rather than runtime parameter control.

### Follow-ups

1. If per-menu/per-dict DB-apply granularity is needed later, treat it as a new planning branch.
2. If naming-rule changes are desired later, start a separate branch because this plan intentionally preserves current precedence.

## Implementation Plan

### Step 1: Introduce the new config switch

- Add one top-priority workspace config field under `codegen`: `apply_to_database`.
- Update `CodegenConfig` defaults and config template comments so the field is explicit.
- Set the default value to `false` according to the clarified rule: generation default-on, DB apply controlled only by config.
- Make the precedence explicit:
  - `menu_sql_mode` / `dict_sql_mode` only control whether SQL fragments are generated
  - `codegen.apply_to_database` alone controls whether menu/dict SQL may be applied to the database

### Step 2: Refactor SQL-apply flow in `generate_codegen_sql_tool()`

- Remove `apply_menu_to_database` as the behavioral switch.
- Replace runtime-parameter-driven DB apply logic with config-driven permission checks.
- Keep SQL bundle generation and file writing behavior intact.
- Preserve menu/dict skip reporting, but base DB-apply decisions on the new config switch plus existing “needs write” conditions.
- Ensure `codegen.apply_to_database=true` still does not apply a disabled menu/dict side when `menu_sql_mode` or `dict_sql_mode` is `disabled`.

### Step 3: Preserve naming-rule behavior explicitly

- Confirm no behavior change to `derive_business_name()` / `build_frontend_business_path()` / permission-prefix derivation is required.
- Add or update regression tests if needed to prove naming precedence stays unchanged while the SQL-control branch lands.

### Step 4: Update docs and regression tests

- Update README config examples and semantics tables.
- Remove or replace references to `apply_menu_to_database`.
- Add/adjust tests for:
  - default SQL generation still on
  - config-disabled DB apply blocks writes even if previous callers would have attempted apply
  - naming behavior unchanged

## Risks

1. Backward-compatibility ambiguity for callers that still pass `apply_menu_to_database`.
2. Accidental coupling between `menu_sql_mode` / `dict_sql_mode` and the new config switch.
3. README drift if examples are updated incompletely.

## Acceptance Criteria

1. Menu/dict migration SQL is still generated by default.
2. DB apply is controlled only by the new workspace config switch `codegen.apply_to_database`.
3. `apply_menu_to_database` no longer controls behavior in the tool flow.
4. `menu_sql_mode` / `dict_sql_mode` do not participate in DB-apply permission decisions; they only govern SQL generation.
5. README/config template accurately document the new behavior.
6. Existing naming precedence is unchanged and covered by regression evidence.
7. Full test suite passes after the change.
8. When a side is `disabled`, it produces no SQL fragment and therefore has nothing to apply; this is a generation outcome, not an extra DB-permission rule.

## Verification Plan

1. Targeted tests for config precedence and SQL generation defaults.
2. Regression tests for naming behavior.
3. Full `uv run pytest`.
4. Static validation / compile checks as already used in this repo.

## Available Agent Types Roster

- `executor`: implementation of config/server/docs/test changes
- `architect`: semantics/precedence review
- `critic`: scope and quality enforcement
- `test-engineer`: regression coverage design
- `verifier`: claim validation and completion evidence
- `explore`: narrow codebase lookups for touched flows

## Suggested Reasoning Levels By Lane

- Config/server semantics lane: `high`
- Test lane: `medium`
- Docs lane: `medium`
- Final verification lane: `high`

## Staffing Guidance

### If executed via `ralph`

1. Update config schema/template and README semantics.
2. Refactor server SQL-apply gating.
3. Add/adjust tests for config precedence and naming no-regression.
4. Run full verification and close.

### If executed via `team`

- Lane 1: config + server flow
- Lane 2: tests + naming no-regression checks
- Lane 3: README/docs synchronization
- Leader responsibility: ensure naming rules are preserved, not “improved”.

## Launch Hints

- `ralph` is the preferred execution path because the touched surfaces are related but not large.
- `team` is optional if you want docs/tests split from server/config work.

## Team Verification Path

1. Config/server lane proves DB apply is config-gated.
2. Test lane proves SQL generation default remains on and naming is unchanged.
3. Docs lane proves README/template examples match code.
4. Final verifier confirms parameter logic is gone from behavior and full pytest is green.
