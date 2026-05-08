from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import WorkspaceConfig
from .inspector import resolve_backend_server_root, resolve_project_path
from .models import DatabaseConfig


def resolve_database_config(
    workspace_root: str | Path, config: WorkspaceConfig
) -> dict[str, Any]:
    resolved = DatabaseConfig.model_validate(config.database.model_dump())
    if config.database.mode == "manual" and config.database.has_manual_values():
        resolved.source = "config"
        return {"ok": True, "database": resolved.model_dump(), "message": "使用工作区配置中的数据库连接"}

    if config.database.has_manual_values():
        resolved.source = "config"
        return {"ok": True, "database": resolved.model_dump(), "message": "优先使用工作区配置中的数据库连接"}

    backend_root = resolve_project_path(Path(workspace_root).resolve(), config.projects.backend.path)
    backend_db = read_backend_local_database(backend_root, config.projects.backend.config_profile)
    if backend_db is None:
        resolved.source = "none"
        return {
            "ok": False,
            "database": resolved.model_dump(),
            "message": "未能从后端本地配置中解析出数据库连接信息",
        }

    merged = DatabaseConfig(
        mode=config.database.mode,
        host=resolved.host or backend_db.get("host", ""),
        port=resolved.port if has_database_override(resolved, "port") else backend_db.get("port", 3306),
        database=resolved.database or backend_db.get("database", ""),
        username=resolved.username or backend_db.get("username", ""),
        password=resolved.password or backend_db.get("password", ""),
        source="config" if has_any_database_override(resolved) else "backend-local",
    )
    message = (
        "已合并工作区配置与后端本地数据库连接"
        if has_any_database_override(resolved)
        else "已从后端本地配置解析数据库连接"
    )
    return {"ok": True, "database": merged.model_dump(), "message": message}


def read_backend_local_database(
    backend_root: Path, config_profile: str
) -> dict[str, Any] | None:
    server_root = resolve_backend_server_root(backend_root)
    resource_root = server_root / "src" / "main" / "resources"
    candidates = unique_paths(
        [
            resource_root / "application.yaml",
            resource_root / "application.yml",
            resource_root / "application-local.yaml",
            resource_root / "application-local.yml",
            resource_root / f"application-{config_profile}.yaml",
            resource_root / f"application-{config_profile}.yml",
        ]
    )

    for file_path in candidates:
        if not file_path.exists():
            continue
        raw_data = load_yaml_documents(file_path)
        resolved = extract_database_from_spring_config(raw_data)
        if resolved:
            return resolved
    return None


def load_yaml_documents(file_path: Path) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    raw_text = file_path.read_text(encoding="utf-8")
    for document in yaml.safe_load_all(raw_text):
        if isinstance(document, dict):
            merged = deep_merge_dicts(merged, document)
    return merged


def extract_database_from_spring_config(raw_data: dict[str, Any]) -> dict[str, Any] | None:
    spring = raw_data.get("spring")
    if not isinstance(spring, dict):
        return None

    datasource = spring.get("datasource")
    if not isinstance(datasource, dict):
        return None

    direct = normalize_jdbc_config(datasource)
    if direct:
        return direct

    dynamic = datasource.get("dynamic")
    if isinstance(dynamic, dict):
        dynamic_sources = dynamic.get("datasource")
        if isinstance(dynamic_sources, dict):
            preferred_names: list[str] = []
            primary_name = stringify_scalar(dynamic.get("primary"))
            if primary_name:
                preferred_names.append(primary_name)
            preferred_names.extend(["master", "primary", "default"])
            for candidate_name in deduplicate_values(preferred_names):
                candidate = dynamic_sources.get(candidate_name)
                if isinstance(candidate, dict):
                    resolved = normalize_jdbc_config(candidate)
                    if resolved:
                        return resolved
            for candidate in dynamic_sources.values():
                if isinstance(candidate, dict):
                    resolved = normalize_jdbc_config(candidate)
                    if resolved:
                        return resolved
    return None


def normalize_jdbc_config(raw_config: dict[str, Any]) -> dict[str, Any] | None:
    url = raw_config.get("url")
    username = stringify_scalar(raw_config.get("username"))
    password = stringify_scalar(raw_config.get("password"), default="")
    if not isinstance(url, str) or username is None or password is None:
        return None

    host, port, database = parse_mysql_jdbc_url(url)
    return {
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password": password,
    }


