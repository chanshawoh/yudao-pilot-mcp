---
name: yudao-pilot-mcp
description: Use when working on a yudao / ruoyi-vue-pro project and the user wants AI-assisted code generation, project detection, database config discovery, table schema inspection, menu/dict SQL generation, or safe writing of generated backend/frontend files through the Yudao Pilot MCP server.
---

# Yudao Pilot MCP

Use this skill before calling the Yudao Pilot MCP server or when deciding whether the MCP is appropriate.

## When To Use

Use Yudao Pilot MCP when the user is in a yudao / ruoyi-vue-pro workspace and asks to:

- detect backend/frontend project layout
- initialize or inspect `./.yudao-pilot/config.yaml`
- resolve local database settings from yudao backend config
- inspect a MySQL table schema for code generation
- infer module/business/entity routing for a table
- generate backend/frontend scaffold files for yudao codegen
- generate menu/dict SQL and H2 test SQL
- safely write generated files into configured backend/frontend projects

Do not use it for general coding, arbitrary refactors, UI-only edits unrelated to yudao codegen, or when the user has not asked for yudao project-aware generation.

## MCP Server Location

Development checkout:

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/woodynew/.codex/worktrees/1583/yudao-pilot-mcp",
        "run",
        "yudao-pilot"
      ]
    }
  }
}
```

Installed user environment:

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "yudao-pilot",
      "args": []
    }
  }
}
```

If the current MCP client has no `yudao-pilot` server configured, add it to the MCP client config first. Prefer the installed `yudao-pilot` command in normal user environments; use the development checkout path only for local development of this MCP package.

## Required Workflow

1. Treat the MCP client's current project root as the workspace root.
2. Call `load_workspace_config` first.
3. If the response has `error_code=config_initialized`, stop the current generation flow. Tell the user the YAML was created, list the detected backend/frontend paths from `config_summary`, and ask whether to continue or stop so they can manually review/edit `./.yudao-pilot/config.yaml`.
4. If config exists, call `validate_workspace_projects`.
5. For code generation, call `inspect_codegen_context` before generating files.
6. If table schema is unresolved, stop and follow the MCP response: create/provide migration SQL or fix DB config before continuing.
7. Preview generated output with `generate_codegen_scaffold(write_files=false)` unless the user explicitly requested direct writing.
8. Only call write-enabled tools (`generate_codegen_scaffold(write_files=true)`, `generate_codegen_sql(write_files=true)`, `write_generated_files`, `write_mysql_migration`) when the target paths and generated content are clear.

## Boundaries And Safety

- Respect `./.yudao-pilot/config.yaml` as the routing source of truth.
- Do not guess backend/frontend paths by directory names alone; rely on MCP project detection and validation.
- For aggregator Maven modules with `packaging=pom`, do not write Java code into the aggregator itself. Use the MCP-generated backend target, which may select an existing child jar module or propose a new child module path.
- Do not write menu/dict SQL to a real database unless `codegen.apply_to_database=true`.
- If MCP returns `should_stop=true`, pause the current generation and report the requested user decision.
- If generated target paths look wrong, stop and inspect `resolved_from_config`, `backend_project.codegen_target`, and `generated_file_plan` before writing.

## Common Tool Order

For a typical table codegen request:

```text
load_workspace_config
validate_workspace_projects
resolve_database_config
inspect_codegen_context(table_name)
generate_codegen_sql(table_name, write_files=false)
generate_codegen_scaffold(table_name, write_files=false)
generate_codegen_sql(table_name, write_files=true)        # only after confirmation
generate_codegen_scaffold(table_name, write_files=true)   # only after confirmation
```

Use `inspect_project_path` when the user asks whether a specific path is a supported yudao backend/frontend project.
