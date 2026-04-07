# Context Snapshot: codegen-sql-naming

- Task statement:
  Adjust menu/dict SQL default behavior and preserve original Java codegen naming precedence.
- Desired outcome:
  Menu/dict migration SQL still generates by default, but database execution is controlled by a new top-priority workspace config switch; `apply_menu_to_database` logic is removed; docs/tests updated.
- Known facts/evidence:
  `src/yudao_pilot/config.py` still defaults `menu_sql_mode` and `dict_sql_mode` to `auto`.
  `src/yudao_pilot/server.py` still exposes and uses `apply_menu_to_database`.
  `README.md` still documents parameter-driven DB apply and `auto` as the default write-capable mode.
  Naming logic still lives in `derive_business_name()` and `build_frontend_business_path()`.
- Constraints:
  Original Java codegen naming rules stay authoritative.
  New workspace config switch has highest priority.
  `apply_menu_to_database` logic should be removed, not merely deprecated in flow control.
  Code, tests, and README must be updated together.
- Unknowns/open questions:
  Exact config field name and whether it should live under `codegen`.
  Whether `menu_sql_mode` / `dict_sql_mode` semantics should become generation-only after the new switch.
- Likely codebase touchpoints:
  `src/yudao_pilot/config.py`
  `src/yudao_pilot/server.py`
  `src/yudao_pilot/sql_codegen.py`
  `src/yudao_pilot/codegen.py`
  `README.md`
  `tests/test_mcp_tools.py`
