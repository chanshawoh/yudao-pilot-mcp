from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError
import yaml

from .codegen import (
    build_codegen_context,
    compare_codegen_reference_projects,
    normalize_snake_case,
    write_mysql_migration,
)
from .config import (
    UnsafeWorkspaceRootError,
    WorkspaceConfig,
    WorkspaceProjectsNotDetectedError,
    auto_init_workspace_config,
    is_unsafe_workspace_root,
    load_workspace_config,
    load_workspace_config_file,
)
from .database import (
    resolve_database_config,
    apply_menu_plan_to_database,
    apply_dict_plan_to_database,
    load_dict_catalog_from_database,
)
from .models import GeneratedFile, TableResolution
from .inspector import discover_workspace_projects, inspect_project_path, scan_backend_table_entities, validate_workspace_projects
from .schema import extract_dict_fields, inspect_table_schema
from .scaffold import generate_scaffold_files
from .sql_codegen import build_codegen_sql_bundle, build_dict_plan, write_codegen_sql_bundle
from .writer import write_generated_files, write_preview_generated_files


mcp = FastMCP("Yudao Pilot")


def get_workspace_root(workspace_root: str | None = None) -> Path:
    return Path(workspace_root).expanduser().resolve() if workspace_root else Path.cwd().resolve()


def get_safe_workspace_root_or_error(workspace_root: str | None = None) -> Path | dict[str, Any]:
    root = get_workspace_root(workspace_root)
    if is_unsafe_workspace_root(root):
        return workspace_root_required_response(root, explicit=workspace_root is not None)
    return root


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


def workspace_root_required_response(root: Path, *, explicit: bool) -> dict[str, Any]:
    if explicit:
        message = "workspace_root 指向过宽目录，已停止初始化 ./.yudao-pilot/config.yaml。"
        prompt = (
            "用户传入的 workspace_root 是文件系统根目录或用户 Home 目录，不能在这里初始化配置。"
            "请询问用户真实的项目工作目录绝对路径，并使用该路径作为 workspace_root 参数重新调用 MCP 工具。"
        )
    else:
        message = "无法确认用户项目工作目录，已停止初始化 ./.yudao-pilot/config.yaml。"
        prompt = (
            "当前 MCP 服务的进程工作目录是文件系统根目录或用户 Home 目录，不能据此判断用户项目位置。"
            "请先询问用户真实的项目工作目录绝对路径，然后把该路径作为 workspace_root 参数重新调用 MCP 工具。"
        )
    return error_response(
        "workspace_root_required",
        message,
        {
            "workspace_root": str(root),
            "initialized": False,
            "should_stop": True,
            "next_action_prompt": prompt,
        },
    )


def workspace_projects_not_detected_response(root: Path) -> dict[str, Any]:
    return error_response(
        "workspace_root_required",
        "未在当前目录识别到受支持的 yudao 后端或前端项目，已停止初始化 ./.yudao-pilot/config.yaml。",
        {
            "workspace_root": str(root),
            "initialized": False,
            "should_stop": True,
            "detected_projects": {"backend": None, "frontend": []},
            "next_action_prompt": (
                "当前目录下没有识别到受支持的 yudao 后端或前端项目，不能确认这是用户项目工作区。"
                "请询问用户真实的项目工作目录绝对路径，并使用该路径作为 workspace_root 参数重新调用 MCP 工具。"
            ),
        },
    )


def stop_response_from_schema(
    table_schema: dict[str, Any],
    data: dict[str, Any],
    *,
    fallback_error_code: str = "table_schema_unresolved",
) -> dict[str, Any]:
    return error_response(
        str(table_schema.get("stop_reason") or fallback_error_code),
        str(table_schema.get("message") or "表结构解析失败"),
        data,
    )


def _describe_menu_apply_skip(menu_plan: dict[str, Any]) -> str:
    if menu_plan.get("disabled"):
        return "菜单 SQL 已在配置中禁用，跳过写库"
    if menu_plan.get("all_menus_exist"):
        return "所有菜单已存在，跳过菜单写库"
    return "跳过菜单写库"


def _describe_dict_apply_skip(dict_plan: dict[str, Any]) -> str:
    if dict_plan.get("disabled"):
        return "字典 SQL 已在配置中禁用"
    if not dict_plan.get("has_dicts"):
        return "未检测到需生成的字典数据"
    return "跳过字典写库"


