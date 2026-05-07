from __future__ import annotations

from pathlib import Path
from typing import Any

from .codegen import (
    build_migration_plan,
    build_permission_prefix,
    coerce_int,
    load_system_menus,
    normalize_snake_case,
    parse_sql_scalar,
    split_sql_value_rows,
    split_sql_values,
    write_mysql_migration,
)
from .inspector import resolve_backend_repo_root
from .schema import extract_dict_fields


MENU_BUTTONS: list[tuple[str, str]] = [
    ("查询", "query"),
    ("创建", "create"),
    ("更新", "update"),
    ("删除", "delete"),
    ("导出", "export"),
]

MODULE_MENU_NAME_HINTS: dict[str, str] = {
    "travel": "旅游管理",
}

BUSINESS_NAME_HINTS: dict[str, str] = {
    "sim": "手机卡",
}


def _disabled_menu_plan_stub(context: dict[str, Any]) -> dict[str, Any]:
    """Minimal menu_plan for H2 markers and tooling when menu SQL is disabled."""
    return {
        "table_name": context["table_name"],
        "module_name": context["module_name"],
        "disabled": True,
        "all_menus_exist": True,
        "needs_create_root_menu": False,
        "needs_create_business_menu": False,
        "needs_create_buttons": False,
    }


def _disabled_dict_plan_stub() -> dict[str, Any]:
    return {
        "ok": True,
        "has_dicts": False,
        "disabled": True,
        "all_complete": True,
        "message": "已在配置中禁用字典 SQL 生成",
        "dict_types": [],
    }


def build_codegen_sql_bundle(
    context: dict[str, Any],
    *,
    module_menu_name: str | None = None,
    menu_name: str | None = None,
    menu_icon: str | None = None,
    module_menu_icon: str | None = None,
) -> dict[str, Any]:
    table_schema = context.get("table_schema") or {}
    if not table_schema.get("resolved"):
        return {
            "ok": False,
            "message": "表结构未解析成功，暂时无法生成 SQL",
            "context": context,
        }

    codegen_sql = context.get("codegen_sql") or {}
    menu_mode: str = str(codegen_sql.get("menu_mode") or "auto")
    dict_mode: str = str(codegen_sql.get("dict_mode") or "auto")

    backend_repo_root = resolve_backend_repo_root(Path(context["backend_project"]["repo_root"]))
    h2_plan = resolve_h2_sql_plan(
        backend_repo_root,
        context["module_name"],
        module_dir_name=(context.get("backend_project") or {}).get("codegen_target", {}).get("module_dir_name"),
    )

    if menu_mode == "disabled":
        menu_plan = _disabled_menu_plan_stub(context)
        menu_sql = ""
    else:
        menu_plan = build_menu_plan(
            context,
            module_menu_name=module_menu_name,
            menu_name=menu_name,
            menu_icon=menu_icon,
            module_menu_icon=module_menu_icon,
        )
        menu_sql = render_mysql_menu_sql(menu_plan)

    sql_dump_path_str = table_schema.get("sql_dump_path")
    sql_dump_path = Path(sql_dump_path_str) if sql_dump_path_str else None
    if dict_mode == "disabled":
        dict_plan = _disabled_dict_plan_stub()
        dict_sql = ""
    else:
        dict_plan = build_dict_plan(context, sql_dump_path=sql_dump_path)
        dict_sql = render_dict_migration_sql(dict_plan) if dict_plan.get("has_dicts") else ""

    parts = [p for p in (menu_sql.strip(), dict_sql.strip()) if p]
    if parts:
        combined_sql = "\n\n".join(parts) + "\n"
    else:
        combined_sql = (
            "-- Yudao Pilot: 菜单与字典 SQL 均在配置中禁用 (codegen.menu_sql_mode / codegen.dict_sql_mode = disabled)\n"
        )

    menu_migration_name = f"add_{context['table_name']}_menus"

    return {
        "ok": True,
        "message": "代码生成 SQL 方案已构建",
        "backend_repo_root": str(backend_repo_root),
        "codegen_sql_modes": {"menu": menu_mode, "dict": dict_mode},
        "mysql": {
            "supported_db": "mysql",
            "migration_name": menu_migration_name,
            "migration_plan": build_migration_plan(backend_repo_root, menu_migration_name),
            "content": combined_sql,
        },
        "h2": {
            **h2_plan,
            "create_sql": render_h2_create_table_sql(table_schema),
            "clean_sql": render_h2_clean_sql(context["table_name"]),
        },
        "menu_plan": menu_plan,
        "dict_plan": dict_plan,
    }


