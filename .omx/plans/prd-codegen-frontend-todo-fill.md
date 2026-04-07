# PRD: Frontend TODO Fill Aligned to Upstream Codegen

## Metadata

- Source spec: `/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/.omx/specs/deep-interview-codegen-gap-fixes.md`
- Planning mode: `ralplan`
- Scope: frontend generator TODO completion only
- Status: approved plan

## RALPLAN-DR Summary

### Principles

1. Upstream-first: when local frontend generator behavior differs from `yudao-module-infra` templates, prefer the upstream template behavior unless the local multi-frontend architecture requires a thin adaptation layer.
2. Scope lock: do not change backend generation, SQL generation defaults, or naming conventions in this round.
3. Replace placeholders with working flows: every current frontend TODO must become concrete generated behavior, not a different placeholder.
4. Shared logic before duplication: when multiple frontend targets need the same semantic behavior, extract or reuse local helper renderers instead of forking logic arbitrarily.

### Decision Drivers

1. The user explicitly narrowed scope to frontend TODO completion only.
2. Upstream `vue3`, `vue3_vben`, and `vue3_admin_uniapp` templates already define the expected CRUD/query/export/form flows.
3. Current local generator still emits explicit TODO-backed frontend placeholders, and only those placeholder-backed paths should change in this round.

### Viable Options

#### Option 1: Minimal TODO patching

- Pros: smallest diff, fastest.
- Cons: likely preserves structural drift from upstream templates; higher risk of incomplete behavior and repeated one-off fixes.

#### Option 2: Targeted upstream-template alignment

- Pros: matches the stated source of truth, removes TODOs by adopting proven flows, keeps scope bounded to frontend generators.
- Cons: requires careful adaptation across three frontend families and regression coverage.

#### Option 3: Full frontend template rewrite from upstream

- Pros: highest fidelity to upstream templates.
- Cons: too broad for this round; would likely disturb local multi-frontend abstractions and exceed scope.

### Recommendation

Adopt Option 2. It is the only option that satisfies both the user’s “按原 JAVA 模板来” constraint and the scope lock against unrelated generator changes.

## Problem Statement

Local frontend scaffold generation in `src/yudao_pilot/scaffold.py` still emits TODO-backed Vue3 behavior and simplified uniapp outputs, while upstream Yudao codegen templates already provide concrete query/list/reset/create/update/delete/export/form flows. The current local output is not production-usable by default.

## Goals

1. Remove the currently emitted frontend TODO placeholders from generated outputs.
2. Align the affected frontend behavior to upstream Yudao templates where the local generator currently emits TODO-backed placeholder logic.
3. Preserve current repository support for multiple frontend targets without proactively rewriting targets that do not currently emit TODO placeholders.

## Non-goals

1. No backend generator changes.
2. No controller export endpoint additions in this round.
3. No menu/dict SQL behavior changes.
4. No renaming-rule overhaul.
5. No proactive rewrite of Vben or Uniapp outputs unless a currently emitted TODO placeholder exists there.
6. No unrelated UI redesign.

## Brownfield Facts

1. Current explicit frontend TODO markers in `/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/src/yudao_pilot/scaffold.py` are at:
   - Vue3 index output
   - Vue3 form output
   - Generic placeholder renderer
2. Upstream reference templates exist at:
   - `/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/yudao-projects/ruoyi-vue-pro-jdk17/yudao-module-infra/src/main/resources/codegen/vue3/api/api.ts.vm`
   - `/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/yudao-projects/ruoyi-vue-pro-jdk17/yudao-module-infra/src/main/resources/codegen/vue3/views/index.vue.vm`
   - `/Users/woodynew/mydata/project/demo/codex/yudao-pilot-mcp/yudao-projects/ruoyi-vue-pro-jdk17/yudao-module-infra/src/main/resources/codegen/vue3/views/form.vue.vm`
   - corresponding `vue3_vben` and `vue3_admin_uniapp` templates
3. Current local Vben outputs already implement substantial behavior and do not currently contain the explicit frontend TODO markers identified in scope.
4. Current local uniapp outputs are simpler than upstream, but this plan should not widen into a rewrite unless an actual TODO-backed placeholder path is being emitted.

## ADR

### Decision

Implement a targeted alignment of local frontend renderers to upstream Yudao codegen templates, limited to replacing currently emitted TODO-backed frontend behavior.

### Drivers

- User requires upstream logic as authority.
- Scope excludes backend and SQL behavior.
- Existing multi-frontend support must remain intact.
- The actionable trigger for change is the presence of current frontend TODO placeholders, not general drift from upstream.

### Alternatives Considered

- Minimal TODO patching only: rejected because it would not reliably align to upstream behavior.
- Full template rewrite: rejected as too broad for the allowed scope.

### Why Chosen

This approach is the narrowest plan that still satisfies the upstream-authority constraint while honoring the user’s later scope lock: only fill current frontend TODO gaps, do not opportunistically rewrite unrelated frontend targets.

### Consequences

- Some local renderers will become structurally closer to upstream templates.
- Tests must shift from presence/absence assertions to behavior-shape assertions for generated outputs.
- Cross-frontend helper boundaries may need light cleanup only where the TODO-backed paths require it.

### Follow-ups

1. If backend export/controller alignment is still desired later, handle it as a separate scoped task.
2. If naming or SQL-default behavior still needs revision later, treat it as a separate planning thread.

## Implementation Plan

