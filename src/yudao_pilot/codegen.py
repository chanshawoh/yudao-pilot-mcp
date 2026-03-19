from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .config import WorkspaceConfig
from .database import extract_database_from_spring_config, resolve_database_config
from .inspector import (
    resolve_backend_repo_root,
    resolve_backend_server_root,
    resolve_project_path,
)
from .schema import inspect_table_schema


FRONTEND_TYPE_TO_CODEGEN_FRONT_TYPES: dict[str, list[int]] = {
    "yudao-ui-admin-vue3": [20],
    "yudao-ui-admin-uniapp": [60],
}

CODEGEN_FRONT_TYPE_LABELS: dict[int, str] = {
    20: "VUE3_ELEMENT_PLUS",
    40: "VUE3_VBEN5_ANTD_SCHEMA",
    41: "VUE3_VBEN5_ANTD_GENERAL",
    50: "VUE3_VBEN5_EP_SCHEMA",
    51: "VUE3_VBEN5_EP_GENERAL",
    60: "VUE3_ADMIN_UNIAPP_WOT",
}

CODEGEN_VO_TYPE_LABELS: dict[int, str] = {
    10: "VO",
    20: "DO",
}


def compare_codegen_reference_projects(reference_root: Path) -> dict[str, Any]:
    jdk8_files = {
        "CodegenBuilder": reference_root / "ruoyi-vue-pro/yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/service/codegen/inner/CodegenBuilder.java",
        "CodegenEngine": reference_root / "ruoyi-vue-pro/yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/service/codegen/inner/CodegenEngine.java",
        "CodegenServiceImpl": reference_root / "ruoyi-vue-pro/yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/service/codegen/CodegenServiceImpl.java",
        "CodegenProperties": reference_root / "ruoyi-vue-pro/yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/framework/codegen/config/CodegenProperties.java",
    }
    jdk17_files = {
        "CodegenBuilder": reference_root / "ruoyi-vue-pro-jdk17/yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/service/codegen/inner/CodegenBuilder.java",
        "CodegenEngine": reference_root / "ruoyi-vue-pro-jdk17/yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/service/codegen/inner/CodegenEngine.java",
        "CodegenServiceImpl": reference_root / "ruoyi-vue-pro-jdk17/yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/service/codegen/CodegenServiceImpl.java",
        "CodegenProperties": reference_root / "ruoyi-vue-pro-jdk17/yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/framework/codegen/config/CodegenProperties.java",
    }

    comparisons: dict[str, Any] = {}
    only_framework_diff = True
    for name, jdk8_path in jdk8_files.items():
        jdk17_path = jdk17_files[name]
        if not (jdk8_path.exists() and jdk17_path.exists()):
            comparisons[name] = {"same": False, "reason": "参考文件缺失"}
            only_framework_diff = False
            continue
        normalized_jdk8 = normalize_java_source(jdk8_path.read_text(encoding="utf-8", errors="ignore"))
        normalized_jdk17 = normalize_java_source(jdk17_path.read_text(encoding="utf-8", errors="ignore"))
        same = normalized_jdk8 == normalized_jdk17
        comparisons[name] = {
            "same": same,
            "jdk8_path": str(jdk8_path),
            "jdk17_path": str(jdk17_path),
        }
        if not same:
            only_framework_diff = False

    return {
        "same_core_logic": only_framework_diff,
        "recommended_reference": "ruoyi-vue-pro-jdk17",
        "reason": "代码生成核心逻辑一致，差异主要是 Spring Boot 2/3 的 javax/jakarta 适配"
        if only_framework_diff
        else "存在超出框架适配的差异，请进一步人工确认",
        "comparisons": comparisons,
    }


