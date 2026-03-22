from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from .codegen import (
    build_codegen_context,
    compare_codegen_reference_projects,
    write_mysql_migration,
)
from .config import (
    WorkspaceConfig,
    init_workspace_config,
    load_workspace_config,
    load_workspace_config_file,
)
from .database import resolve_database_config
from .database import apply_menu_plan_to_database, apply_dict_plan_to_database
from .models import GeneratedFile, TableResolution
from .inspector import inspect_project_path, scan_backend_table_entities, validate_workspace_projects
from .schema import extract_dict_fields, inspect_table_schema
from .scaffold import generate_scaffold_files
from .sql_codegen import build_codegen_sql_bundle, write_codegen_sql_bundle
from .writer import write_generated_files


mcp = FastMCP("Yudao Pilot")


def get_workspace_root(workspace_root: str | None = None) -> Path:
    return Path(workspace_root).expanduser().resolve() if workspace_root else Path.cwd().resolve()


def load_validated_config(workspace_root: str | None = None) -> tuple[Path, WorkspaceConfig]:
    root = get_workspace_root(workspace_root)
    config = load_workspace_config(root)
    return root, config


def get_reference_projects_root() -> Path:
    return Path.cwd().resolve() / "yudao-projects"


def success_response(message: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "error_code": None,
        "message": message,
        "data": data,
    }


def error_response(
    error_code: str, message: str, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": error_code,
        "message": message,
        "data": data or {},
    }


def _describe_menu_apply_skip(menu_mode: str, menu_plan: dict[str, Any]) -> str:
    if menu_plan.get("disabled"):
        return "菜单 SQL 已在配置中禁用，跳过写库"
    if menu_mode == "migration_only":
        return "菜单为 migration_only 模式，仅迁移文件、不写库"
    if menu_plan.get("all_menus_exist"):
        return "所有菜单已存在，跳过菜单写库"
    return "跳过菜单写库"


def _describe_dict_apply_skip(dict_mode: str, dict_plan: dict[str, Any]) -> str:
    if dict_plan.get("disabled"):
        return "字典 SQL 已在配置中禁用"
    if dict_mode == "migration_only":
        return "字典为 migration_only 模式，仅迁移文件、不写库"
    if not dict_plan.get("has_dicts"):
        return "未检测到需生成的字典数据"
    return "跳过字典写库"


def _describe_sql_apply_skip(
    menu_mode: str,
    dict_mode: str,
    menu_plan: dict[str, Any],
    dict_plan: dict[str, Any],
) -> str:
    parts = [
        _describe_menu_apply_skip(menu_mode, menu_plan),
        _describe_dict_apply_skip(dict_mode, dict_plan),
    ]
    return "；".join(parts)


def load_config_or_error(
    workspace_root: str | None = None,
) -> tuple[Path, WorkspaceConfig] | dict[str, Any]:
    root = get_workspace_root(workspace_root)
    config_file = load_workspace_config_file(root)
    if not config_file.exists:
        return error_response(
            "config_missing",
            "工作区配置不存在，请先初始化 ./.yudao-pilot/config.yaml",
            {
                "workspace_root": str(root),
                "config": config_file.model_dump(),
            },
        )
    try:
        config = load_workspace_config(root)
    except ValidationError as exc:
        return error_response(
            "config_invalid",
            "工作区配置校验失败",
            {
                "workspace_root": str(root),
                "errors": exc.errors(),
                "config_path": config_file.path,
            },
        )
    except FileNotFoundError:
        return error_response(
            "config_missing",
            "工作区配置不存在，请先初始化 ./.yudao-pilot/config.yaml",
            {
                "workspace_root": str(root),
                "config": config_file.model_dump(),
            },
        )
    return root, config


@mcp.tool
def load_workspace_config_tool(workspace_root: str | None = None) -> dict[str, Any]:
    """加载当前工作区配置；如果配置文件不存在，则返回初始化模板。"""
    root = get_workspace_root(workspace_root)
    config_file = load_workspace_config_file(root)
    if not config_file.exists:
        return error_response(
            "config_missing",
            "工作区配置不存在，请先初始化 ./.yudao-pilot/config.yaml",
            {
                "workspace_root": str(root),
                "config": config_file.model_dump(),
            },
        )
    return success_response(
        "工作区配置加载成功",
        {
            "workspace_root": str(root),
            "config": config_file.model_dump(),
        },
    )