def _describe_sql_apply_skip(
    menu_plan: dict[str, Any],
    dict_plan: dict[str, Any],
) -> str:
    parts = [
        _describe_menu_apply_skip(menu_plan),
        _describe_dict_apply_skip(dict_plan),
    ]
    return "；".join(parts)


def _prepare_codegen_sql_result(
    root: Path,
    config: WorkspaceConfig,
    context: dict[str, Any],
    *,
    write_files: bool,
    overwrite: bool,
    module_menu_name: str | None = None,
    menu_name: str | None = None,
    menu_icon: str | None = None,
    module_menu_icon: str | None = None,
) -> dict[str, Any]:
    sql_result: dict[str, Any] = {}
    database_result, database_catalog = _load_database_dict_catalog_safely(root, config)
    sql_result["database"] = database_result
    sql_result["database_dict_catalog"] = database_catalog
    sql_bundle = build_codegen_sql_bundle(
        context,
        module_menu_name=module_menu_name,
        menu_name=menu_name,
        menu_icon=menu_icon,
        module_menu_icon=module_menu_icon,
        database_dict_catalog=database_catalog if database_catalog and database_catalog.get("ok") else None,
    )
    sql_result["sql_bundle"] = sql_bundle
    _attach_generated_dict_types(context, dict_plan=sql_bundle.get("dict_plan"))
    if not sql_bundle.get("ok"):
        sql_result["ok"] = False
        sql_result["error_code"] = "generate_codegen_sql_failed"
        sql_result["message"] = str(sql_bundle.get("message") or "代码生成 SQL 构建失败")
        return sql_result

    if write_files:
        write_result = write_codegen_sql_bundle(sql_bundle, overwrite=overwrite)
        write_result["workspace_root"] = str(root)
        sql_result["write_result"] = write_result

    codegen_sql = context.get("codegen_sql", {})
    menu_mode = str(codegen_sql.get("menu_mode") or "auto")
    dict_mode = str(codegen_sql.get("dict_mode") or "auto")
    apply_to_database = bool(codegen_sql.get("apply_to_database"))
    menu_plan = sql_bundle.get("menu_plan", {})
    dict_plan = sql_bundle.get("dict_plan", {})

    menu_generates_sql = not menu_plan.get("disabled")
    dict_generates_sql = not dict_plan.get("disabled")
    menu_needs_db = (
        apply_to_database
        and menu_mode == "auto"
        and menu_generates_sql
        and not menu_plan.get("all_menus_exist", False)
    )
    dict_needs_db = (
        apply_to_database
        and dict_mode == "auto"
        and dict_generates_sql
        and bool(dict_plan.get("has_dicts"))
        and not bool(dict_plan.get("all_complete", False))
    )

    if not apply_to_database:
        sql_result["apply_result"] = {
            "ok": True,
            "skipped_reason": "apply_disabled_by_config",
            "codegen_sql_modes": {"menu": menu_mode, "dict": dict_mode},
            "message": "codegen.apply_to_database=false，跳过菜单与字典写库",
        }
    elif not menu_needs_db and not dict_needs_db:
        sql_result["apply_result"] = {
            "ok": True,
            "skipped_reason": "no_database_apply_needed",
            "codegen_sql_modes": {"menu": menu_mode, "dict": dict_mode},
            "message": _describe_sql_apply_skip(menu_plan, dict_plan),
        }
    else:
        if not database_result.get("ok"):
            sql_result["ok"] = False
            sql_result["error_code"] = "database_config_unresolved"
            sql_result["message"] = str(database_result.get("message") or "数据库配置未解析")
            return sql_result

        if menu_needs_db:
            sql_result["apply_result"] = apply_menu_plan_to_database(
                database_result["database"],
                menu_plan,
            )
        else:
            sql_result["apply_result"] = {
                "ok": True,
                "skipped_reason": "menu_skipped",
                "codegen_sql_modes": {"menu": menu_mode, "dict": dict_mode},
                "message": _describe_menu_apply_skip(menu_plan),
            }

        if dict_needs_db:
            sql_result["dict_apply_result"] = apply_dict_plan_to_database(
                database_result["database"],
                dict_plan,
            )
        elif dict_plan.get("has_dicts"):
            sql_result["dict_apply_result"] = {
                "ok": True,
                "skipped_reason": "all_dicts_complete",
                "codegen_sql_modes": {"menu": menu_mode, "dict": dict_mode},
                "message": "所有字典数据已存在且完整，跳过字典创建",
            }
        else:
            sql_result["dict_apply_result"] = {
                "ok": True,
                "skipped_reason": "dict_skipped",
                "codegen_sql_modes": {"menu": menu_mode, "dict": dict_mode},
                "message": _describe_dict_apply_skip(dict_plan),
            }

    write_failed = bool(write_files and not sql_result.get("write_result", {}).get("ok", True))
    apply_succeeded = bool(
        sql_result.get("apply_result", {}).get("ok", True)
        and sql_result.get("dict_apply_result", {}).get("ok", True)
    )
    if write_failed:
        sql_result["ok"] = bool(apply_to_database and apply_succeeded)
        sql_result["error_code"] = None if sql_result["ok"] else "generate_codegen_sql_write_failed"
        sql_result["message"] = (
            "SQL 已生成并执行数据库写入，但部分文件写入失败"
            if sql_result["ok"]
            else "SQL 已生成，但写入文件时存在失败项"
        )
        return sql_result

    sql_result["ok"] = apply_succeeded
    sql_result["error_code"] = None if apply_succeeded else "generate_codegen_sql_apply_failed"
    sql_result["message"] = "代码生成 SQL 已准备完成" if apply_succeeded else "SQL 已生成，但数据库写入存在失败项"
    return sql_result