def write_codegen_sql_bundle(
    sql_bundle: dict[str, Any],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    backend_repo_root = Path(sql_bundle["backend_repo_root"])

    mysql_bundle = sql_bundle["mysql"]
    mysql_result = write_mysql_migration(
        backend_repo_root,
        mysql_bundle["migration_name"],
        mysql_bundle["content"],
        overwrite=overwrite,
    )
    mysql_result["kind"] = "mysql_migration"
    results.append(mysql_result)

    h2_bundle = sql_bundle["h2"]
    if not h2_bundle.get("resolved"):
        results.append(
            {
                "ok": False,
                "kind": "h2_create_tables",
                "path": h2_bundle.get("create_tables_path"),
                "message": h2_bundle.get("message", "未能定位 H2 SQL 文件"),
            }
        )
        results.append(
            {
                "ok": False,
                "kind": "h2_clean",
                "path": h2_bundle.get("clean_path"),
                "message": h2_bundle.get("message", "未能定位 H2 SQL 文件"),
            }
        )
        return {
            "ok": False,
            "results": results,
        }

    create_result = merge_sql_snippet(
        Path(h2_bundle["create_tables_path"]),
        marker=build_h2_create_marker(sql_bundle["menu_plan"]["table_name"]),
        content=h2_bundle["create_sql"],
    )
    create_result["kind"] = "h2_create_tables"
    results.append(create_result)

    clean_result = merge_sql_snippet(
        Path(h2_bundle["clean_path"]),
        marker=build_h2_clean_marker(sql_bundle["menu_plan"]["table_name"]),
        content=h2_bundle["clean_sql"],
    )
    clean_result["kind"] = "h2_clean"
    results.append(clean_result)

    return {
        "ok": all(result["ok"] for result in results),
        "results": results,
    }


def resolve_h2_sql_plan(
    backend_repo_root: Path,
    module_name: str,
    module_dir_name: str | None = None,
) -> dict[str, Any]:
    module_dir_name = module_dir_name or f"yudao-module-{module_name}"
    create_candidates = sorted(
        backend_repo_root.glob(f"**/{module_dir_name}/src/test/resources/sql/create_tables.sql")
    )
    paired_candidates = [
        candidate
        for candidate in create_candidates
        if candidate.with_name("clean.sql").exists()
    ]
    if len(paired_candidates) != 1:
        module_root = backend_repo_root / module_dir_name
        if module_root.is_dir():
            create_path, clean_path = ensure_h2_sql_files(module_root)
            return {
                "resolved": True,
                "module_name": module_name,
                "create_tables_path": str(create_path),
                "clean_path": str(clean_path),
                "message": "模块测试 SQL 文件不存在，已自动创建基础文件",
            }
        return {
            "resolved": False,
            "module_name": module_name,
            "create_tables_path": None,
            "clean_path": None,
            "message": "未能唯一定位模块测试 SQL 文件，请检查后端模块结构",
            "candidates": [str(candidate) for candidate in paired_candidates],
        }

    create_path = paired_candidates[0]
    clean_path = create_path.with_name("clean.sql")
    return {
        "resolved": True,
        "module_name": module_name,
        "create_tables_path": str(create_path),
        "clean_path": str(clean_path),
        "message": "已定位模块测试 SQL 文件",
    }


def ensure_h2_sql_files(module_root: Path) -> tuple[Path, Path]:
    sql_dir = module_root / "src" / "test" / "resources" / "sql"
    sql_dir.mkdir(parents=True, exist_ok=True)
    create_path = sql_dir / "create_tables.sql"
    clean_path = sql_dir / "clean.sql"
    for path in (create_path, clean_path):
        if not path.exists():
            path.write_text("", encoding="utf-8")
    return create_path, clean_path


def build_menu_plan(
    context: dict[str, Any],
    *,
    module_menu_name: str | None = None,
    menu_name: str | None = None,
    menu_icon: str | None = None,
    module_menu_icon: str | None = None,
) -> dict[str, Any]:
    sql_dump_path = Path(context["menu_context"]["sql_dump_path"])
    menus = load_system_menus(sql_dump_path) if sql_dump_path.exists() else []
    menus_by_id = {
        coerce_int(menu.get("id")): menu
        for menu in menus
        if coerce_int(menu.get("id")) is not None
    }
    resolved_root = resolve_module_root_menu(
        menus,
        menus_by_id,
        module_name=context["module_name"],
        requested_parent_menu_name=context["menu_context"].get("requested_parent_menu_name"),
        requested_parent_menu_id=context["menu_context"].get("requested_parent_menu_id"),
    )

    module_root_name = (
        str(module_menu_name).strip()
        if module_menu_name and str(module_menu_name).strip()
        else infer_missing_root_menu_name(context, resolved_root, menu_name)
    )
    table_comment = str(context["table_schema"].get("table_comment") or context["entity_name"])
    raw_menu_name = resolve_business_menu_label_source(context, menu_name, table_comment)
    menu_label = normalize_business_menu_name(raw_menu_name)
    button_prefix_name = strip_management_suffix(menu_label)
    business_menu_path = normalize_snake_case(
        context["generated_file_plan"]["simple_class_name"]
    ).replace("_", "-")
    component_path = (
        f"{context['module_name']}/"
        f"{context['generated_file_plan']['frontend_business_path']}/index"
    ).replace("//", "/")
    permission_prefix = build_permission_prefix(context["module_name"], context["entity_name"])

    root_sort = (
        coerce_int((resolved_root or {}).get("sort"))
        if resolved_root
        else compute_next_root_sort(menus)
    )
    root_icon = resolve_root_menu_icon(
        module_name=context["module_name"],
        explicit_icon=module_menu_icon,
        resolved_root=resolved_root,
    )
    business_icon = resolve_business_menu_icon(
        menus,
        root_menu=resolved_root,
        module_name=context["module_name"],
        business_name=context["business_name"],
        entity_name=context["entity_name"],
        menu_name=menu_label,
        component_path=component_path,
        business_path=business_menu_path,
        explicit_icon=menu_icon,
        fallback_icon=root_icon,
    )

    root_menu = {
        "id": (resolved_root or {}).get("id"),
        "exists": resolved_root is not None,
        "name": module_root_name,
        "type": 1,
        "sort": root_sort,
        "parent_id": 0,
        "path": f"/{context['module_name']}",
        "icon": root_icon,
        "component": None,
        "component_name": None,
        "lookup_paths": [f"/{context['module_name']}", context["module_name"]],
    }

    resolved_business = find_existing_business_menu(
        menus,
        root_menu_id=coerce_int((resolved_root or {}).get("id")),
        component_path=component_path,
        menu_path=business_menu_path,
    )
    business_menu = {
        "id": (resolved_business or {}).get("id"),
        "exists": resolved_business is not None,
        "name": menu_label,
        "type": 2,
        "sort": 0,
        "path": business_menu_path,
        "icon": business_icon,
        "component": component_path,
        "component_name": context["generated_file_plan"]["simple_class_name"],
        "permission": "",
    }

    existing_permissions = {
        str(menu.get("permission") or "")
        for menu in menus
        if str(menu.get("permission") or "").strip()
    }
    buttons = [
        {
            "name": f"{button_prefix_name}{button_name}",
            "permission": f"{permission_prefix}:{button_permission}",
            "exists": f"{permission_prefix}:{button_permission}" in existing_permissions,
            "type": 3,
            "sort": index,
            "path": "",
            "icon": "",
            "component": "",
            "component_name": None,
        }
        for index, (button_name, button_permission) in enumerate(MENU_BUTTONS, start=1)
    ]

    needs_create_root = resolved_root is None
    needs_create_business = resolved_business is None
    needs_create_buttons = any(not btn["exists"] for btn in buttons)

    return {
        "table_name": context["table_name"],
        "module_name": context["module_name"],
        "module_menu_name": module_root_name,
        "menu_name": menu_label,
        "button_prefix_name": button_prefix_name,
        "permission_prefix": permission_prefix,
        "root_menu": root_menu,
        "business_menu": business_menu,
        "buttons": buttons,
        "resolved_root_menu": resolved_root,
        "needs_create_root_menu": needs_create_root,
        "needs_create_business_menu": needs_create_business,
        "needs_create_buttons": needs_create_buttons,
        "all_menus_exist": not needs_create_root and not needs_create_business and not needs_create_buttons,
    }


def find_existing_business_menu(
    menus: list[dict[str, Any]],
    *,
    root_menu_id: int | None,
    component_path: str,
    menu_path: str,
) -> dict[str, Any] | None:
    """Check if a business menu already exists in the SQL dump by component or path."""
    for menu in menus:
        if menu.get("type") != 2:
            continue
        if str(menu.get("component") or "") == component_path:
            return menu
        if root_menu_id is not None and coerce_int(menu.get("parent_id")) == root_menu_id:
            if normalize_menu_path(str(menu.get("path") or "")) == normalize_menu_path(menu_path):
                return menu
    return None


def infer_missing_root_menu_name(
    context: dict[str, Any],
    resolved_root: dict[str, Any] | None,
    requested_menu_name: str | None,
) -> str:
    if resolved_root and str(resolved_root.get("name") or "").strip():
        return str(resolved_root["name"]).strip()

    module_hint = infer_module_menu_name(context)
    if module_hint:
        return module_hint

    table_schema = context.get("table_schema") or {}
    for value in (
        requested_menu_name,
        table_schema.get("table_comment"),
        context.get("menu_name"),
    ):
        if not isinstance(value, str):
            continue
        normalized = strip_management_suffix(normalize_business_menu_name(value))
        if contains_cjk(normalized):
            return normalized
    return str(context["module_name"]).strip()


def contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def infer_module_menu_name(context: dict[str, Any]) -> str | None:
    for key in (
        str(context.get("configured_module_name") or ""),
        str(context.get("module_name") or ""),
    ):
        normalized = normalize_snake_case(key)
        if normalized in MODULE_MENU_NAME_HINTS:
            return MODULE_MENU_NAME_HINTS[normalized]
    return None


def resolve_business_menu_label_source(
    context: dict[str, Any],
    requested_menu_name: str | None,
    table_comment: str,
) -> str:
    if requested_menu_name and requested_menu_name.strip():
        return requested_menu_name.strip()

    module_label = infer_module_menu_name(context)
    business_hint = infer_business_menu_name(context)
    if business_hint:
        suffix = extract_table_comment_suffix(table_comment, module_label, business_hint)
        return f"{business_hint} {suffix}".strip() if suffix else business_hint

    return str(table_comment or context["entity_name"]).strip()


def infer_business_menu_name(context: dict[str, Any]) -> str | None:
    business_name = normalize_snake_case(str(context.get("business_name") or ""))
    for part in business_name.split("_"):
        if part in BUSINESS_NAME_HINTS:
            return BUSINESS_NAME_HINTS[part]
    return None


def extract_table_comment_suffix(
    table_comment: str,
    module_label: str | None,
    business_label: str,
) -> str:
    cleaned = strip_management_suffix(normalize_business_menu_name(str(table_comment or "")))
    for prefix in (
        strip_management_suffix(module_label or ""),
        business_label,
    ):
        if prefix and cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned


def resolve_module_root_menu(
    menus: list[dict[str, Any]],
    menus_by_id: dict[int, dict[str, Any]],
    *,
    module_name: str,
    requested_parent_menu_name: str | None,
    requested_parent_menu_id: int | None,
) -> dict[str, Any] | None:
    explicit_parent = None
    if requested_parent_menu_id is not None:
        explicit_parent = menus_by_id.get(requested_parent_menu_id)
    elif requested_parent_menu_name:
        explicit_parent = next(
            (menu for menu in menus if str(menu.get("name") or "") == requested_parent_menu_name),
            None,
        )
    if explicit_parent is not None:
        return ascend_to_root_menu(explicit_parent, menus_by_id)

    direct_candidates = [
        menu
        for menu in menus
        if coerce_int(menu.get("parent_id")) == 0
        and normalize_menu_path(str(menu.get("path") or "")) == module_name
    ]
    if direct_candidates:
        return sort_menu_candidates(direct_candidates)[0]

    inferred_roots: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for menu in menus:
        component = str(menu.get("component") or "")
        if not component.startswith(f"{module_name}/"):
            continue
        root_menu = ascend_to_root_menu(menu, menus_by_id)
        root_id = coerce_int((root_menu or {}).get("id"))
        if root_menu is None or root_id is None or root_id in seen_ids:
            continue
        seen_ids.add(root_id)
        inferred_roots.append(root_menu)
    if inferred_roots:
        return sort_menu_candidates(inferred_roots)[0]
    return None


def ascend_to_root_menu(
    menu: dict[str, Any], menus_by_id: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    current = menu
    while coerce_int(current.get("parent_id")) not in {None, 0}:
        parent = menus_by_id.get(coerce_int(current.get("parent_id")))
        if parent is None:
            break
        current = parent
    return current


def sort_menu_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: (
            coerce_int(item.get("sort")) or 0,
            coerce_int(item.get("id")) or 0,
        ),
    )


def normalize_menu_path(path: str) -> str:
    return path.strip().strip("/")


def compute_next_root_sort(menus: list[dict[str, Any]]) -> int:
    top_level_sorts = [
        coerce_int(menu.get("sort")) or 0
        for menu in menus
        if coerce_int(menu.get("parent_id")) == 0
    ]
    if not top_level_sorts:
        return 10
    current_max = max(top_level_sorts)
    return ((current_max // 10) + 1) * 10


def resolve_root_menu_icon(
    *,
    module_name: str,
    explicit_icon: str | None,
    resolved_root: dict[str, Any] | None,
) -> str:
    if explicit_icon and explicit_icon.strip():
        return explicit_icon.strip()
    if resolved_root and str(resolved_root.get("icon") or "").strip():
        return str(resolved_root["icon"]).strip()
    return ROOT_MENU_ICON_HINTS.get(module_name, "ep:menu")


def resolve_business_menu_icon(
    menus: list[dict[str, Any]],
    *,
    root_menu: dict[str, Any] | None,
    module_name: str,
    business_name: str,
    entity_name: str,
    menu_name: str,
    component_path: str,
    business_path: str,
    explicit_icon: str | None,
    fallback_icon: str,
) -> str:
    if explicit_icon and explicit_icon.strip():
        return explicit_icon.strip()

    existing_icon = find_existing_business_icon(
        menus,
        root_menu=root_menu,
        component_path=component_path,
        business_path=business_path,
        keywords=extract_business_icon_keywords(business_name, entity_name, menu_name),
    )
    if existing_icon:
        return existing_icon

    hinted_icon = infer_icon_from_keywords(
        extract_business_icon_keywords(business_name, entity_name, menu_name)
    )
    if hinted_icon:
        return hinted_icon
    return fallback_icon or "ep:menu"


def find_existing_business_icon(
    menus: list[dict[str, Any]],
    *,
    root_menu: dict[str, Any] | None,
    component_path: str,
    business_path: str,
    keywords: list[str],
) -> str | None:
    root_id = coerce_int((root_menu or {}).get("id"))
    candidates = [
        menu
        for menu in menus
        if menu.get("type") == 2
        and str(menu.get("icon") or "").strip()
        and str(menu.get("icon") or "").strip() != "#"
    ]

    for candidate in candidates:
        if str(candidate.get("component") or "") == component_path:
            return str(candidate["icon"]).strip()
        if normalize_menu_path(str(candidate.get("path") or "")) == normalize_menu_path(business_path):
            return str(candidate["icon"]).strip()

    scored: list[tuple[int, dict[str, Any]]] = []
    for candidate in candidates:
        score = 0
        keyword_hits = 0
        haystack = " ".join(
            [
                str(candidate.get("name") or ""),
                str(candidate.get("path") or ""),
                str(candidate.get("component") or ""),
                str(candidate.get("component_name") or ""),
            ]
        ).lower()
        for keyword in keywords:
            if keyword.lower() in haystack:
                keyword_hits += 1
                score += 3
        if keyword_hits == 0:
            continue
        if root_id is not None and coerce_int(candidate.get("parent_id")) == root_id:
            score += 10
        if score > 0:
            scored.append((score, candidate))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], coerce_int(item[1].get("sort")) or 0, coerce_int(item[1].get("id")) or 0))
    return str(scored[0][1]["icon"]).strip()