def build_codegen_context(
    workspace_root: str | Path,
    config: WorkspaceConfig,
    table_name: str,
    *,
    module_name: str,
    business_name: str,
    entity_name: str,
    menu_name: str | None = None,
    parent_menu_name: str | None = None,
    parent_menu_id: int | None = None,
) -> dict[str, Any]:
    root = Path(workspace_root).expanduser().resolve()
    configured_backend_root = resolve_project_path(root, config.projects.backend.path)
    backend_repo_root = resolve_backend_repo_root(configured_backend_root)
    backend_server_root = resolve_backend_server_root(configured_backend_root)
    backend_defaults = resolve_backend_codegen_defaults(
        backend_server_root, config.projects.backend.config_profile
    )
    frontend_targets = resolve_frontend_codegen_targets(root, config)
    menu_context = resolve_menu_context(
        backend_repo_root,
        module_name=module_name,
        menu_name=menu_name or entity_name,
        parent_menu_name=parent_menu_name,
        parent_menu_id=parent_menu_id,
    )
    migration_plan = build_migration_plan(
        backend_repo_root,
        f"create_{table_name}_table",
    )
    database_result = resolve_database_config(root, config)
    table_schema = inspect_table_schema(
        backend_repo_root,
        table_name,
        database_result["database"] if database_result.get("ok") else None,
    )
    generated_file_plan = build_generated_file_plan(
        module_name=module_name,
        business_name=business_name,
        entity_name=entity_name,
        base_package=str(backend_defaults.get("base_package") or "cn.iocoder.yudao"),
        frontend_targets=frontend_targets,
        unit_test_enable=bool(backend_defaults.get("unit_test_enable")),
    )

    return {
        "table_name": table_name,
        "module_name": module_name,
        "business_name": business_name,
        "entity_name": entity_name,
        "menu_name": menu_name or entity_name,
        "permission_prefix": build_permission_prefix(module_name, entity_name),
        "backend_project": {
            "type": config.projects.backend.type,
            "path": str(configured_backend_root),
            "repo_root": str(backend_repo_root),
            "server_root": str(backend_server_root),
        },
        "backend_codegen_defaults": backend_defaults,
        "frontend_targets": frontend_targets,
        "menu_context": menu_context,
        "table_schema": table_schema,
        "migration_plan": migration_plan,
        "generated_file_plan": generated_file_plan,
        "notes": build_codegen_notes(menu_context, frontend_targets, backend_defaults, table_schema),
    }


def resolve_backend_codegen_defaults(
    backend_root: Path, config_profile: str
) -> dict[str, Any]:
    application_config = load_backend_application_config(backend_root, config_profile)
    if application_config is None:
        return {
            "resolved": False,
            "message": "未能从后端配置读取 yudao.codegen 默认配置",
        }

    flattened = flatten_dict(application_config)
    resolved = resolve_placeholders_in_mapping(flattened)
    codegen_section = extract_nested(application_config, ["yudao", "codegen"]) or {}

    base_package = resolve_scalar(codegen_section.get("base-package"), resolved)
    db_schemas, db_schemas_source = resolve_codegen_db_schemas(application_config, codegen_section, resolved)
    front_type = coerce_int(resolve_scalar(codegen_section.get("front-type"), resolved))
    vo_type = coerce_int(resolve_scalar(codegen_section.get("vo-type"), resolved))
    delete_batch_enable = coerce_bool(
        resolve_scalar(codegen_section.get("delete-batch-enable"), resolved)
    )
    unit_test_enable = coerce_bool(
        resolve_scalar(codegen_section.get("unit-test-enable"), resolved)
    )

    return {
        "resolved": True,
        "config_source": application_config.get("__source__"),
        "base_package": base_package,
        "db_schemas": db_schemas,
        "db_schemas_source": db_schemas_source,
        "front_type": front_type,
        "front_type_label": CODEGEN_FRONT_TYPE_LABELS.get(front_type),
        "vo_type": vo_type,
        "vo_type_label": CODEGEN_VO_TYPE_LABELS.get(vo_type),
        "delete_batch_enable": delete_batch_enable,
        "unit_test_enable": unit_test_enable,
    }