def _load_database_dict_catalog_safely(
    root: Path,
    config: WorkspaceConfig,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    database_result = resolve_database_config(root, config)
    database_catalog: dict[str, Any] | None = None
    if database_result.get("ok"):
        try:
            database_catalog = load_dict_catalog_from_database(database_result["database"])
        except Exception as exc:
            database_catalog = {
                "ok": False,
                "message": f"读取数据库字典目录失败：{exc}",
            }
    return database_result, database_catalog


def _attach_smart_generated_dict_types(
    root: Path,
    config: WorkspaceConfig,
    context: dict[str, Any],
) -> None:
    database_result, database_catalog = _load_database_dict_catalog_safely(root, config)
    table_schema = context.get("table_schema") or {}
    sql_dump_path_str = table_schema.get("sql_dump_path")
    sql_dump_path = Path(sql_dump_path_str) if sql_dump_path_str else None
    dict_plan = build_dict_plan(
        context,
        sql_dump_path=sql_dump_path,
        database_dict_catalog=database_catalog if database_catalog and database_catalog.get("ok") else None,
    )
    context["dict_catalog_resolution"] = {
        "database": database_result,
        "database_dict_catalog": database_catalog,
        "dict_plan": dict_plan,
    }
    _attach_generated_dict_types(context, dict_plan=dict_plan)


def load_config_or_error(
    workspace_root: str | None = None,
) -> tuple[Path, WorkspaceConfig] | dict[str, Any]:
    root_or_error = get_safe_workspace_root_or_error(workspace_root)
    if isinstance(root_or_error, dict):
        return root_or_error
    root = root_or_error
    config_file = load_workspace_config_file(root)
    if not config_file.exists:
        return initialize_config_response(root)
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
        return initialize_config_response(root)
    return root, config


def initialize_config_response(root: Path) -> dict[str, Any]:
    try:
        config_file = auto_init_workspace_config(root)
    except UnsafeWorkspaceRootError:
        return workspace_root_required_response(root, explicit=True)
    except WorkspaceProjectsNotDetectedError:
        return workspace_projects_not_detected_response(root)
    detected_projects = discover_workspace_projects(root)
    config_summary = summarize_initialized_config(config_file)
    return error_response(
        "config_initialized",
        "首次使用 Yudao Pilot，已经自动初始化 ./.yudao-pilot/config.yaml，并根据当前 MCP Client 项目根目录补充项目路径。请先让用户确认：继续执行当前操作，还是先结束以便手动审阅或编辑 yaml。",
        {
            "workspace_root": str(root),
            "initialized": True,
            "should_stop": True,
            "config": config_file.model_dump(),
            "detected_projects": detected_projects,
            "config_summary": config_summary,
            "next_action_prompt": (
                "当前 MCP 初始化的 ./.yudao-pilot/config.yaml 已经准备好。"
                "请向用户说明已识别并写入的后端/前端项目目录，然后询问："
                "是否继续执行刚才的操作，还是先结束会话以便手动审阅或编辑 yaml？"
            ),
        },
    )


def summarize_initialized_config(config_file: Any) -> dict[str, Any]:
    content = getattr(config_file, "content", None) or ""
    try:
        config = WorkspaceConfig.model_validate(yaml.safe_load(content) or {})
    except Exception:
        return {"backend": None, "frontends": []}
    return {
        "backend": {
            "type": config.projects.backend.type,
            "path": config.projects.backend.path,
        },
        "frontends": [
            {"type": frontend.type, "path": frontend.path}
            for frontend in config.projects.frontend
        ],
    }


@mcp.tool
def load_workspace_config_tool(workspace_root: str | None = None) -> dict[str, Any]:
    """加载当前工作区配置；如果配置文件不存在，则返回初始化模板。"""
    root_or_error = get_safe_workspace_root_or_error(workspace_root)
    if isinstance(root_or_error, dict):
        return root_or_error
    root = root_or_error
    config_file = load_workspace_config_file(root)
    if not config_file.exists:
        return initialize_config_response(root)
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
    root_or_error = get_safe_workspace_root_or_error(workspace_root)
    if isinstance(root_or_error, dict):
        return root_or_error
    root = root_or_error
    try:
        config_file = auto_init_workspace_config(root, overwrite=overwrite)
    except UnsafeWorkspaceRootError:
        return workspace_root_required_response(root, explicit=workspace_root is not None)
    except WorkspaceProjectsNotDetectedError:
        return workspace_projects_not_detected_response(root)
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
    backend_module_dir: str | None = None,
    backend_package_module: str | None = None,
) -> dict[str, Any]:
    """结合配置规则、后端默认配置和 SQL 菜单数据，构建生成代码所需上下文。

    backend_module_dir: 显式后端目标模块目录，支持 yudao-module-a/yudao-module-b 或 a/b。
    backend_package_module: 显式 Java package module 名，例如 b；未传时使用 module_name。
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
        backend_module_dir=backend_module_dir,
        backend_package_module=backend_package_module,
        preserve_business_name=business_name is not None,
    )
    context["workspace_root"] = str(root)
    context["resolved_from_config"] = resolution.model_dump()
    if not context["table_schema"].get("resolved"):
        return stop_response_from_schema(context["table_schema"], context)
    return success_response("代码生成上下文分析完成", context)


@mcp.tool
def inspect_table_schema_tool(
    table_name: str, workspace_root: str | None = None
) -> dict[str, Any]:
    """优先从真实数据库解析字段，缺失时回退到目标迁移 SQL 或本地结构 SQL。"""
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
    return stop_response_from_schema(result, result)


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
    overwrite: bool = False,
    field_overrides: dict[str, str] | None = None,
    backend_module_dir: str | None = None,
    backend_package_module: str | None = None,
) -> dict[str, Any]:
    """根据当前上下文生成首版代码骨架，可选择只预览或直接写入工作区。

    普通代码文件默认 overwrite=false，写入时若文件已存在会返回 should_stop，
    由调用方询问用户是否覆盖；前端字典常量、后端错误码等合并型文件不受此限制。

    field_overrides: AI 覆盖字段组件类型，格式为 {"java_field": "html_type"}，
    例如 {"lng": "inputNumber", "lat": "inputNumber"}。
    可用 html_type 值: input, inputNumber, textarea, editor, select, radio,
    checkbox, datetime, date, imageUpload, fileUpload。
    backend_module_dir: 显式后端目标模块目录，支持 yudao-module-a/yudao-module-b 或 a/b。
    backend_package_module: 显式 Java package module 名，例如 b；未传时使用 module_name。
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
        backend_module_dir=backend_module_dir,
        backend_package_module=backend_package_module,
        preserve_business_name=business_name is not None,
    )
    if field_overrides:
        _apply_field_overrides(context, field_overrides)
    _attach_smart_generated_dict_types(root, config, context)
    result: dict[str, Any] = {
        "workspace_root": str(root),
        "table_name": table_name,
        "resolved_from_config": resolution.model_dump(),
        "context": context,
    }
    table_schema = context.get("table_schema") or {}
    if table_schema and not table_schema.get("resolved"):
        return stop_response_from_schema(table_schema, result)
    generated_files = generate_scaffold_files(
        context,
        overwrite=overwrite,
        include_backend=include_backend,
        include_frontend=include_frontend,
    )
    result["generated_files"] = [file.model_dump() for file in generated_files]
    result["generation_summary"] = summarize_generated_files(
        generated_files,
        config,
        include_backend=include_backend,
        include_frontend=include_frontend,
    )
    if write_files:
        write_result = write_generated_files(root, config, generated_files)
        write_result["workspace_root"] = str(root)
        result["write_result"] = write_result
        if write_result["ok"]:
            sql_result = _prepare_codegen_sql_result(
                root,
                config,
                context,
                write_files=True,
                overwrite=overwrite,
                menu_name=menu_name,
            )
            result["sql_result"] = sql_result
            if sql_result["ok"]:
                return success_response("代码骨架与 SQL 资产已生成并按配置处理完成", result)
            return error_response(
                str(sql_result.get("error_code") or "generate_codegen_sql_failed"),
                str(sql_result.get("message") or "代码骨架已写入，但 SQL 资产处理失败"),
                result,
            )
        return error_response("generate_codegen_scaffold_failed", "代码骨架生成成功，但写入存在失败项", result)
    preview_result = write_preview_generated_files(root, generated_files, table_name=table_name)
    preview_result["workspace_root"] = str(root)
    result["preview_result"] = preview_result
    if not preview_result["ok"]:
        return error_response("generate_codegen_preview_failed", "代码骨架预览写入临时目录失败", result)
    return success_response("代码骨架生成成功", result)