def extract_icon_keywords(
    module_name: str, business_name: str, entity_name: str, menu_name: str
) -> list[str]:
    raw_values = [
        module_name,
        business_name,
        entity_name,
        normalize_snake_case(entity_name),
        menu_name,
        strip_management_suffix(menu_name),
    ]
    keywords: list[str] = []
    for raw in raw_values:
        text = str(raw or "").strip()
        if not text:
            continue
        normalized = normalize_snake_case(text)
        if normalized:
            keywords.extend([part for part in normalized.split("_") if part])
        keywords.append(text.lower())
    deduped: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        if keyword in seen:
            continue
        seen.add(keyword)
        deduped.append(keyword)
    return deduped


def extract_business_icon_keywords(
    business_name: str, entity_name: str, menu_name: str
) -> list[str]:
    return extract_icon_keywords("", business_name, entity_name, menu_name)


def infer_icon_from_keywords(keywords: list[str]) -> str | None:
    for keyword in keywords:
        if keyword in BUSINESS_MENU_ICON_HINTS:
            return BUSINESS_MENU_ICON_HINTS[keyword]
    return None


def normalize_business_menu_name(value: str) -> str:
    normalized = value.strip()
    for suffix in ("信息表", "信息", "表"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            normalized = normalized[: -len(suffix)].strip()
            break
    if normalized.endswith("管理"):
        return normalized
    return f"{normalized}管理"


def strip_management_suffix(value: str) -> str:
    return value[:-2] if value.endswith("管理") else value


def render_mysql_menu_sql(menu_plan: dict[str, Any]) -> str:
    root_menu = menu_plan["root_menu"]
    business_menu = menu_plan["business_menu"]
    buttons = menu_plan["buttons"]

    root_name = escape_sql_string(root_menu["name"])
    root_path = escape_sql_string(root_menu["path"])
    root_alt_path = escape_sql_string(root_menu["lookup_paths"][1])
    root_icon = escape_sql_string(root_menu["icon"])
    menu_name = escape_sql_string(business_menu["name"])
    menu_path = escape_sql_string(business_menu["path"])
    menu_icon = escape_sql_string(business_menu["icon"])
    component = escape_sql_string(business_menu["component"])
    component_name = escape_sql_string(business_menu["component_name"])

    lines = [
        "-- 模块根菜单，存在则复用，不存在则自动创建",
        "SET @rootMenuId := (",
        "    SELECT id FROM system_menu",
        "    WHERE deleted = b'0' AND parent_id = 0",
        f"      AND (path = '{root_path}' OR path = '{root_alt_path}' OR name = '{root_name}')",
        "    ORDER BY id ASC",
        "    LIMIT 1",
        ");",
        "",
        "INSERT INTO system_menu(",
        "    name, permission, type, sort, parent_id,",
        "    path, icon, component, component_name, status",
        ")",
        "SELECT",
        f"    '{root_name}', '', 1, {root_menu['sort']}, 0,",
        f"    '{root_path}', '{root_icon}', NULL, NULL, 0",
        "WHERE @rootMenuId IS NULL;",
        "",
        "SET @rootMenuId := IFNULL(@rootMenuId, LAST_INSERT_ID());",
        "",
        "-- 业务菜单，存在则跳过",
        "SET @bizMenuId := (",
        "    SELECT id FROM system_menu",
        "    WHERE deleted = b'0' AND parent_id = @rootMenuId",
        f"      AND (component = '{component}' OR path = '{menu_path}')",
        "    ORDER BY id ASC",
        "    LIMIT 1",
        ");",
        "",
        "INSERT INTO system_menu(",
        "    name, permission, type, sort, parent_id,",
        "    path, icon, component, component_name, status",
        ")",
        "SELECT",
        f"    '{menu_name}', '', 2, {business_menu['sort']}, @rootMenuId,",
        f"    '{menu_path}', '{menu_icon}', '{component}', '{component_name}', 0",
        "WHERE @bizMenuId IS NULL;",
        "",
        "SET @bizMenuId := IFNULL(@bizMenuId, LAST_INSERT_ID());",
        "",
        "-- 按钮权限，按 permission 幂等插入",
    ]

    for button in buttons:
        button_name = escape_sql_string(button["name"])
        permission = escape_sql_string(button["permission"])
        lines.extend(
            [
                "INSERT INTO system_menu(",
                "    name, permission, type, sort, parent_id,",
                "    path, icon, component, status",
                ")",
                "SELECT",
                f"    '{button_name}', '{permission}', 3, {button['sort']}, @bizMenuId,",
                "    '', '', '', 0",
                "WHERE NOT EXISTS (",
                "    SELECT 1 FROM system_menu",
                f"    WHERE deleted = b'0' AND permission = '{permission}'",
                ");",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def render_h2_create_table_sql(table_schema: dict[str, Any]) -> str:
    columns = table_schema.get("columns") or []
    table_name = str(table_schema["table_name"]).lower()
    table_comment = escape_sql_string(str(table_schema.get("table_comment") or table_name))
    primary_column = next(
        (column for column in columns if column.get("primary_key")),
        columns[0] if columns else None,
    )
    if primary_column is None:
        return ""

    lines = [f'CREATE TABLE IF NOT EXISTS "{table_name}" (']
    rendered_columns = [render_h2_column(column) for column in columns]
    lines.extend(rendered_columns)
    lines.append(f'    PRIMARY KEY ("{str(primary_column["column_name"]).lower()}")')
    lines.append(f") COMMENT '{table_comment}';")
    return "\n".join(lines) + "\n"


def render_h2_column(column: dict[str, Any]) -> str:
    column_name = str(column["column_name"]).lower()
    comment = escape_sql_string(str(column.get("column_comment") or column_name))
    sql_type = build_h2_column_type(column)
    nullable = bool(column.get("nullable"))
    primary_key = bool(column.get("primary_key"))
    java_type = str(column.get("java_type") or "")

    if primary_key:
        if java_type == "String":
            return f'    "{column_name}" {sql_type} NOT NULL COMMENT \'{comment}\','
        return (
            f'    "{column_name}" {sql_type} NOT NULL GENERATED BY DEFAULT AS IDENTITY '
            f"COMMENT '{comment}',"
        )

    if column_name == "create_time":
        return f'    "create_time" datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT \'{comment}\','
    if column_name == "update_time":
        return (
            f'    "update_time" datetime NOT NULL DEFAULT CURRENT_TIMESTAMP '
            f"ON UPDATE CURRENT_TIMESTAMP COMMENT '{comment}',"
        )
    if column_name in {"creator", "updater"}:
        return f'    "{column_name}" varchar(64) DEFAULT \'\' COMMENT \'{comment}\','
    if column_name == "deleted":
        return f'    "deleted" bit NOT NULL DEFAULT FALSE COMMENT \'{comment}\','
    if column_name == "tenant_id":
        return f'    "tenant_id" bigint NOT NULL DEFAULT 0 COMMENT \'{comment}\','

    not_null = " NOT NULL" if not nullable else ""
    return f'    "{column_name}" {sql_type}{not_null} COMMENT \'{comment}\','


def build_h2_column_type(column: dict[str, Any]) -> str:
    raw_type = str(column.get("raw_type") or "").strip().lower()
    sql_type = str(column.get("sql_type") or "").strip().lower()
    if raw_type.startswith("varchar("):
        return raw_type
    if raw_type.startswith("char("):
        return raw_type
    if raw_type.startswith("decimal(") or raw_type.startswith("numeric("):
        return raw_type
    if raw_type.startswith("bit("):
        return "bit"
    if sql_type in {"tinyint", "smallint", "int", "integer", "bigint", "double", "float"}:
        return sql_type if sql_type != "integer" else "int"
    if sql_type in {"decimal", "numeric"}:
        return raw_type or "decimal(10,2)"
    if sql_type in {"datetime", "timestamp"}:
        return "datetime"
    if sql_type == "date":
        return "date"
    if sql_type == "time":
        return "time"
    if sql_type in {"text", "mediumtext", "longtext", "json"}:
        return "varchar(4000)"
    if raw_type:
        return raw_type
    return "varchar(255)"


def render_h2_clean_sql(table_name: str) -> str:
    return f'DELETE FROM "{table_name.lower()}";\n'


def build_h2_create_marker(table_name: str) -> str:
    return f'CREATE TABLE IF NOT EXISTS "{table_name.lower()}"'


def build_h2_clean_marker(table_name: str) -> str:
    return f'DELETE FROM "{table_name.lower()}";'


def merge_sql_snippet(file_path: Path, *, marker: str, content: str) -> dict[str, Any]:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    existing = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    if marker in existing:
        return {
            "ok": True,
            "path": str(file_path),
            "message": "SQL 片段已存在，跳过写入",
            "written": False,
        }

    block = content.strip()
    merged = existing.rstrip()
    if merged:
        merged += "\n\n"
    merged += block + "\n"
    file_path.write_text(merged, encoding="utf-8")
    return {
        "ok": True,
        "path": str(file_path),
        "message": "SQL 片段已合并写入",
        "written": True,
    }


def escape_sql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def build_dict_plan(
    context: dict[str, Any],
    sql_dump_path: Path | None = None,
) -> dict[str, Any]:
    """Build a dict data generation plan by parsing column comments for enum patterns."""
    table_schema = context.get("table_schema") or {}
    columns = table_schema.get("columns") or []
    table_name = context.get("table_name", "")
    table_comment = str(table_schema.get("table_comment") or table_name)

    dict_fields = extract_dict_fields(columns, table_name, table_comment)
    if not dict_fields:
        return {
            "ok": True,
            "has_dicts": False,
            "message": "未检测到需要生成的字典数据",
            "dict_types": [],
        }

    existing_types: dict[str, dict[str, Any]] = {}
    existing_data: dict[str, list[dict[str, Any]]] = {}
    if sql_dump_path and Path(sql_dump_path).exists():
        existing_types = load_dict_types_from_sql(Path(sql_dump_path))
        existing_data = load_dict_data_from_sql(Path(sql_dump_path))

    dict_types: list[dict[str, Any]] = []
    for field in dict_fields:
        dt_key = field["dict_type"]
        type_exists = dt_key in existing_types
        existing_items = existing_data.get(dt_key, [])
        existing_values = {str(item.get("value", "")) for item in existing_items}

        missing_items = [
            item for item in field["items"]
            if str(item["value"]) not in existing_values
        ]

        dict_types.append({
            "dict_type": dt_key,
            "dict_name": field["dict_name"],
            "column_name": field["column_name"],
            "java_field": field["java_field"],
            "ts_type": field["ts_type"],
            "type_exists": type_exists,
            "items": field["items"],
            "existing_items": existing_items,
            "missing_items": missing_items,
            "needs_create_type": not type_exists,
            "needs_create_data": len(missing_items) > 0,
            "all_complete": type_exists and len(missing_items) == 0,
        })

    all_complete = all(dt["all_complete"] for dt in dict_types)

    return {
        "ok": True,
        "has_dicts": True,
        "all_complete": all_complete,
        "message": "所有字典数据已存在且完整" if all_complete else "检测到需要生成的字典数据",
        "dict_types": dict_types,
    }


def load_dict_types_from_sql(sql_dump_path: Path) -> dict[str, dict[str, Any]]:
    """Load existing dict types from the SQL dump file."""
    types: dict[str, dict[str, Any]] = {}
    for line in sql_dump_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith("INSERT INTO `system_dict_type`"):
            continue
        values_text = line.partition("VALUES")[2].strip().rstrip(";")
        for row_text in split_sql_value_rows(values_text):
            values = split_sql_values(row_text)
            if len(values) < 4:
                continue
            dict_id = coerce_int(parse_sql_scalar(values[0]))
            name = parse_sql_scalar(values[1])
            type_key = parse_sql_scalar(values[2])
            if type_key:
                types[str(type_key)] = {
                    "id": dict_id,
                    "name": name,
                    "type": type_key,
                }
    return types


def load_dict_data_from_sql(sql_dump_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load existing dict data items grouped by dict_type from the SQL dump file."""
    data: dict[str, list[dict[str, Any]]] = {}
    for line in sql_dump_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith("INSERT INTO `system_dict_data`"):
            continue
        values_text = line.partition("VALUES")[2].strip().rstrip(";")
        for row_text in split_sql_value_rows(values_text):
            values = split_sql_values(row_text)
            if len(values) < 5:
                continue
            dict_id = coerce_int(parse_sql_scalar(values[0]))
            sort_val = coerce_int(parse_sql_scalar(values[1]))
            label = parse_sql_scalar(values[2])
            value = parse_sql_scalar(values[3])
            dict_type = parse_sql_scalar(values[4])
            if dict_type:
                data.setdefault(str(dict_type), []).append({
                    "id": dict_id,
                    "sort": sort_val,
                    "label": label,
                    "value": value,
                    "dict_type": dict_type,
                })
    return data


def render_dict_migration_sql(dict_plan: dict[str, Any]) -> str:
    """Render idempotent INSERT SQL for dict types and dict data items."""
    dict_types = dict_plan.get("dict_types") or []
    if not dict_types:
        return ""

    lines: list[str] = [
        "-- 字典类型与字典数据，由 Yudao Pilot 自动生成",
        "",
    ]

    for dt in dict_types:
        dt_key = escape_sql_string(dt["dict_type"])
        dt_name = escape_sql_string(dt["dict_name"])

        lines.append(f"-- 字典类型: {dt['dict_name']} ({dt['dict_type']})")
        lines.extend([
            "INSERT INTO system_dict_type(",
            "    name, type, status, remark,",
            "    creator, create_time, updater, update_time, deleted",
            ")",
            "SELECT",
            f"    '{dt_name}', '{dt_key}', 0, NULL,",
            "    'yudao-pilot', NOW(), 'yudao-pilot', NOW(), b'0'",
            "WHERE NOT EXISTS (",
            f"    SELECT 1 FROM system_dict_type WHERE type = '{dt_key}' AND deleted = b'0'",
            ");",
            "",
        ])

        for item in dt["items"]:
            item_label = escape_sql_string(str(item["label"]))
            item_value = escape_sql_string(str(item["value"]))
            color_type = escape_sql_string(str(item.get("color_type", "")))
            sort_val = item.get("sort", 0)

            lines.extend([
                "INSERT INTO system_dict_data(",
                "    sort, label, value, dict_type, status, color_type, css_class, remark,",
                "    creator, create_time, updater, update_time, deleted",
                ")",
                "SELECT",
                f"    {sort_val}, '{item_label}', '{item_value}', '{dt_key}', 0, '{color_type}', '', NULL,",
                "    'yudao-pilot', NOW(), 'yudao-pilot', NOW(), b'0'",
                "WHERE NOT EXISTS (",
                f"    SELECT 1 FROM system_dict_data WHERE dict_type = '{dt_key}' AND value = '{item_value}' AND deleted = b'0'",
                ");",
                "",
            ])

    return "\n".join(lines).rstrip() + "\n"


ROOT_MENU_ICON_HINTS: dict[str, str] = {
    "system": "ep:tools",
    "infra": "ep:monitor",
    "member": "ep:bicycle",
    "mall": "lucide:shopping-bag",
    "pay": "lucide:badge-japanese-yen",
    "bpm": "carbon:flow-connection",
    "crm": "simple-icons:civicrm",
    "iot": "lucide:cpu",
    "report": "ep:data-analysis",
    "ai": "tabler:ai",
}


BUSINESS_MENU_ICON_HINTS: dict[str, str] = {
    "user": "ep:avatar",
    "member": "ep:avatar",
    "account": "ep:user",
    "merchant": "ep:shop",
    "shop": "ep:shop",
    "store": "ep:shop",
    "tag": "ep:collection-tag",
    "level": "fa:level-up",
    "group": "fa:group",
    "config": "fa:connectdevelop",
    "codegen": "ep:document-copy",
    "job": "fa-solid:tasks",
    "dict": "ep:collection",
    "notice": "ep:bell",
    "message": "ant-design:message-filled",
    "order": "ep:tickets",
    "trade": "ep:sold-out",
    "product": "ep:goods",
    "goods": "ep:goods",
    "coupon": "ep:present",
    "point": "fa:asterisk",
    "record": "ep:document",
    "role": "ep:user",
    "dept": "fa:address-card",
}
