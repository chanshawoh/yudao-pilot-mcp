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
        "ai_component_hints": build_ai_component_hints(columns),
        "available_components": AVAILABLE_COMPONENTS,
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
        "ai_component_hints": build_ai_component_hints(columns),
        "available_components": AVAILABLE_COMPONENTS,
    }


def parse_type_meta(raw_type: str) -> dict[str, Any]:
    """Extract max_length, precision, scale from raw SQL type like varchar(255) or decimal(10,6)."""
    meta: dict[str, Any] = {}
    m = re.match(r"[a-z]+\((\d+)(?:,\s*(\d+))?\)", raw_type.lower())
    if not m:
        return meta
    first = int(m.group(1))
    second = int(m.group(2)) if m.group(2) else None
    base = raw_type.split("(", 1)[0].lower()
    if base in {"varchar", "char", "tinytext"}:
        meta["max_length"] = first
    elif base in {"decimal", "numeric"}:
        meta["precision"] = first
        meta["scale"] = second if second is not None else 0
        meta["integer_digits"] = first - (second or 0)
    return meta


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
    type_meta = parse_type_meta(raw_type)

    return {
        "column_name": column_name,
        "column_comment": str(row.get("COLUMN_COMMENT") or column_name),
        "sql_type": sql_type,
        "raw_type": raw_type,
        "java_field": java_field,
        "java_type": map_java_type(sql_type),
        "ts_type": map_ts_type(sql_type),
        "html_type": infer_html_type(column_name, sql_type, str(row.get("COLUMN_COMMENT") or "")),
        "nullable": nullable,
        "primary_key": is_primary_key,
        "auto_increment": is_auto_increment,
        "is_base_column": is_base_column,
        **type_meta,
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
    html_type = infer_html_type(column_name, sql_type, column_comment or "")
    is_primary_key = column_name in primary_keys
    is_base_column = column_name in BASE_AUDIT_COLUMNS
    is_internal = column_name in INTERNAL_COLUMNS
    is_auto_increment = "AUTO_INCREMENT" in line.upper()
    nullable = "NOT NULL" not in line.upper()
    type_meta = parse_type_meta(raw_type)

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
        **type_meta,
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


def infer_html_type(column_name: str, sql_type: str, column_comment: str = "") -> str:
    name_lower = column_name.lower()
    is_string_type = sql_type in {
        "varchar", "char", "text", "mediumtext", "longtext", "tinytext",
    }

    _IMAGE_NAME_TOKENS = (
        "image", "avatar", "logo", "icon", "pic", "photo",
        "cover", "banner", "thumbnail",
    )
    if any(token in name_lower for token in _IMAGE_NAME_TOKENS) and is_string_type:
        return "imageUpload"
    _IMAGE_COMMENT_KW = ("图片", "封面图", "轮播图", "头像", "图标", "缩略图", "相册")
    if is_string_type and any(kw in column_comment for kw in _IMAGE_COMMENT_KW):
        return "imageUpload"

    _FILE_NAME_TOKENS = ("video", "file", "attachment")
    if any(token in name_lower for token in _FILE_NAME_TOKENS) and is_string_type:
        return "fileUpload"
    _FILE_COMMENT_KW = ("视频", "文件", "附件")
    if is_string_type and any(kw in column_comment for kw in _FILE_COMMENT_KW):
        return "fileUpload"

    if name_lower.endswith(("status", "sex")):
        return "radio"
    if name_lower.endswith("type"):
        return "select"

    if sql_type in {"text", "mediumtext", "longtext"}:
        return "editor"

    if name_lower.endswith(("content", "description", "remark", "memo", "note", "intro", "summary")):
        return "textarea"

    if sql_type in {"datetime", "timestamp"} or name_lower.endswith(("time", "birthday")):
        return "datetime"
    if sql_type == "date":
        return "date"
    return "input"


AVAILABLE_COMPONENTS = [
    {"component": "Input", "html_type": "input", "description": "单行文本输入框，适用于短文本如名称、编号、手机号等"},
    {"component": "InputNumber", "html_type": "inputNumber", "description": "数字输入框，适用于数值如金额、数量、排序号、经纬度等"},
    {"component": "Textarea", "html_type": "textarea", "description": "多行文本域，适用于中等长度文本如备注、描述等"},
    {"component": "RichTextarea", "html_type": "editor", "description": "富文本编辑器，适用于长文本内容如文章、详情、公告等"},
    {"component": "Select", "html_type": "select", "description": "下拉选择框，适用于枚举选项超过3个的场景如类型选择"},
    {"component": "RadioGroup", "html_type": "radio", "description": "单选框组，适用于枚举选项不超过3个的场景如状态、性别"},
    {"component": "Checkbox", "html_type": "checkbox", "description": "复选框，适用于布尔值或多选场景"},
    {"component": "DatePicker", "html_type": "datetime", "description": "日期时间选择器，适用于日期/时间字段"},
    {"component": "ImageUpload", "html_type": "imageUpload", "description": "图片上传组件，适用于图片URL字段如头像、封面图、Logo、轮播图等"},
    {"component": "FileUpload", "html_type": "fileUpload", "description": "文件上传组件，适用于文件/视频/附件URL字段"},
]


def build_ai_component_hints(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identify columns with html_type='input' that might need AI review."""
    undetermined: list[dict[str, Any]] = []
    for col in columns:
        if col.get("html_type") != "input":
            continue
        if col.get("is_base_column") or col.get("primary_key"):
            continue
        undetermined.append({
            "column_name": col["column_name"],
            "java_field": col["java_field"],
            "column_comment": col.get("column_comment", ""),
            "sql_type": col.get("sql_type", ""),
            "java_type": col.get("java_type", ""),
            "current_html_type": "input",
        })
    if not undetermined:
        return []
    return undetermined


def extract_dict_fields(
    columns: list[dict[str, Any]],
    table_name: str,
    table_comment: str,
) -> list[dict[str, Any]]:
    """Detect columns whose comments contain enum-like patterns (e.g. '状态: 0-开启, 1-禁用')
    and return a structured dict plan for each."""
    dict_fields: list[dict[str, Any]] = []
    biz_label = _normalize_table_comment_for_dict(table_comment)

    for col in columns:
        if col.get("is_base_column") or col.get("primary_key"):
            continue
        comment = re.sub(r"[\r\n]+", " ", str(col.get("column_comment") or "")).strip()
        if not comment:
            continue
        options = _parse_dict_options_from_comment(comment)
        if not options:
            continue

        field_label = _sanitize_dict_field_label(comment)
        dict_type_key = f"{table_name}_{col['column_name']}"
        dict_type_name = f"{biz_label}{field_label}"
        ts_type = col.get("ts_type", "string")

        for idx, opt in enumerate(options):
            opt["sort"] = idx
            opt["color_type"] = _infer_dict_color_type(opt["label"], idx, len(options))
            opt["value"] = str(opt["value"])

        dict_fields.append({
            "column_name": col["column_name"],
            "java_field": col["java_field"],
            "dict_type": dict_type_key,
            "dict_name": dict_type_name,
            "ts_type": ts_type,
            "items": options,
        })
    return dict_fields


def _normalize_table_comment_for_dict(table_comment: str) -> str:
    """Strip common table-comment suffixes to derive a clean business label."""
    cleaned = table_comment.strip()
    for suffix in ("基础信息表", "信息表", "数据表", "记录表", "表", "基础信息", "信息"):
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
            break
    return cleaned


def _sanitize_dict_field_label(comment: str) -> str:
    """Extract the short field label from a comment like '状态: 0-开启, 1-禁用' → '状态'."""
    cleaned = re.sub(r"[\r\n]+", " ", comment).strip()
    return re.split(r"[:：(（]", cleaned, maxsplit=1)[0].strip() or cleaned


def _parse_dict_options_from_comment(comment: str) -> list[dict[str, Any]]:
    """Parse 'value-label' pairs from comments like '状态: 0-开启, 1-禁用' or '类型（1-酒店, 2-民宿）'."""
    delim_match = re.search(r"[:：(（]", comment)
    if not delim_match:
        return []
    option_text = comment[delim_match.end():].rstrip(")）").strip()
    if not re.search(r"\d+\s*[-=]\s*\S", option_text):
        return []
    options: list[dict[str, Any]] = []
    for segment in re.split(r"[，,；;\s]+", option_text):
        item = segment.strip()
        if not item:
            continue
        match = re.match(r"(?P<value>[^-=:：\s]+)\s*[-=:：]\s*(?P<label>.+)", item)
        if not match:
            return []
        options.append({
            "value": match.group("value").strip(),
            "label": match.group("label").strip(),
        })
    return options if options else []


_SUCCESS_LABELS = {"开启", "启用", "正常", "成功", "是", "通过", "完成", "有效", "上架", "已支付", "已完成", "显示", "生效"}
_DANGER_LABELS = {"关闭", "禁用", "停用", "失败", "否", "拒绝", "无效", "下架", "已取消", "隐藏", "作废", "删除"}
_WARNING_LABELS = {"待处理", "进行中", "审核中", "处理中", "待审核", "待支付", "待发货", "未开始", "草稿"}
_INFO_LABELS = {"未知", "默认", "其他", "其它"}


def _infer_dict_color_type(label: str, index: int, total: int) -> str:
    if label in _SUCCESS_LABELS:
        return "success"
    if label in _DANGER_LABELS:
        return "danger"
    if label in _WARNING_LABELS:
        return "warning"
    if label in _INFO_LABELS:
        return "info"
    if index == 0 and total <= 3:
        return "primary"
    if index == 1 and total <= 3:
        return "success"
    return "default"


def snake_to_camel(value: str) -> str:
    parts = [part for part in value.split("_") if part]
    if not parts:
        return value
    return parts[0] + "".join(part.capitalize() for part in parts[1:])