def resolve_frontend_codegen_targets(
    workspace_root: Path, config: WorkspaceConfig
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for frontend in config.projects.frontend:
        frontend_root = resolve_project_path(workspace_root, frontend.path)
        type_candidates = FRONTEND_TYPE_TO_CODEGEN_FRONT_TYPES.get(frontend.type)
        if type_candidates is None and frontend.type == "yudao-ui-admin-vben":
            type_candidates = infer_vben_front_types(frontend_root)

        default_front_type = type_candidates[0] if type_candidates else None
        results.append(
            {
                "project_type": frontend.type,
                "path": str(frontend_root),
                "codegen_front_types": type_candidates or [],
                "default_front_type": default_front_type,
                "default_front_type_label": CODEGEN_FRONT_TYPE_LABELS.get(default_front_type),
                "ambiguous": len(type_candidates or []) > 1,
            }
        )
    return results


def infer_vben_front_types(frontend_root: Path) -> list[int]:
    app_root = frontend_root / "apps"
    has_web_ele = (app_root / "web-ele").exists()
    has_web_antd = (app_root / "web-antd").exists()
    if has_web_ele and has_web_antd:
        return [50, 40]
    if has_web_ele:
        return [50]
    if has_web_antd:
        return [40]
    return [50]


def resolve_menu_context(
    backend_root: Path,
    *,
    module_name: str,
    menu_name: str,
    parent_menu_name: str | None,
    parent_menu_id: int | None,
) -> dict[str, Any]:
    sql_dump = backend_root / "sql" / "mysql" / "ruoyi-vue-pro.sql"
    if not sql_dump.exists():
        return {
            "sql_dump_path": str(sql_dump),
            "resolved": False,
            "message": "未找到系统 SQL 文件，无法自动分析菜单数据",
            "parent_menu_candidates": [],
        }

    menus = load_system_menus(sql_dump)
    parent_candidates = find_parent_menu_candidates(menus, module_name)
    resolved_parent = None

    if parent_menu_id is not None:
        resolved_parent = next((menu for menu in menus if menu["id"] == parent_menu_id), None)
    elif parent_menu_name:
        resolved_parent = next((menu for menu in menus if menu["name"] == parent_menu_name), None)
    elif parent_candidates:
        resolved_parent = parent_candidates[0]

    return {
        "sql_dump_path": str(sql_dump),
        "resolved": resolved_parent is not None,
        "menu_name": menu_name,
        "requested_parent_menu_name": parent_menu_name,
        "requested_parent_menu_id": parent_menu_id,
        "resolved_parent_menu": resolved_parent,
        "parent_menu_candidates": parent_candidates,
        "needs_ai_parent_menu": resolved_parent is None,
        "message": "已自动匹配父菜单"
        if resolved_parent
        else "未能自动确定父菜单，请 AI 结合业务语义或用户输入决定",
    }

def write_mysql_migration(
    backend_root: Path,
    migration_name: str,
    sql_content: str,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    migration_plan = build_migration_plan(backend_root, migration_name)
    output_path = Path(migration_plan["path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not overwrite:
        return {
            "ok": False,
            "path": str(output_path),
            "message": "迁移文件已存在，且 overwrite=false",
        }

    header = "-- Laravel-style migration generated by Yudao Pilot\n"
    output_path.write_text(header + sql_content.strip() + "\n", encoding="utf-8")
    return {
        "ok": True,
        "path": str(output_path),
        "message": "迁移文件已生成",
    }


def build_migration_plan(backend_root: Path, migration_name: str) -> dict[str, Any]:
    repo_root = resolve_backend_repo_root(backend_root)
    migration_dir = repo_root / "sql" / "mysql" / "migrations"
    filename = generate_laravel_style_migration_filename(migration_name)
    return {
        "directory": str(migration_dir),
        "filename": filename,
        "path": str(migration_dir / filename),
    }


def load_backend_application_config(
    backend_root: Path, config_profile: str
) -> dict[str, Any] | None:
    server_root = resolve_backend_server_root(backend_root)
    resource_root = server_root / "src" / "main" / "resources"
    candidates = deduplicate_preserve_order(
        [
        resource_root / "application.yaml",
        resource_root / "application.yml",
        resource_root / "application-local.yaml",
        resource_root / "application-local.yml",
        resource_root / f"application-{config_profile}.yaml",
        resource_root / f"application-{config_profile}.yml",
        ]
    )
    merged: dict[str, Any] = {}
    found_paths: list[str] = []
    for file_path in candidates:
        if not file_path.exists():
            continue
        raw_text = file_path.read_text(encoding="utf-8")
        current_merged: dict[str, Any] = {}
        for document in yaml.safe_load_all(raw_text):
            if isinstance(document, dict):
                current_merged = deep_merge_dicts(current_merged, document)
        if current_merged:
            merged = deep_merge_dicts(merged, current_merged)
            found_paths.append(str(file_path))
    if not found_paths:
        return None
    merged["__source__"] = found_paths
    return merged


def load_system_menus(sql_dump_path: Path) -> list[dict[str, Any]]:
    menus: list[dict[str, Any]] = []
    for line in sql_dump_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith("INSERT INTO `system_menu`"):
            continue
        values_text = line.partition("VALUES")[2].strip().rstrip(";")
        for row_text in split_sql_value_rows(values_text):
            values = split_sql_values(row_text)
            if len(values) < 10:
                continue
            menu = {
                "id": coerce_int(parse_sql_scalar(values[0])),
                "name": parse_sql_scalar(values[1]),
                "permission": parse_sql_scalar(values[2]),
                "type": coerce_int(parse_sql_scalar(values[3])),
                "sort": coerce_int(parse_sql_scalar(values[4])),
                "parent_id": coerce_int(parse_sql_scalar(values[5])),
                "path": parse_sql_scalar(values[6]),
                "icon": parse_sql_scalar(values[7]),
                "component": parse_sql_scalar(values[8]),
                "component_name": parse_sql_scalar(values[9]),
            }
            menus.append(menu)
    return menus


def find_parent_menu_candidates(
    menus: list[dict[str, Any]], module_name: str
) -> list[dict[str, Any]]:
    parent_ids: list[int] = []
    for menu in menus:
        component = str(menu.get("component") or "")
        path = str(menu.get("path") or "")
        if component.startswith(f"{module_name}/"):
            parent_id = coerce_int(menu.get("parent_id"))
            if parent_id:
                parent_ids.append(parent_id)
        elif path == module_name or path == f"/{module_name}":
            menu_id = coerce_int(menu.get("id"))
            if menu_id:
                parent_ids.append(menu_id)

    unique_parent_ids = []
    seen: set[int] = set()
    for parent_id in parent_ids:
        if parent_id in seen:
            continue
        seen.add(parent_id)
        unique_parent_ids.append(parent_id)

    return [menu for menu in menus if menu.get("id") in unique_parent_ids]


def build_codegen_notes(
    menu_context: dict[str, Any],
    frontend_targets: list[dict[str, Any]],
    backend_defaults: dict[str, Any],
    table_schema: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    if backend_defaults.get("resolved"):
        notes.append(
            "后端默认 codegen 配置已从 application.yaml 解析，可直接作为未显式指定时的默认值使用"
        )
    else:
        notes.append("后端默认 codegen 配置未解析成功，AI 需要使用保守默认值")
    if backend_defaults.get("db_schemas_source") == "datasource-url":
        notes.append("db-schemas 未在 yudao.codegen 中解析成功，已回退为数据源 JDBC URL 中的数据库名")
    elif backend_defaults.get("db_schemas_source") == "unresolved":
        notes.append("db-schemas 未能自动解析，AI 生成 SQL 或同步表结构时需要再次确认数据库名")

    if any(target.get("ambiguous") for target in frontend_targets):
        notes.append(
            "存在多种可映射的前端模板类型，当前已按项目结构优先级给出默认值，但 AI 仍应在重要场景下复核"
        )
    if menu_context.get("needs_ai_parent_menu"):
        notes.append("父菜单未能自动解析，AI 需要结合业务语义或用户输入决定上级菜单")
    if not table_schema.get("resolved"):
        notes.append("未能自动解析表结构，当前只能生成保守骨架；如需字段级代码，请继续提供数据库或 SQL 信息")
    return notes


def generate_laravel_style_migration_filename(name: str) -> str:
    timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    return f"{timestamp}_{normalize_snake_case(name)}.sql"


def normalize_java_source(source: str) -> str:
    source = source.replace("javax.annotation", "annotation")
    source = source.replace("jakarta.annotation", "annotation")
    source = source.replace("javax.validation", "validation")
    source = source.replace("jakarta.validation", "validation")
    source = re.sub(r"import [^;]+;", "", source)
    source = re.sub(r"\s+", " ", source)
    return source.strip()


def normalize_db_schemas(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def flatten_dict(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key == "__source__":
            continue
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            result.update(flatten_dict(value, full_key))
        else:
            result[full_key] = value
    return result


def resolve_placeholders_in_mapping(flattened: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(flattened)
    for _ in range(5):
        changed = False
        for key, value in list(resolved.items()):
            if not isinstance(value, str):
                continue
            new_value = resolve_scalar(value, resolved)
            if new_value != value:
                resolved[key] = new_value
                changed = True
        if not changed:
            break
    return resolved


def resolve_scalar(value: Any, context: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        expr = match.group(1)
        default = ""
        if ":" in expr:
            expr, default = expr.split(":", 1)
        resolved = context.get(expr)
        if resolved is None:
            return default
        return str(resolved)

    return re.sub(r"\$\{([^}]+)\}", replace, value)


def extract_nested(data: dict[str, Any], keys: list[str]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def split_sql_value_rows(values_text: str) -> list[str]:
    rows: list[str] = []
    depth = 0
    current: list[str] = []
    in_string = False
    previous = ""
    for char in values_text:
        current.append(char)
        if char == "'" and previous != "\\":
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    row = "".join(current).strip().strip(",")
                    rows.append(row)
                    current = []
        previous = char
    return rows


def split_sql_values(row_text: str) -> list[str]:
    row = row_text.strip().removeprefix("(").removesuffix(")")
    values: list[str] = []
    current: list[str] = []
    in_string = False
    previous = ""
    for char in row:
        if char == "'" and previous != "\\":
            in_string = not in_string
        if char == "," and not in_string:
            values.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        previous = char
    if current:
        values.append("".join(current).strip())
    return values


def parse_sql_scalar(raw_value: str) -> Any:
    value = raw_value.strip()
    if value == "NULL":
        return None
    if value.startswith("b'") and value.endswith("'"):
        return value[2:-1]
    if value.startswith("'") and value.endswith("'"):
        inner = value[1:-1]
        inner = inner.replace("\\'", "'")
        return inner
    return value


def normalize_snake_case(value: str) -> str:
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    snake = re.sub(r"[^a-zA-Z0-9]+", "_", snake)
    snake = snake.strip("_").lower()
    return snake or "migration"


def snake_to_pascal(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_") if part)


def coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    return None


def resolve_codegen_db_schemas(
    application_config: dict[str, Any],
    codegen_section: dict[str, Any],
    resolved_mapping: dict[str, Any],
) -> tuple[list[str], str]:
    raw_db_schemas = resolve_scalar(codegen_section.get("db-schemas"), resolved_mapping)
    db_schemas = normalize_db_schemas(raw_db_schemas)
    if db_schemas:
        return db_schemas, "yudao.codegen.db-schemas"

    datasource_config = extract_database_from_spring_config(application_config)
    datasource_database = normalize_db_schemas((datasource_config or {}).get("database"))
    if datasource_database:
        return datasource_database, "datasource-url"

    return [], "unresolved"


def build_generated_file_plan(
    *,
    module_name: str,
    business_name: str,
    entity_name: str,
    base_package: str,
    frontend_targets: list[dict[str, Any]],
    unit_test_enable: bool,
) -> dict[str, Any]:
    simple_class_name = build_simple_class_name(module_name, entity_name)
    backend_files = build_backend_file_plan(
        module_name=module_name,
        business_name=business_name,
        entity_name=entity_name,
        base_package=base_package,
        unit_test_enable=unit_test_enable,
    )
    frontend_files = [
        {
            "project_type": frontend_target["project_type"],
            "default_front_type": frontend_target["default_front_type"],
            "default_front_type_label": frontend_target["default_front_type_label"],
            "ambiguous": frontend_target["ambiguous"],
            "relative_paths": build_frontend_file_plan(
                front_type=frontend_target["default_front_type"],
                module_name=module_name,
                business_name=business_name,
                simple_class_name=simple_class_name,
            ),
        }
        for frontend_target in frontend_targets
    ]
    return {
        "backend": backend_files,
        "frontends": frontend_files,
        "simple_class_name": simple_class_name,
    }


def build_backend_file_plan(
    *,
    module_name: str,
    business_name: str,
    entity_name: str,
    base_package: str,
    unit_test_enable: bool,
) -> list[str]:
    package_dir = base_package.replace(".", "/").strip("/")
    backend_files = [
        build_backend_java_path(
            module_name,
            "main",
            package_dir,
            f"controller/admin/{business_name}/vo/{entity_name}PageReqVO.java",
        ),
        build_backend_java_path(
            module_name,
            "main",
            package_dir,
            f"controller/admin/{business_name}/vo/{entity_name}RespVO.java",
        ),
        build_backend_java_path(
            module_name,
            "main",
            package_dir,
            f"controller/admin/{business_name}/vo/{entity_name}SaveReqVO.java",
        ),
        build_backend_java_path(
            module_name,
            "main",
            package_dir,
            f"controller/admin/{business_name}/{entity_name}Controller.java",
        ),
        build_backend_java_path(
            module_name,
            "main",
            package_dir,
            f"dal/dataobject/{business_name}/{entity_name}DO.java",
        ),
        build_backend_java_path(
            module_name,
            "main",
            package_dir,
            f"dal/mysql/{business_name}/{entity_name}Mapper.java",
        ),
        f"yudao-module-{module_name}/src/main/resources/mapper/{business_name}/{entity_name}Mapper.xml",
        build_backend_java_path(
            module_name,
            "main",
            package_dir,
            f"service/{business_name}/{entity_name}Service.java",
        ),
        build_backend_java_path(
            module_name,
            "main",
            package_dir,
            f"service/{business_name}/{entity_name}ServiceImpl.java",
        ),
        build_backend_java_path(
            module_name,
            "main",
            package_dir,
            "enums/ErrorCodeConstants_手动操作.java",
        ),
    ]
    if unit_test_enable:
        backend_files.append(
            build_backend_java_path(
                module_name,
                "test",
                package_dir,
                f"service/{business_name}/{entity_name}ServiceImplTest.java",
            )
        )
    return backend_files


def build_frontend_file_plan(
    *,
    front_type: int | None,
    module_name: str,
    business_name: str,
    simple_class_name: str,
) -> list[str]:
    if front_type == 20:
        return [
            f"src/views/{module_name}/{business_name}/index.vue",
            f"src/views/{module_name}/{business_name}/{simple_class_name}Form.vue",
            f"src/api/{module_name}/{business_name}/index.ts",
        ]
    if front_type == 60:
        return [
            f"src/api/{module_name}/{business_name}/index.ts",
            f"src/pages-{module_name}/{business_name}/index.vue",
            f"src/pages-{module_name}/{business_name}/components/search-form.vue",
            f"src/pages-{module_name}/{business_name}/form/index.vue",
            f"src/pages-{module_name}/{business_name}/detail/index.vue",
        ]
    if front_type in {40, 50}:
        return [
            f"src/views/{module_name}/{business_name}/data.ts",
            f"src/views/{module_name}/{business_name}/index.vue",
            f"src/views/{module_name}/{business_name}/modules/form.vue",
            f"src/api/{module_name}/{business_name}/index.ts",
        ]
    if front_type in {41, 51}:
        return [
            f"src/views/{module_name}/{business_name}/index.vue",
            f"src/views/{module_name}/{business_name}/modules/form.vue",
            f"src/api/{module_name}/{business_name}/index.ts",
        ]
    return []


def build_backend_java_path(
    module_name: str,
    src_type: str,
    package_dir: str,
    suffix: str,
) -> str:
    return (
        f"yudao-module-{module_name}/"
        f"src/{src_type}/java/{package_dir}/module/{module_name}/{suffix}"
    )


def build_simple_class_name(module_name: str, entity_name: str) -> str:
    prefix = snake_to_pascal(module_name)
    if entity_name.lower() == module_name.lower():
        return entity_name
    if prefix and entity_name.startswith(prefix):
        stripped = entity_name[len(prefix):]
        return stripped or entity_name
    return entity_name


def build_permission_prefix(module_name: str, entity_name: str) -> str:
    simple_class_name = build_simple_class_name(module_name, entity_name)
    strike_case = normalize_snake_case(simple_class_name).replace("_", "-")
    return f"{module_name}:{strike_case}"


def deduplicate_preserve_order(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
