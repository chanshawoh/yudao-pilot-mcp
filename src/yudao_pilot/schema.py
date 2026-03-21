from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .inspector import resolve_backend_repo_root
from .models import DatabaseConfig


BASE_AUDIT_COLUMNS = {
    "creator",
    "create_time",
    "updater",
    "update_time",
    "deleted",
    "tenant_id",
}

INTERNAL_COLUMNS = {
    "delete_token",
}


def inspect_table_schema(
    backend_root: Path,
    table_name: str,
    database_config: dict[str, Any] | DatabaseConfig | None = None,
) -> dict[str, Any]:
    repo_root = resolve_backend_repo_root(backend_root)
    sql_dump_path = resolve_mysql_schema_dump(repo_root)
    sql_message: str | None = None
    if sql_dump_path is not None:
        schema = parse_table_schema_from_sql(sql_dump_path, table_name)
        if schema is not None:
            return schema
        sql_message = "在 SQL 结构文件中未找到目标表"
    else:
        sql_message = "未找到 MySQL 结构文件"

    normalized_db_config = normalize_database_config(database_config)
    if normalized_db_config is not None:
        try:
            runtime_schema = parse_table_schema_from_database(normalized_db_config, table_name)
        except Exception as exc:
            db_message = (
                f"尝试连接真实数据库 {normalized_db_config.database} 失败: "
                f"{exc.__class__.__name__}: {exc}"
            )
        else:
            if runtime_schema is not None:
                runtime_schema["sql_dump_path"] = str(sql_dump_path) if sql_dump_path else None
                return runtime_schema
            db_message = f"已尝试连接真实数据库 {normalized_db_config.database}，但未找到目标表"
    else:
        db_message = "未提供可用数据库连接，暂时无法回退到真实数据库解析"

    return {
        "resolved": False,
        "table_name": table_name,
        "sql_dump_path": str(sql_dump_path) if sql_dump_path else None,
        "message": f"{sql_message}；{db_message}，请 AI 结合迁移文件继续判断",
        "columns": [],
    }


def resolve_mysql_schema_dump(repo_root: Path) -> Path | None:
    mysql_root = repo_root / "sql" / "mysql"
    preferred = mysql_root / "ruoyi-vue-pro.sql"
    if preferred.exists():
        return preferred

    if not mysql_root.exists():
        return None

    for candidate in sorted(mysql_root.glob("*.sql")):
        if candidate.name.startswith("quartz"):
            continue
        return candidate
    return None


def parse_table_schema_from_sql(sql_dump_path: Path, table_name: str) -> dict[str, Any] | None:
    sql_text = sql_dump_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(
        rf"CREATE TABLE `{re.escape(table_name)}`\s*\((?P<body>.*?)\)\s*ENGINE\s*=\s*(?P<engine>[^ ]+).*?COMMENT\s*=\s*'(?P<comment>[^']*)'",
        re.S,
    )
    match = pattern.search(sql_text)
    if not match:
        return None

    body = match.group("body")
    lines = [line.strip().rstrip(",") for line in body.splitlines() if line.strip()]
    primary_keys = parse_primary_keys(lines)
    columns = [
        column
        for line in lines
        if (column := parse_column_line(line, primary_keys)) is not None
    ]
    return {
        "resolved": True,
        "table_name": table_name,
        "table_comment": match.group("comment"),
        "sql_dump_path": str(sql_dump_path),
        "schema_source": "sql-dump",
        "message": "已从 MySQL 结构文件解析表字段",
        "columns": columns,
    }


def normalize_database_config(
    database_config: dict[str, Any] | DatabaseConfig | None,
) -> DatabaseConfig | None:
    if database_config is None:
        return None
    if isinstance(database_config, DatabaseConfig):
        config = database_config
    else:
        try:
            config = DatabaseConfig.model_validate(database_config)
        except Exception:
            return None
    if not config.has_manual_values():
        return None
    return config