@mcp.tool
def init_workspace_config_tool(
    workspace_root: str | None = None, overwrite: bool = False
) -> dict[str, Any]:
    """初始化当前工作区配置文件。"""
    root = get_workspace_root(workspace_root)
    config_file = init_workspace_config(root, overwrite=overwrite)
    return success_response(
        "工作区配置模板已生成",
        {
            "workspace_root": str(root),
            "config": config_file.model_dump(),
        },
    )


@mcp.tool
def inspect_project_path_tool(project_path: str) -> dict[str, Any]:
    """根据 pom.xml 或 package.json 的依赖指纹分析项目类型，不依赖目录名。"""
    result = inspect_project_path(project_path)
    if not result["exists"]:
        return error_response("project_path_not_found", "项目路径不存在", result)
    if result["best_match"]["supported"]:
        return success_response("项目类型识别成功", result)
    return error_response("project_not_supported", "项目未识别为受支持类型", result)


@mcp.tool
def compare_codegen_reference_projects_tool() -> dict[str, Any]:
    """比较 ruoyi-vue-pro 与 ruoyi-vue-pro-jdk17 的代码生成核心实现差异。"""
    reference_root = get_reference_projects_root()
    result = compare_codegen_reference_projects(reference_root)
    return success_response("参考项目代码生成差异分析完成", result)


@mcp.tool
def validate_workspace_projects_tool(workspace_root: str | None = None) -> dict[str, Any]:
    """校验工作区中的后端和前端项目是否与配置严格匹配。"""
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    result = validate_workspace_projects(root, config)
    if result["ok"]:
        return success_response("项目校验成功", result)
    return error_response("workspace_project_validation_failed", "项目校验失败", result)


@mcp.tool
def resolve_database_config_tool(workspace_root: str | None = None) -> dict[str, Any]:
    """解析数据库配置，优先遵循工作区 config，其次从后端本地配置中读取。"""
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    result = resolve_database_config(root, config)
    result["workspace_root"] = str(root)
    if result["ok"]:
        return success_response(result["message"], result)
    return error_response("database_config_unresolved", result["message"], result)


@mcp.tool
def infer_codegen_plan_tool(table_name: str, workspace_root: str | None = None) -> dict[str, Any]:
    """根据工作区配置推导表对应的模块、业务名、实体名和生成目标。"""
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    backend_root = (root / config.projects.backend.path).resolve()
    resolution = infer_table_resolution(table_name, config, backend_root=backend_root)

    return success_response(
        "生成规划推导成功",
        {
            "workspace_root": str(root),
            "table_name": table_name,
            "routing_mode": config.codegen.routing.mode,
            "resolution": resolution.model_dump(),
            "backend": {
                "type": config.projects.backend.type,
                "path": str((root / config.projects.backend.path).resolve()),
            },
            "frontends": [
                {
                    "type": frontend.type,
                    "path": str((root / frontend.path).resolve()),
                }
                for frontend in config.projects.frontend
            ],
        },
    )


@mcp.tool
def inspect_codegen_context_tool(
    table_name: str,
    workspace_root: str | None = None,
    module_name: str | None = None,
    business_name: str | None = None,
    entity_name: str | None = None,
    menu_name: str | None = None,
    parent_menu_name: str | None = None,
    parent_menu_id: int | None = None,
) -> dict[str, Any]:
    """结合配置规则、后端默认配置和 SQL 菜单数据，构建生成代码所需上下文。"""
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    backend_root = (root / config.projects.backend.path).resolve()
    resolution = infer_table_resolution(table_name, config, backend_root=backend_root)
    context = build_codegen_context(
        root,
        config,
        table_name,
        module_name=module_name or resolution.module,
        business_name=business_name or resolution.business,
        entity_name=entity_name or resolution.entity,
        menu_name=menu_name,
        parent_menu_name=parent_menu_name,
        parent_menu_id=parent_menu_id,
    )
    context["workspace_root"] = str(root)
    context["resolved_from_config"] = resolution.model_dump()
    return success_response("代码生成上下文分析完成", context)


