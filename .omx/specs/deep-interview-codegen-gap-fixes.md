# Deep Interview Spec: codegen-gap-fixes

## Metadata

- Profile: standard
- Context type: brownfield
- Final ambiguity: 6%
- Threshold: 20%
- Transcript: `.omx/interviews/codegen-gap-fixes-20260407T052950Z.md`
- Context snapshot: `.omx/context/codegen-gap-fixes-20260407T051911Z.md`

## Clarity Breakdown

| Dimension | Score |
| --- | ---: |
| Intent | 0.95 |
| Outcome | 0.93 |
| Scope | 0.95 |
| Constraints | 0.97 |
| Success Criteria | 0.85 |
| Brownfield Context | 0.94 |

## Intent

Make the generated frontend code production-usable by removing current TODO placeholders and filling the missing behavior using the original Yudao codegen templates as the authority, not by inventing new conventions.

## Desired Outcome

For the currently supported frontend generators, replace the remaining TODO-style placeholder behavior with concrete implementations that follow the existing `ruoyi-vue-pro-jdk17` infra codegen templates as closely as practical in this repository.

## In Scope

- Frontend-side TODO completion only.
- Use the original Yudao codegen source as the functional reference:
  - `yudao-projects/ruoyi-vue-pro-jdk17/yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/controller/admin/codegen`
  - `yudao-projects/ruoyi-vue-pro-jdk17/yudao-module-infra/src/main/resources/codegen`
- Cover the frontend targets currently supported by this repo where TODO placeholders remain:
  - Vue3 Element Plus
  - Vben variants
  - Uniapp variant
- Align generated frontend CRUD/query/export/form behavior to the reference templates as closely as possible.

## Out of Scope / Non-goals

- Do not change backend generation behavior in this round.
- Do not add or modify backend export endpoints in this round.
- Do not change menu/dict SQL default generation or database-apply behavior in this round.
- Do not change naming conventions beyond what is already implied by the original reference templates.
- Do not pursue earlier tentative naming-rule changes from this interview; they are superseded.
- Do not redesign page visuals or introduce new UX patterns unrelated to matching the reference behavior.

## Decision Boundaries

- When current local generator behavior conflicts with earlier conversational guesses, prefer the original Java/template logic.
- OMX may adapt paths or implementation details only where strictly necessary to fit this repository’s existing multi-frontend structure.
- OMX should not introduce new conventions unless the reference behavior cannot be represented otherwise.

## Constraints

- Original Java/codegen templates are the source of truth.
- Preserve current repository support for multiple frontend targets.
- Keep changes focused on replacing TODO placeholders with real behavior.
- Avoid unrelated generator refactors.

## Testable Acceptance Criteria

1. Generated frontend files no longer contain the current TODO placeholders that block CRUD usage.
2. Generated frontend list/index pages wire query/list/reset/create/delete/export behavior in line with the reference templates for the corresponding frontend family.
3. Generated frontend form pages wire create/update fetching/submission/reset behavior in line with the reference templates for the corresponding frontend family.
4. Existing non-frontend generator behavior remains unchanged unless required by a frontend-template dependency.
5. Regression tests cover the previously TODO-backed frontend outputs.

## Assumptions Exposed + Resolutions

- Assumption: the task included backend export/controller and menu SQL default changes.
  Resolution: rejected for this round; frontend TODO completion only.
- Assumption: earlier custom naming rules should drive this work.
  Resolution: rejected; original Java/template behavior takes precedence.

## Brownfield Evidence vs Inference

### Evidence

- `src/yudao_pilot/scaffold.py` still contains frontend TODO placeholders in generated Vue3 outputs.
- `yudao-module-infra` reference templates already implement concrete frontend CRUD/query/export/form behavior.
- The reference `controller.vm` already includes export endpoint logic, but user narrowed current scope away from backend changes.

### Inference

- Some adaptation will still be necessary because this repo supports multiple frontend targets beyond the single upstream template structure.

## Execution Bridge

Recommended next handoff: `$ralplan` using this spec as the requirements source of truth, then execute only the approved frontend-template work.