def parse_table_schema_from_database(
    database_config: DatabaseConfig, table_name: str
) -> dict[str, Any] | None:
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ModuleNotFoundError:
        return None

    connection = pymysql.connect(
        host=database_config.host,
        port=database_config.port,
        user=database_config.username,
        password=database_config.password,
        database=database_config.database,
        charset="utf8mb4",
        cursorclass=DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT TABLE_NAME, TABLE_COMMENT
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                """,
                (database_config.database, table_name),
            )
            table_row = cursor.fetchone()
            if not table_row:
                return None

            cursor.execute(
                """
                SELECT
                    COLUMN_NAME,
                    COLUMN_COMMENT,
                    COLUMN_TYPE,
                    DATA_TYPE,
                    IS_NULLABLE,
                    COLUMN_KEY,
                    EXTRA
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                (database_config.database, table_name),
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    columns = [parse_database_column(row) for row in rows]
    return {
        "resolved": True,
        "table_name": table_name,
        "table_comment": table_row.get("TABLE_COMMENT") or table_name,
        "sql_dump_path": None,
        "schema_source": "database",
        "database_name": database_config.database,
        "message": "已从真实数据库解析表字段",
        "columns": columns,
    }


def parse_database_column(row: dict[str, Any]) -> dict[str, Any]:
    column_name = str(row["COLUMN_NAME"])
    raw_type = str(row["COLUMN_TYPE"])
    sql_type = str(row["DATA_TYPE"]).lower()
    java_field = snake_to_camel(column_name)
    is_primary_key = str(row.get("COLUMN_KEY") or "").upper() == "PRI"
    is_base_column = column_name in BASE_AUDIT_COLUMNS
    is_internal = column_name in INTERNAL_COLUMNS
    is_auto_increment = "auto_increment" in str(row.get("EXTRA") or "").lower()
    nullable = str(row.get("IS_NULLABLE") or "").upper() == "YES"

    return {
        "column_name": column_name,
        "column_comment": str(row.get("COLUMN_COMMENT") or column_name),
        "sql_type": sql_type,
        "raw_type": raw_type,
        "java_field": java_field,
        "java_type": map_java_type(sql_type),
        "ts_type": map_ts_type(sql_type),
        "html_type": infer_html_type(column_name, sql_type),
        "nullable": nullable,
        "primary_key": is_primary_key,
        "auto_increment": is_auto_increment,
        "is_base_column": is_base_column,
        "in_do": not is_base_column and not is_internal,
        "in_save": not is_base_column and not is_primary_key and not is_internal,
        "in_resp": (not is_base_column or column_name == "create_time") and not is_internal,
        "in_list": not is_base_column and column_name not in {"description", "content"} and not is_internal,
        "in_query": is_query_column(column_name, sql_type) and (not is_base_column or column_name == "create_time") and not is_internal,
    }


def parse_primary_keys(lines: list[str]) -> set[str]:
    primary_keys: set[str] = set()
    for line in lines:
        if not line.startswith("PRIMARY KEY"):
            continue
        primary_keys.update(re.findall(r"`([^`]+)`", line))
    return primary_keys


def parse_column_line(line: str, primary_keys: set[str]) -> dict[str, Any] | None:
    if not line.startswith("`"):
        return None

    match = re.match(r"`(?P<name>[^`]+)`\s+(?P<type>[^\s]+)", line)
    if not match:
        return None

    column_name = match.group("name")
    raw_type = match.group("type")
    sql_type = raw_type.split("(", 1)[0].lower()
    column_comment = extract_sql_comment(line)
    java_field = snake_to_camel(column_name)
    java_type = map_java_type(sql_type)
    ts_type = map_ts_type(sql_type)
    html_type = infer_html_type(column_name, sql_type)
    is_primary_key = column_name in primary_keys
    is_base_column = column_name in BASE_AUDIT_COLUMNS
    is_internal = column_name in INTERNAL_COLUMNS
    is_auto_increment = "AUTO_INCREMENT" in line.upper()
    nullable = "NOT NULL" not in line.upper()

    return {
        "column_name": column_name,
        "column_comment": column_comment or column_name,
        "sql_type": sql_type,
        "raw_type": raw_type,
        "java_field": java_field,
        "java_type": java_type,
        "ts_type": ts_type,
        "html_type": html_type,
        "nullable": nullable,
        "primary_key": is_primary_key,
        "auto_increment": is_auto_increment,
        "is_base_column": is_base_column,
        "in_do": not is_base_column and not is_internal,
        "in_save": not is_base_column and not is_primary_key and not is_internal,
        "in_resp": (not is_base_column or column_name == "create_time") and not is_internal,
        "in_list": not is_base_column and column_name not in {"description", "content"} and not is_internal,
        "in_query": is_query_column(column_name, sql_type) and (not is_base_column or column_name == "create_time") and not is_internal,
    }


def extract_sql_comment(line: str) -> str:
    match = re.search(r"COMMENT\s+'([^']*)'", line)
    return match.group(1) if match else ""


def is_query_column(column_name: str, sql_type: str) -> bool:
    if column_name in {"id", "status", "type", "name", "title", "code"}:
        return True
    if column_name.endswith("_id"):
        return True
    if sql_type in {"datetime", "timestamp", "date"}:
        return True
    return False


def map_java_type(sql_type: str) -> str:
    mapping = {
        "bigint": "Long",
        "int": "Integer",
        "integer": "Integer",
        "tinyint": "Integer",
        "smallint": "Integer",
        "mediumint": "Integer",
        "bit": "Boolean",
        "boolean": "Boolean",
        "decimal": "BigDecimal",
        "numeric": "BigDecimal",
        "double": "Double",
        "float": "Float",
        "char": "String",
        "varchar": "String",
        "text": "String",
        "mediumtext": "String",
        "longtext": "String",
        "json": "String",
        "datetime": "LocalDateTime",
        "timestamp": "LocalDateTime",
        "date": "LocalDate",
        "time": "LocalTime",
    }
    return mapping.get(sql_type, "String")


def map_ts_type(sql_type: str) -> str:
    if sql_type in {"bigint", "int", "integer", "tinyint", "smallint", "mediumint", "decimal", "numeric", "double", "float"}:
        return "number"
    if sql_type in {"bit", "boolean"}:
        return "boolean"
    return "string"


def infer_html_type(column_name: str, sql_type: str) -> str:
    if column_name.endswith(("status", "sex")):
        return "radio"
    if column_name.endswith("type"):
        return "select"
    if any(token in column_name for token in ("image", "avatar", "logo", "icon")):
        return "imageUpload"
    if column_name.endswith("file"):
        return "fileUpload"
    if column_name.endswith(("content", "description", "remark")) or sql_type in {"text", "mediumtext", "longtext"}:
        return "textarea"
    if sql_type in {"datetime", "timestamp"} or column_name.endswith(("time", "birthday")):
        return "datetime"
    if sql_type == "date":
        return "date"
    return "input"


def snake_to_camel(value: str) -> str:
    parts = [part for part in value.split("_") if part]
    if not parts:
        return value
    return parts[0] + "".join(part.capitalize() for part in parts[1:])