def parse_mysql_jdbc_url(url: str) -> tuple[str, int, str]:
    prefix = "jdbc:mysql://"
    if not url.startswith(prefix):
        return "", 3306, ""

    remainder = url[len(prefix):]
    host_port, _, tail = remainder.partition("/")
    host, _, port_text = host_port.partition(":")
    database = tail.partition("?")[0]
    try:
        port = int(port_text) if port_text else 3306
    except ValueError:
        port = 3306
    return host, port, database


def deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def stringify_scalar(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def deduplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def has_any_database_override(config: DatabaseConfig) -> bool:
    return bool(
        config.host
        or config.database
        or config.username
        or config.password
        or has_database_override(config, "port")
    )


def has_database_override(config: DatabaseConfig, field_name: str) -> bool:
    if field_name == "port":
        return config.port != 3306
    return bool(getattr(config, field_name))


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def import_pymysql() -> Any:
    import pymysql

    return pymysql


def apply_menu_plan_to_database(
    database_config: dict[str, Any] | DatabaseConfig,
    menu_plan: dict[str, Any],
) -> dict[str, Any]:
    config = (
        database_config
        if isinstance(database_config, DatabaseConfig)
        else DatabaseConfig.model_validate(database_config)
    )
    pymysql = import_pymysql()
    connection = pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.username,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    root_menu = menu_plan["root_menu"]
    business_menu = menu_plan["business_menu"]
    buttons = menu_plan["buttons"]
    try:
        with connection.cursor() as cursor:
            root_id, root_status = ensure_root_menu(cursor, root_menu)
            if root_status == "created":
                created.append(f"根菜单:{root_menu['name']}")
            elif root_status == "updated":
                updated.append(f"根菜单:{root_menu['name']}")
            else:
                skipped.append(f"根菜单:{root_menu['name']}")

            business_id, business_status = ensure_business_menu(cursor, root_id, business_menu)
            if business_status == "created":
                created.append(f"业务菜单:{business_menu['name']}")
            elif business_status == "updated":
                updated.append(f"业务菜单:{business_menu['name']}")
            else:
                skipped.append(f"业务菜单:{business_menu['name']}")

            for button in buttons:
                _, button_created = ensure_button_menu(cursor, business_id, button)
                label = f"按钮:{button['permission']}"
                if button_created:
                    created.append(label)
                else:
                    skipped.append(label)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return {
        "ok": True,
        "database": config.database,
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


def ensure_root_menu(cursor: Any, menu: dict[str, Any]) -> tuple[int, str]:
    cursor.execute(
        """
        SELECT id, name, path, icon
        FROM system_menu
        WHERE deleted = b'0'
          AND parent_id = 0
          AND (path = %s OR path = %s OR name = %s)
        ORDER BY id ASC
        LIMIT 1
        """,
        (menu["lookup_paths"][0], menu["lookup_paths"][1], menu["name"]),
    )
    existing = cursor.fetchone()
    if existing:
        status = sync_existing_root_menu(cursor, existing, menu)
        return int(existing["id"]), status

    cursor.execute(
        """
        SELECT COALESCE(MAX(sort), 0) AS max_sort
        FROM system_menu
        WHERE deleted = b'0' AND parent_id = 0
        """
    )
    sort_row = cursor.fetchone() or {}
    sort_value = max(int(sort_row.get("max_sort") or 0) + 10, int(menu["sort"]))
    cursor.execute(
        """
        INSERT INTO system_menu(
            name, permission, type, sort, parent_id,
            path, icon, component, component_name, status,
            visible, keep_alive, always_show, creator, updater, deleted
        )
        VALUES (
            %s, '', 1, %s, 0,
            %s, %s, NULL, NULL, 0,
            b'1', b'1', b'1', %s, %s, b'0'
        )
        """,
        (menu["name"], sort_value, menu["path"], menu["icon"], "yudao-pilot", "yudao-pilot"),
    )
    return int(cursor.lastrowid), "created"


def ensure_business_menu(
    cursor: Any, parent_id: int, menu: dict[str, Any]
) -> tuple[int, str]:
    cursor.execute(
        """
        SELECT id, parent_id, name, path, icon, component, component_name
        FROM system_menu
        WHERE deleted = b'0'
          AND parent_id = %s
          AND (component = %s OR path = %s)
        ORDER BY id ASC
        LIMIT 1
        """,
        (parent_id, menu["component"], menu["path"]),
    )
    existing = cursor.fetchone()
    if existing:
        status = sync_existing_business_menu(cursor, existing, parent_id, menu)
        return int(existing["id"]), status

    cursor.execute(
        """
        INSERT INTO system_menu(
            name, permission, type, sort, parent_id,
            path, icon, component, component_name, status,
            visible, keep_alive, always_show, creator, updater, deleted
        )
        VALUES (
            %s, '', 2, %s, %s,
            %s, %s, %s, %s, 0,
            b'1', b'1', b'1', %s, %s, b'0'
        )
        """,
        (
            menu["name"],
            int(menu["sort"]),
            parent_id,
            menu["path"],
            menu["icon"],
            menu["component"],
            menu["component_name"],
            "yudao-pilot",
            "yudao-pilot",
        ),
    )
    return int(cursor.lastrowid), "created"


def ensure_button_menu(
    cursor: Any, parent_id: int, button: dict[str, Any]
) -> tuple[int, bool]:
    cursor.execute(
        """
        SELECT id
        FROM system_menu
        WHERE deleted = b'0' AND permission = %s
        ORDER BY id ASC
        LIMIT 1
        """,
        (button["permission"],),
    )
    existing = cursor.fetchone()
    if existing:
        return int(existing["id"]), False

    cursor.execute(
        """
        INSERT INTO system_menu(
            name, permission, type, sort, parent_id,
            path, icon, component, status,
            visible, keep_alive, always_show, creator, updater, deleted
        )
        VALUES (
            %s, %s, 3, %s, %s,
            '', '', '', 0,
            b'1', b'1', b'1', %s, %s, b'0'
        )
        """,
        (
            button["name"],
            button["permission"],
            int(button["sort"]),
            parent_id,
            "yudao-pilot",
            "yudao-pilot",
        ),
    )
    return int(cursor.lastrowid), True


def apply_dict_plan_to_database(
    database_config: dict[str, Any] | DatabaseConfig,
    dict_plan: dict[str, Any],
) -> dict[str, Any]:
    """Apply dict plan to database: create missing dict types and data items."""
    dict_types = dict_plan.get("dict_types") or []
    if not dict_types:
        return {"ok": True, "created": [], "skipped": [], "message": "无需创建字典数据"}

    config = (
        database_config
        if isinstance(database_config, DatabaseConfig)
        else DatabaseConfig.model_validate(database_config)
    )
    pymysql = import_pymysql()
    connection = pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.username,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    created: list[str] = []
    skipped: list[str] = []
    data_created: list[str] = []
    data_skipped: list[str] = []

    try:
        with connection.cursor() as cursor:
            for dt in dict_types:
                type_key = dt["dict_type"]
                type_name = dt["dict_name"]

                cursor.execute(
                    "SELECT id FROM system_dict_type WHERE type = %s AND deleted = b'0' LIMIT 1",
                    (type_key,),
                )
                existing_type = cursor.fetchone()

                if existing_type:
                    skipped.append(f"字典类型:{type_key}({type_name})")
                else:
                    cursor.execute(
                        """
                        INSERT INTO system_dict_type(
                            name, type, status, remark,
                            creator, create_time, updater, update_time, deleted
                        ) VALUES (
                            %s, %s, 0, NULL,
                            'yudao-pilot', NOW(), 'yudao-pilot', NOW(), b'0'
                        )
                        """,
                        (type_name, type_key),
                    )
                    created.append(f"字典类型:{type_key}({type_name})")

                for item in dt["items"]:
                    item_value = str(item["value"])
                    item_label = str(item["label"])
                    color_type = str(item.get("color_type", ""))
                    sort_val = item.get("sort", 0)

                    cursor.execute(
                        "SELECT id FROM system_dict_data WHERE dict_type = %s AND value = %s AND deleted = b'0' LIMIT 1",
                        (type_key, item_value),
                    )
                    existing_item = cursor.fetchone()
                    if existing_item:
                        data_skipped.append(f"字典数据:{type_key}[{item_value}={item_label}]")
                    else:
                        cursor.execute(
                            """
                            INSERT INTO system_dict_data(
                                sort, label, value, dict_type, status, color_type, css_class, remark,
                                creator, create_time, updater, update_time, deleted
                            ) VALUES (
                                %s, %s, %s, %s, 0, %s, '', NULL,
                                'yudao-pilot', NOW(), 'yudao-pilot', NOW(), b'0'
                            )
                            """,
                            (sort_val, item_label, item_value, type_key, color_type),
                        )
                        data_created.append(f"字典数据:{type_key}[{item_value}={item_label}]")

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return {
        "ok": True,
        "database": config.database,
        "type_created": created,
        "type_skipped": skipped,
        "data_created": data_created,
        "data_skipped": data_skipped,
    }


def load_dict_catalog_from_database(
    database_config: dict[str, Any] | DatabaseConfig,
) -> dict[str, Any]:
    """Read active system dictionary types and data from the configured database."""
    config = (
        database_config
        if isinstance(database_config, DatabaseConfig)
        else DatabaseConfig.model_validate(database_config)
    )
    pymysql = import_pymysql()
    connection = pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.username,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, type
                FROM system_dict_type
                WHERE deleted = b'0'
                ORDER BY id ASC
                """
            )
            type_rows = cursor.fetchall() or []
            cursor.execute(
                """
                SELECT id, sort, label, value, dict_type
                FROM system_dict_data
                WHERE deleted = b'0'
                ORDER BY dict_type ASC, sort ASC, id ASC
                """
            )
            data_rows = cursor.fetchall() or []
    finally:
        connection.close()

    types: dict[str, dict[str, Any]] = {}
    for row in type_rows:
        type_key = str(row.get("type") or "")
        if not type_key:
            continue
        types[type_key] = {
            "id": row.get("id"),
            "name": row.get("name"),
            "type": type_key,
        }

    data: dict[str, list[dict[str, Any]]] = {}
    for row in data_rows:
        type_key = str(row.get("dict_type") or "")
        if not type_key:
            continue
        data.setdefault(type_key, []).append({
            "id": row.get("id"),
            "sort": row.get("sort"),
            "label": row.get("label"),
            "value": row.get("value"),
            "dict_type": type_key,
        })

    return {
        "ok": True,
        "database": config.database,
        "dict_types": types,
        "dict_data": data,
    }


def sync_existing_root_menu(cursor: Any, existing: dict[str, Any], menu: dict[str, Any]) -> str:
    updates: list[str] = []
    params: list[Any] = []

    if str(existing.get("name") or "") != str(menu["name"]):
        updates.append("name = %s")
        params.append(menu["name"])
    if str(existing.get("path") or "") != str(menu["path"]):
        updates.append("path = %s")
        params.append(menu["path"])
    if str(existing.get("icon") or "") != str(menu["icon"]):
        updates.append("icon = %s")
        params.append(menu["icon"])

    if not updates:
        return "skipped"

    updates.append("updater = %s")
    params.append("yudao-pilot")
    params.append(int(existing["id"]))
    cursor.execute(
        f"""
        UPDATE system_menu
        SET {", ".join(updates)}
        WHERE id = %s
        """,
        tuple(params),
    )
    return "updated"


def sync_existing_business_menu(
    cursor: Any, existing: dict[str, Any], parent_id: int, menu: dict[str, Any]
) -> str:
    updates: list[str] = []
    params: list[Any] = []

    if str(existing.get("name") or "") != str(menu["name"]):
        updates.append("name = %s")
        params.append(menu["name"])
    if str(existing.get("path") or "") != str(menu["path"]):
        updates.append("path = %s")
        params.append(menu["path"])
    if str(existing.get("icon") or "") != str(menu["icon"]):
        updates.append("icon = %s")
        params.append(menu["icon"])
    if str(existing.get("component") or "") != str(menu["component"]):
        updates.append("component = %s")
        params.append(menu["component"])
    if str(existing.get("component_name") or "") != str(menu["component_name"]):
        updates.append("component_name = %s")
        params.append(menu["component_name"])
    if parent_id != int(existing.get("parent_id") or parent_id):
        updates.append("parent_id = %s")
        params.append(parent_id)

    if not updates:
        return "skipped"

    updates.append("updater = %s")
    params.append("yudao-pilot")
    params.append(int(existing["id"]))
    cursor.execute(
        f"""
        UPDATE system_menu
        SET {", ".join(updates)}
        WHERE id = %s
        """,
        tuple(params),
    )
    return "updated"
