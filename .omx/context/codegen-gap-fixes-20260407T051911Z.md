# Context Snapshot: codegen-gap-fixes

- Task statement:
  Continue fixing code generation gaps around controller export support, menu SQL apply defaults, backend/frontend naming rules, and incomplete frontend views.
- Desired outcome:
  An execution-ready clarification artifact that pins down scope, naming conventions, default write-to-database behavior, and how far generated frontend pages should go.
- Stated solution:
  Reference existing backend generation logic where needed and keep improving the generator.
- Probable intent hypothesis:
  The user wants generated code to be production-usable by default, match Yudao conventions, and avoid unsafe side effects like silently writing menu data to databases.
- Known facts/evidence:
  `render_controller()` currently generates CRUD/page only; no export endpoint.
  `render_controller()` now adds `@PreAuthorize` and Swagger annotations, but no export method yet.
  `CodegenConfig` currently defaults `menu_sql_mode` and `dict_sql_mode` to `auto`, and README documents `auto` as the default.
  `generate_codegen_sql_tool()` only writes menu/dict to DB when `apply_menu_to_database=true` and mode is `auto`, but the documented default still encourages auto-write capability.
  Backend file plan uses snake path segments from `business_name`, e.g. `controller/admin/{business_name}` and `dal/dataobject/{business_name}`.
  Frontend file plan also uses `frontend_business_path`, currently derived via `build_frontend_business_path()` and kept in snake/path form.
  Vue3 frontend templates still contain TODO placeholders like `继续接入查询条件、权限点和真实接口调用` and `接入 save API，并结合字段规则补齐校验`.
- Constraints:
  Existing generated outputs and tests already rely on current route and permission derivation conventions.
  The workspace now stops generation when table schema is unresolved.
  The user explicitly invoked `deep-interview`, so this turn should clarify, not implement.
- Unknowns/open questions:
  Whether the new backend business naming rule applies only to `system_*` tables or all modules.
  Whether frontend “小驼峰” means directory names, API file names, route segments, generated TS symbols, or all of them.
  Whether export endpoint should always be generated or only when table/list fields support Excel/export conventions.
  How complete frontend pages should become in this round: CRUD wiring only, or also search/form validation/dict rendering/export.
  Whether `dict_sql_mode` should also default away from auto-write, in addition to `menu_sql_mode`.
- Decision-boundary unknowns:
  Whether OMX may change default config values and README semantics without preserving backward compatibility.
  Whether OMX may restructure existing generated path conventions across backend and frontend beyond the stated examples.
- Likely codebase touchpoints:
  `src/yudao_pilot/scaffold.py`
  `src/yudao_pilot/codegen.py`
  `src/yudao_pilot/config.py`
  `src/yudao_pilot/server.py`
  `src/yudao_pilot/sql_codegen.py`
  `README.md`