@mcp.tool
def inspect_table_schema_tool(
    table_name: str, workspace_root: str | None = None
) -> dict[str, Any]:
    """优先从后端仓库 SQL 结构文件解析字段，缺失时回退到真实数据库。"""
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    backend_root = (root / config.projects.backend.path).resolve()
    database_result = resolve_database_config(root, config)
    result = inspect_table_schema(
        backend_root,
        table_name,
        database_result["database"] if database_result.get("ok") else None,
    )
    result["workspace_root"] = str(root)
    if result["resolved"]:
        return success_response("表结构解析成功", result)
    return error_response("table_schema_unresolved", result["message"], result)


@mcp.tool
def generate_codegen_scaffold_tool(
    table_name: str,
    workspace_root: str | None = None,
    module_name: str | None = None,
    business_name: str | None = None,
    entity_name: str | None = None,
    menu_name: str | None = None,
    parent_menu_name: str | None = None,
    parent_menu_id: int | None = None,
    include_backend: bool = True,
    include_frontend: bool = True,
    write_files: bool = False,
    overwrite: bool = True,
    field_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """根据当前上下文直接生成首版代码骨架，可选择只预览或直接写入工作区。

    field_overrides: AI 覆盖字段组件类型，格式为 {"java_field": "html_type"}，
    例如 {"lng": "inputNumber", "lat": "inputNumber"}。
    可用 html_type 值: input, inputNumber, textarea, editor, select, radio,
    checkbox, datetime, date, imageUpload, fileUpload。
    """
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    backend_root = (root / config.projects.backend.path).resolve()
    resolution = infer_table_resolution(table_name, config, backend_root=backend_root)
    context = build_codegen_context(
        root,
        config,
        table_name,
        module_name=module_name or resolution.module,
        business_name=business_name or resolution.business,
        entity_name=entity_name or resolution.entity,
        menu_name=menu_name,
        parent_menu_name=parent_menu_name,
        parent_menu_id=parent_menu_id,
    )
    if field_overrides:
        _apply_field_overrides(context, field_overrides)
    _attach_generated_dict_types(context)
    generated_files = generate_scaffold_files(
        context,
        overwrite=overwrite,
        include_backend=include_backend,
        include_frontend=include_frontend,
    )
    result: dict[str, Any] = {
        "workspace_root": str(root),
        "table_name": table_name,
        "resolved_from_config": resolution.model_dump(),
        "context": context,
        "generated_files": [file.model_dump() for file in generated_files],
    }
    if write_files:
        write_result = write_generated_files(root, config, generated_files)
        write_result["workspace_root"] = str(root)
        result["write_result"] = write_result
        if write_result["ok"]:
            return success_response("代码骨架已生成并写入工作区", result)
        return error_response("generate_codegen_scaffold_failed", "代码骨架生成成功，但写入存在失败项", result)
    return success_response("代码骨架生成成功", result)


@mcp.tool
def write_generated_files_tool(
    files: list[dict[str, Any]], workspace_root: str | None = None
) -> dict[str, Any]:
    """将 AI 应用生成的文件安全写入到配置指定的后端或前端项目中。"""
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    try:
        generated_files = [GeneratedFile.model_validate(item) for item in files]
    except ValidationError as exc:
        return error_response(
            "generated_files_invalid",
            "生成文件参数校验失败",
            {
                "workspace_root": str(root),
                "errors": exc.errors(),
            },
        )
    result = write_generated_files(root, config, generated_files)
    result["workspace_root"] = str(root)
    if result["ok"]:
        return success_response("生成文件写入成功", result)
    return error_response("write_generated_files_failed", "生成文件写入存在失败项", result)


@mcp.tool
def write_mysql_migration_tool(
    migration_name: str,
    sql_content: str,
    workspace_root: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """将新的 SQL 结构以 Laravel 风格文件名写入 sql/mysql/migrations 目录。"""
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    backend_root = (root / config.projects.backend.path).resolve()
    result = write_mysql_migration(
        backend_root,
        migration_name,
        sql_content,
        overwrite=overwrite,
    )
    result["workspace_root"] = str(root)
    if result["ok"]:
        return success_response("SQL 迁移文件写入成功", result)
    return error_response("write_mysql_migration_failed", result["message"], result)


@mcp.tool
def generate_codegen_sql_tool(
    table_name: str,
    workspace_root: str | None = None,
    module_name: str | None = None,
    business_name: str | None = None,
    entity_name: str | None = None,
    menu_name: str | None = None,
    module_menu_name: str | None = None,
    menu_icon: str | None = None,
    module_menu_icon: str | None = None,
    parent_menu_name: str | None = None,
    parent_menu_id: int | None = None,
    write_files: bool = False,
    overwrite: bool = False,
    apply_menu_to_database: bool = False,
) -> dict[str, Any]:
    """生成 MySQL 菜单 SQL 与模块 H2 测试 SQL，可选直接写入文件并执行菜单数据。

    菜单/字典是否生成、是否允许写库由工作区配置 codegen.menu_sql_mode、codegen.dict_sql_mode 控制：
    auto（默认）= 生成 SQL，write_files 写迁移；apply_menu_to_database 时可写库；
    migration_only = 生成 SQL 并可写迁移文件，但永不写库；
    disabled = 不生成对应 SQL（不写迁移中的该段）。
    """
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    backend_root = (root / config.projects.backend.path).resolve()
    resolution = infer_table_resolution(table_name, config, backend_root=backend_root)
    context = build_codegen_context(
        root,
        config,
        table_name,
        module_name=module_name or resolution.module,
        business_name=business_name or resolution.business,
        entity_name=entity_name or resolution.entity,
        menu_name=menu_name,
        parent_menu_name=parent_menu_name,
        parent_menu_id=parent_menu_id,
    )
    sql_bundle = build_codegen_sql_bundle(
        context,
        module_menu_name=module_menu_name,
        menu_name=menu_name,
        menu_icon=menu_icon,
        module_menu_icon=module_menu_icon,
    )
    result: dict[str, Any] = {
        "workspace_root": str(root),
        "table_name": table_name,
        "resolved_from_config": resolution.model_dump(),
        "context": context,
        "sql_bundle": sql_bundle,
    }
    if not sql_bundle.get("ok"):
        return error_response("generate_codegen_sql_failed", sql_bundle["message"], result)

    if write_files:
        write_result = write_codegen_sql_bundle(sql_bundle, overwrite=overwrite)
        write_result["workspace_root"] = str(root)
        result["write_result"] = write_result
        if not write_result["ok"]:
            return error_response(
                "generate_codegen_sql_write_failed",
                "SQL 已生成，但写入文件时存在失败项",
                result,
            )

    if apply_menu_to_database:
        codegen_sql = context.get("codegen_sql", {})
        menu_mode = str(codegen_sql.get("menu_mode") or "auto")
        dict_mode = str(codegen_sql.get("dict_mode") or "auto")
        menu_plan = sql_bundle.get("menu_plan", {})
        dict_plan = sql_bundle.get("dict_plan", {})

        apply_menu_allowed = menu_mode == "auto" and not menu_plan.get("disabled")
        apply_dict_allowed = dict_mode == "auto" and not dict_plan.get("disabled")

        menu_needs_db = apply_menu_allowed and not menu_plan.get("all_menus_exist", False)
        dict_needs_db = (
            apply_dict_allowed
            and bool(dict_plan.get("has_dicts"))
            and not bool(dict_plan.get("all_complete", False))
        )

        if not menu_needs_db and not dict_needs_db:
            result["apply_result"] = {
                "ok": True,
                "skipped_reason": "no_database_apply_needed",
                "codegen_sql_modes": {"menu": menu_mode, "dict": dict_mode},
                "message": _describe_sql_apply_skip(
                    menu_mode, dict_mode, menu_plan, dict_plan
                ),
            }
            return success_response("无需向数据库写入菜单或字典", result)

        database_result = resolve_database_config(root, config)
        result["database"] = database_result
        if not database_result.get("ok"):
            return error_response(
                "database_config_unresolved",
                database_result["message"],
                result,
            )

        if menu_needs_db:
            result["apply_result"] = apply_menu_plan_to_database(
                database_result["database"],
                menu_plan,
            )
        else:
            result["apply_result"] = {
                "ok": True,
                "skipped_reason": "menu_skipped",
                "codegen_sql_modes": {"menu": menu_mode, "dict": dict_mode},
                "message": _describe_menu_apply_skip(menu_mode, menu_plan),
            }

        if dict_needs_db:
            result["dict_apply_result"] = apply_dict_plan_to_database(
                database_result["database"],
                dict_plan,
            )
        elif dict_plan.get("has_dicts"):
            result["dict_apply_result"] = {
                "ok": True,
                "skipped_reason": "all_dicts_complete",
                "codegen_sql_modes": {"menu": menu_mode, "dict": dict_mode},
                "message": "所有字典数据已存在且完整，跳过字典创建",
            }
        else:
            result["dict_apply_result"] = {
                "ok": True,
                "skipped_reason": "dict_skipped",
                "codegen_sql_modes": {"menu": menu_mode, "dict": dict_mode},
                "message": _describe_dict_apply_skip(dict_mode, dict_plan),
            }

    return success_response("代码生成 SQL 已准备完成", result)


def infer_table_resolution(
    table_name: str,
    config: WorkspaceConfig,
    *,
    backend_root: Path | None = None,
) -> TableResolution:
    # 1) manual_rules exact match
    if config.codegen.manual_rules:
        for manual_rule in config.codegen.manual_rules:
            for table_rule in manual_rule.table_rules:
                if table_rule.table == table_name:
                    return TableResolution(
                        module=manual_rule.module,
                        matched_by="exact",
                        matched_table=table_rule.table,
                        business=table_rule.business,
                        entity=table_rule.entity,
                    )

        # 2) manual_rules prefix match
        matched_prefix: str | None = None
        prefix_module: str | None = None
        for manual_rule in config.codegen.manual_rules:
            for prefix in manual_rule.table_prefixes:
                if table_name == prefix or table_name.startswith(f"{prefix}_"):
                    matched_prefix = prefix
                    prefix_module = manual_rule.module
                    break
            if matched_prefix:
                break

        if matched_prefix and prefix_module:
            return TableResolution(
                module=prefix_module,
                matched_by="prefix",
                matched_prefix=matched_prefix,
                business=matched_prefix,
                entity=snake_to_pascal(table_name),
            )

    # 3) scan existing DO entities in backend modules
    if backend_root:
        scan_result = _resolve_by_scan(table_name, backend_root)
        if scan_result:
            return scan_result

    # 4) fallback: derive module from first segment, may trigger new module
    inferred_module = table_name.split("_", 1)[0] if "_" in table_name else table_name
    if backend_root:
        module_dir = backend_root / f"yudao-module-{inferred_module}"
        if module_dir.is_dir():
            _ensure_module_enabled(backend_root, inferred_module)
            return TableResolution(
                module=inferred_module,
                matched_by="new_module",
                business=table_name,
                entity=snake_to_pascal(table_name),
            )
        _create_module_scaffold(backend_root, inferred_module)
        _ensure_module_enabled(backend_root, inferred_module)
        return TableResolution(
            module=inferred_module,
            matched_by="new_module",
            business=table_name,
            entity=snake_to_pascal(table_name),
        )

    return TableResolution(
        module=inferred_module,
        matched_by="fallback",
        business=table_name,
        entity=snake_to_pascal(table_name),
    )


def _resolve_by_scan(table_name: str, backend_root: Path) -> TableResolution | None:
    """Find the best matching existing DO table by longest prefix."""
    entities = scan_backend_table_entities(backend_root)
    best_match = None
    best_len = 0
    for entity in entities:
        existing = entity.table_name
        if table_name == existing:
            return TableResolution(
                module=entity.module_name,
                matched_by="scan",
                matched_table=existing,
                business=entity.business_dir,
                entity=snake_to_pascal(table_name),
            )
        if table_name.startswith(f"{existing}_") and len(existing) > best_len:
            best_match = entity
            best_len = len(existing)
    if best_match:
        return TableResolution(
            module=best_match.module_name,
            matched_by="scan",
            matched_prefix=best_match.table_name,
            business=best_match.business_dir,
            entity=snake_to_pascal(table_name),
        )
    return None



def _ensure_module_enabled(backend_root: Path, module_name: str) -> None:
    """Uncomment or add module in root pom.xml and yudao-server/pom.xml."""
    artifact = f"yudao-module-{module_name}"
    _enable_in_root_pom(backend_root / "pom.xml", artifact)
    _enable_in_server_pom(backend_root / "yudao-server" / "pom.xml", artifact)


def _enable_in_root_pom(pom_path: Path, artifact: str) -> None:
    if not pom_path.exists():
        return
    text = pom_path.read_text(encoding="utf-8")
    module_tag = f"<module>{artifact}</module>"
    commented = f"<!--        <module>{artifact}</module>-->"
    alt_commented = f"<!--<module>{artifact}</module>-->"

    if module_tag in text and commented not in text and alt_commented not in text:
        return

    for pattern in [commented, alt_commented]:
        if pattern in text:
            text = text.replace(pattern, f"        {module_tag}")
            pom_path.write_text(text, encoding="utf-8")
            return

    insert_marker = "</modules>"
    if insert_marker in text:
        text = text.replace(insert_marker, f"        {module_tag}\n    {insert_marker}")
        pom_path.write_text(text, encoding="utf-8")


def _enable_in_server_pom(pom_path: Path, artifact: str) -> None:
    if not pom_path.exists():
        return
    text = pom_path.read_text(encoding="utf-8")

    dep_block = (
        f"<dependency>\n"
        f"            <groupId>cn.iocoder.boot</groupId>\n"
        f"            <artifactId>{artifact}</artifactId>\n"
        f"            <version>${{revision}}</version>\n"
        f"        </dependency>"
    )

    if f"<artifactId>{artifact}</artifactId>" in text:
        commented_pattern = re.compile(
            r"<!--\s*<dependency>\s*.*?"
            + re.escape(f"<artifactId>{artifact}</artifactId>")
            + r".*?</dependency>\s*-->",
            re.DOTALL,
        )
        match = commented_pattern.search(text)
        if match:
            text = text[:match.start()] + f"        {dep_block}" + text[match.end():]
            pom_path.write_text(text, encoding="utf-8")
        return

    insert_marker = "</dependencies>"
    if insert_marker in text:
        text = text.replace(
            insert_marker,
            f"\n        {dep_block}\n\n    {insert_marker}",
            1,
        )
        pom_path.write_text(text, encoding="utf-8")


def _attach_generated_dict_types(context: dict[str, Any]) -> None:
    """Detect dict-like columns and attach generated_dict_type to each column."""
    table_schema = context.get("table_schema") or {}
    columns = table_schema.get("columns") or []
    table_name = context.get("table_name", "")
    table_comment = str(table_schema.get("table_comment") or table_name)
    dict_fields = extract_dict_fields(columns, table_name, table_comment)
    if not dict_fields:
        return
    dict_map = {df["column_name"]: df for df in dict_fields}
    for col in columns:
        df = dict_map.get(col["column_name"])
        if df:
            col["generated_dict_type"] = df["dict_type"]
            col["generated_dict_name"] = df["dict_name"]
            col["generated_dict_items"] = df["items"]


def _apply_field_overrides(context: dict[str, Any], overrides: dict[str, str]) -> None:
    """Apply AI-provided html_type overrides to table schema columns."""
    columns = context.get("table_schema", {}).get("columns", [])
    for col in columns:
        new_html_type = overrides.get(col.get("java_field", ""))
        if new_html_type:
            col["html_type"] = new_html_type


def _create_module_scaffold(backend_root: Path, module_name: str) -> None:
    """Create a minimal module directory with pom.xml and standard package layout."""
    module_root = backend_root / f"yudao-module-{module_name}"
    module_root.mkdir(parents=True, exist_ok=True)

    pkg_base = module_root / "src" / "main" / "java" / "cn" / "iocoder" / "yudao" / "module" / module_name
    for sub in [
        "controller/admin",
        "dal/dataobject",
        "dal/mysql",
        "service",
        "enums",
    ]:
        (pkg_base / sub).mkdir(parents=True, exist_ok=True)

    (module_root / "src" / "main" / "resources" / "mapper").mkdir(parents=True, exist_ok=True)

    test_sql_dir = module_root / "src" / "test" / "resources" / "sql"
    test_sql_dir.mkdir(parents=True, exist_ok=True)
    for sql_file in ["create_tables.sql", "clean.sql"]:
        sql_path = test_sql_dir / sql_file
        if not sql_path.exists():
            sql_path.write_text("", encoding="utf-8")

    error_code_path = pkg_base / "enums" / "ErrorCodeConstants.java"
    if not error_code_path.exists():
        error_code_path.write_text(
            f"package cn.iocoder.yudao.module.{module_name}.enums;\n\n"
            f"import cn.iocoder.yudao.framework.common.exception.ErrorCode;\n\n"
            f"public interface ErrorCodeConstants {{\n\n}}\n",
            encoding="utf-8",
        )

    pom_path = module_root / "pom.xml"
    if not pom_path.exists():
        pom_path.write_text(
            _render_module_pom(module_name),
            encoding="utf-8",
        )


def _render_module_pom(module_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<project xmlns="http://maven.apache.org/POM/4.0.0"\n'
        '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 '
        'http://maven.apache.org/xsd/maven-4.0.0.xsd">\n'
        "    <parent>\n"
        "        <groupId>cn.iocoder.boot</groupId>\n"
        "        <artifactId>yudao</artifactId>\n"
        "        <version>${revision}</version>\n"
        "    </parent>\n"
        "    <modelVersion>4.0.0</modelVersion>\n"
        f"    <artifactId>yudao-module-{module_name}</artifactId>\n"
        "    <packaging>jar</packaging>\n\n"
        "    <name>${project.artifactId}</name>\n"
        f"    <description>{module_name} 模块</description>\n\n"
        "    <dependencies>\n"
        "        <dependency>\n"
        "            <groupId>cn.iocoder.boot</groupId>\n"
        "            <artifactId>yudao-module-system</artifactId>\n"
        "            <version>${revision}</version>\n"
        "        </dependency>\n"
        "        <dependency>\n"
        "            <groupId>cn.iocoder.boot</groupId>\n"
        "            <artifactId>yudao-module-infra</artifactId>\n"
        "            <version>${revision}</version>\n"
        "        </dependency>\n\n"
        "        <dependency>\n"
        "            <groupId>cn.iocoder.boot</groupId>\n"
        "            <artifactId>yudao-spring-boot-starter-biz-tenant</artifactId>\n"
        "        </dependency>\n"
        "        <dependency>\n"
        "            <groupId>cn.iocoder.boot</groupId>\n"
        "            <artifactId>yudao-spring-boot-starter-security</artifactId>\n"
        "        </dependency>\n"
        "        <dependency>\n"
        "            <groupId>org.springframework.boot</groupId>\n"
        "            <artifactId>spring-boot-starter-validation</artifactId>\n"
        "        </dependency>\n\n"
        "        <dependency>\n"
        "            <groupId>cn.iocoder.boot</groupId>\n"
        "            <artifactId>yudao-spring-boot-starter-mybatis</artifactId>\n"
        "        </dependency>\n"
        "        <dependency>\n"
        "            <groupId>cn.iocoder.boot</groupId>\n"
        "            <artifactId>yudao-spring-boot-starter-redis</artifactId>\n"
        "        </dependency>\n\n"
        "        <dependency>\n"
        "            <groupId>cn.iocoder.boot</groupId>\n"
        "            <artifactId>yudao-spring-boot-starter-test</artifactId>\n"
        "            <scope>test</scope>\n"
        "        </dependency>\n"
        "        <dependency>\n"
        "            <groupId>cn.iocoder.boot</groupId>\n"
        "            <artifactId>yudao-spring-boot-starter-excel</artifactId>\n"
        "        </dependency>\n"
        "    </dependencies>\n\n"
        "</project>\n"
    )


def snake_to_pascal(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_") if part)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
