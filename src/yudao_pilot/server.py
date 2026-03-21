from __future__ import annotations

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
from .database import apply_menu_plan_to_database
from .models import GeneratedFile, TableResolution
from .inspector import inspect_project_path, validate_workspace_projects
from .schema import inspect_table_schema
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
    resolution = infer_table_resolution(table_name, config)

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
    resolution = infer_table_resolution(table_name, config)
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
) -> dict[str, Any]:
    """根据当前上下文直接生成首版代码骨架，可选择只预览或直接写入工作区。"""
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    resolution = infer_table_resolution(table_name, config)
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
    """生成 MySQL 菜单 SQL 与模块 H2 测试 SQL，可选直接写入文件并执行菜单数据。"""
    loaded = load_config_or_error(workspace_root)
    if isinstance(loaded, dict):
        return loaded
    root, config = loaded
    resolution = infer_table_resolution(table_name, config)
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
        database_result = resolve_database_config(root, config)
        result["database"] = database_result
        if not database_result.get("ok"):
            return error_response(
                "database_config_unresolved",
                database_result["message"],
                result,
            )
        apply_result = apply_menu_plan_to_database(
            database_result["database"],
            sql_bundle["menu_plan"],
        )
        result["apply_result"] = apply_result

    return success_response("代码生成 SQL 已准备完成", result)


def infer_table_resolution(table_name: str, config: WorkspaceConfig) -> TableResolution:
    if not config.codegen.manual_rules:
        inferred_module = table_name.split("_", 1)[0] if "_" in table_name else "system"
        return TableResolution(
            module=inferred_module,
            matched_by="fallback",
            business=table_name,
            entity=snake_to_pascal(table_name),
        )

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

    prefix_match: tuple[str, str] | None = None
    prefix_module: str | None = None
    for manual_rule in config.codegen.manual_rules:
        for prefix in manual_rule.table_prefixes:
            if table_name == prefix or table_name.startswith(f"{prefix}_"):
                prefix_match = (prefix, trim_prefix(table_name, prefix))
                prefix_module = manual_rule.module
                break
        if prefix_match:
            break

    if prefix_match and prefix_module:
        matched_prefix, business = prefix_match
        return TableResolution(
            module=prefix_module,
            matched_by="prefix",
            matched_prefix=matched_prefix,
            business=business,
            entity=snake_to_pascal(table_name),
        )

    first_rule = config.codegen.manual_rules[0]
    return TableResolution(
        module=first_rule.module,
        matched_by="fallback",
        business=table_name,
        entity=snake_to_pascal(table_name),
    )


def trim_prefix(table_name: str, prefix: str) -> str:
    if table_name == prefix:
        return prefix
    trimmed = table_name[len(prefix):].lstrip("_")
    return trimmed or prefix


def snake_to_pascal(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_") if part)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