def summarize_generated_files(
    generated_files: list[GeneratedFile],
    config: WorkspaceConfig,
    *,
    include_backend: bool,
    include_frontend: bool,
) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_target_type: dict[str, int] = {}
    warnings: list[str] = []
    for generated_file in generated_files:
        by_kind[generated_file.target_kind] = by_kind.get(generated_file.target_kind, 0) + 1
        by_target_type[generated_file.target_type] = by_target_type.get(generated_file.target_type, 0) + 1

    configured_frontends = [frontend.type for frontend in config.projects.frontend]
    if configured_frontends and not include_frontend:
        warnings.append("include_frontend=false，已跳过配置中的前端代码生成")
    if include_frontend and configured_frontends and by_kind.get("frontend", 0) == 0:
        warnings.append("已请求前端代码生成，但未产生前端文件，请检查前端项目配置")

    return {
        "total": len(generated_files),
        "by_kind": by_kind,
        "by_target_type": by_target_type,
        "include_backend": include_backend,
        "include_frontend": include_frontend,
        "configured_frontends": configured_frontends,
        "warnings": warnings,
    }


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
    backend_module_dir: str | None = None,
    backend_package_module: str | None = None,
) -> dict[str, Any]:
    """生成 MySQL 菜单 SQL 与模块 H2 测试 SQL，可选直接写入文件，并按配置决定是否写库。

    菜单/字典是否生成由工作区配置 codegen.menu_sql_mode、codegen.dict_sql_mode 控制；
    是否允许写库由 codegen.apply_to_database 控制：
    auto（默认）= 生成 SQL，write_files 写迁移，若 apply_to_database=true 则允许写库；
    migration_only = 仅生成/写入迁移文件，不执行真实数据库写入；
    disabled = 不生成对应 SQL（不写迁移中的该段）。
    backend_module_dir: 显式后端目标模块目录，支持 yudao-module-a/yudao-module-b 或 a/b。
    backend_package_module: 显式 Java package module 名，例如 b；未传时使用 module_name。
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
        backend_module_dir=backend_module_dir,
        backend_package_module=backend_package_module,
        preserve_business_name=business_name is not None,
    )
    result: dict[str, Any] = {
        "workspace_root": str(root),
        "table_name": table_name,
        "resolved_from_config": resolution.model_dump(),
        "context": context,
    }
    table_schema = context.get("table_schema") or {}
    if table_schema and not table_schema.get("resolved"):
        return stop_response_from_schema(table_schema, result)
    sql_result = _prepare_codegen_sql_result(
        root,
        config,
        context,
        write_files=write_files,
        overwrite=overwrite,
        module_menu_name=module_menu_name,
        menu_name=menu_name,
        menu_icon=menu_icon,
        module_menu_icon=module_menu_icon,
    )
    result.update(sql_result)
    sql_bundle = sql_result.get("sql_bundle", {})
    result["sql_bundle"] = sql_bundle
    if not sql_bundle.get("ok"):
        return error_response("generate_codegen_sql_failed", sql_bundle["message"], result)
    if sql_result["ok"]:
        if sql_result.get("message") == "SQL 已生成并执行数据库写入，但部分文件写入失败":
            return success_response(sql_result["message"], result)
        if sql_result.get("apply_result", {}).get("skipped_reason") == "no_database_apply_needed":
            return success_response("无需向数据库写入菜单或字典", result)
        return success_response("代码生成 SQL 已准备完成", result)
    if sql_result.get("error_code") == "database_config_unresolved":
        return error_response(
            "database_config_unresolved",
            str(sql_result.get("message") or "数据库配置未解析"),
            result,
        )
    if sql_result.get("error_code") == "generate_codegen_sql_write_failed":
        return error_response(
            "generate_codegen_sql_write_failed",
            "SQL 已生成，但写入文件时存在失败项",
            result,
        )
    return error_response(
        str(sql_result.get("error_code") or "generate_codegen_sql_failed"),
        str(sql_result.get("message") or "代码生成 SQL 处理失败"),
        result,
    )


def infer_table_resolution(
    table_name: str,
    config: WorkspaceConfig,
    *,
    backend_root: Path | None = None,
    create_missing_module: bool = False,
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
                business=derive_business_name(prefix_module, table_name, matched_prefix),
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
            if create_missing_module:
                _ensure_module_enabled(backend_root, inferred_module)
            return TableResolution(
                module=inferred_module,
                matched_by="new_module",
                business=derive_business_name(inferred_module, table_name),
                entity=snake_to_pascal(table_name),
            )
        if create_missing_module:
            _create_module_scaffold(backend_root, inferred_module)
            _ensure_module_enabled(backend_root, inferred_module)
        return TableResolution(
            module=inferred_module,
            matched_by="new_module",
            business=derive_business_name(inferred_module, table_name),
            entity=snake_to_pascal(table_name),
        )

    return TableResolution(
        module=inferred_module,
        matched_by="fallback",
        business=derive_business_name(inferred_module, table_name),
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
                business=derive_business_name(entity.module_name, table_name, entity.business_dir),
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
            business=derive_business_name(best_match.module_name, table_name, best_match.business_dir),
            entity=snake_to_pascal(table_name),
        )
    return None


def derive_business_name(module_name: str, table_name: str, business_name: str | None = None) -> str:
    normalized_module = normalize_snake_case(module_name)
    normalized_table = normalize_snake_case(table_name)
    raw_business = str(business_name or normalized_table).replace("\\", "/").strip().strip("/")
    if not raw_business:
        raw_business = normalized_table

    business_segments = [normalize_snake_case(segment) for segment in raw_business.split("/") if segment.strip()]
    if not business_segments:
        business_segments = [normalized_table]

    business_leaf = business_segments[-1]
    if normalized_table.startswith(normalized_module + "_"):
        table_suffix = normalized_table[len(normalized_module) + 1 :]
        if business_leaf in {normalized_table, normalized_module, f"{normalized_module}_{table_suffix}"}:
            business_segments[-1] = table_suffix

    return "/".join(segment for segment in business_segments if segment)



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


def _attach_generated_dict_types(
    context: dict[str, Any],
    dict_plan: dict[str, Any] | None = None,
) -> None:
    """Detect dict-like columns and attach generated_dict_type to each column."""
    table_schema = context.get("table_schema") or {}
    columns = table_schema.get("columns") or []
    table_name = context.get("table_name", "")
    table_comment = str(table_schema.get("table_comment") or table_name)
    if dict_plan and dict_plan.get("dict_types"):
        dict_fields = list(dict_plan.get("dict_types") or [])
    else:
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
            if df.get("reuse_existing"):
                col["generated_dict_reused"] = True
                col["generated_dict_match"] = df.get("reuse_match")


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