### Step 1: Map TODO-backed local generators to upstream templates

- Inventory the exact local renderer functions responsible for frontend outputs:
  - `render_frontend_api`
  - `render_vue3_index`
  - `render_vue3_form`
  - `render_plain_placeholder` where it affects emitted frontend files
- For each affected path, record which upstream template sections are authoritative and which local adaptations are unavoidable.
- Output of this step: an evidence-backed mapping table in the PR branch notes or comments, not a new feature surface.

### Step 2: Bring Vue3 Element Plus outputs to upstream parity

- Align generated API file to upstream CRUD/export contract and type shape.
- Replace the current simplified index page with upstream-style:
  - query form
  - list loading
  - reset/query handlers
  - create/edit modal flow
  - delete flow
  - export flow
  - permission-gated actions where already supported by current generator context
- Replace the current simplified form page with upstream-style:
  - dialog/form refs
  - create/update fetch flow
  - reset handling
  - submit logic
  - field-derived validation where supported by current schema metadata

### Step 3: Apply only the minimum non-Vue3 changes required by actual TODO-backed frontend outputs

- If the generic placeholder renderer is currently used by any emitted frontend path, replace those placeholder outputs with concrete upstream-aligned behavior for that specific target.
- Do not rewrite Vben or Uniapp merely for stylistic upstream parity if they are not currently emitting TODO placeholders.
- If export wiring is added to frontend outputs, it must be explicitly documented as depending on an existing backend contract; this round must not imply a backend generator change.

### Step 4: Lock behavior with regression tests

- Add targeted generation tests for each actually affected frontend family verifying that generated outputs contain working behavior shapes rather than TODO placeholders.
- Cover at minimum:
  - API file includes export method and complete CRUD contract where upstream expects it
  - Vue3 index contains query/reset/list/delete/export/modal wiring
  - Vue3 form contains fetch/reset/create/update wiring
  - any non-Vue3 frontend path touched because of an actual TODO-backed placeholder is covered with a focused regression
  - untouched Vben/Uniapp outputs are protected by scope-guard expectations, not rewritten-behavior assertions

## Risks

1. Upstream template fidelity vs local framework wrappers:
   local abstractions may require adaptation rather than literal copying.
2. Over-expansion into backend parity:
   upstream frontend templates assume backend endpoints like export already exist, but backend is out of scope here.
   Mitigation: document export as a frontend contract alignment only; do not represent it as a backend change, and add a scope guard that backend generator assertions remain unchanged.
3. Regression in existing frontend-specific assertions:
   current tests may encode simplified local output assumptions.
4. Scope creep into untouched frontend targets:
   Vben or Uniapp may tempt broader cleanup because upstream templates are richer.
   Mitigation: only touch them when an emitted TODO-backed placeholder path is proven.

## Acceptance Criteria

1. No generated frontend file in the scoped renderers contains the current TODO placeholders.
2. Vue3 Element Plus generated API/index/form outputs reflect upstream CRUD/query/export/form patterns as far as frontend-only scope allows.
3. Any non-Vue3 frontend path that currently emits TODO placeholders is converted to concrete behavior and covered by regression tests.
4. Untouched Vben/Uniapp paths remain unchanged.
5. No backend generator, SQL mode default, or naming-rule changes are introduced.

## Verification Plan

1. Targeted renderer tests for each frontend family.
2. Full `uv run pytest`.
3. Diff review against upstream template semantics for at least one representative affected table/output family.
4. Manual spot check of generated outputs for a representative table:
   - API
   - index/list page
   - form page
5. Scope review confirming no non-TODO frontend targets were rewritten without evidence.

## Available Agent Types Roster

- `executor`: implementation lane for scaffold/template changes
- `architect`: source-of-truth reconciliation against upstream templates
- `critic`: plan and scope enforcement
- `test-engineer`: regression test design and coverage review
- `verifier`: completion evidence and final verification
- `explore`: fast mapping of local TODO-backed renderers to upstream template sections

## Suggested Reasoning Levels By Lane

- Upstream mapping / architecture lane: `high`
- Implementation lane: `medium` to `high`
- Test lane: `medium`
- Verification lane: `high`

## Staffing Guidance

### If executed via `ralph`

- Single-owner sequential flow:
  1. map renderer gaps to upstream templates
  2. implement Vue3 alignment
  3. implement only proven non-Vue3 TODO-backed output fixes if they exist
  4. add tests
  5. run verification and fix fallout

### If executed via `team`

- Lane 1: Vue3 Element Plus API/index/form alignment
- Lane 2: only proven non-Vue3 TODO-backed output fixes
- Lane 3: regression tests and verification harness
- Leader responsibility: prevent scope creep into backend/SQL/naming changes

## Launch Hints

- `ralph` path:
  - use this PRD plus the companion test spec as the execution brief
  - keep execution strictly inside frontend renderers and tests
- `team` path:
  - split write scopes to avoid overlap:
    - Lane 1: Vue3 renderer sections in `scaffold.py`
    - Lane 2: only the non-Vue3 renderer sections shown to emit TODO-backed placeholders
    - Lane 3: `tests/test_mcp_tools.py`

## Team Verification Path

1. Each lane submits concrete generated-output evidence, not only code diffs.
2. Shared verification pass runs targeted tests first, then full pytest.
3. Leader checks that no touched files outside frontend renderers/tests introduced backend or SQL behavior changes.
4. Final verifier confirms acceptance criteria item-by-item before completion.
