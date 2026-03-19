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
