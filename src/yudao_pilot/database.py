from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import WorkspaceConfig
from .inspector import resolve_project_path
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
        host=backend_db.get("host", ""),
        port=backend_db.get("port", 3306),
        database=backend_db.get("database", ""),
        username=backend_db.get("username", ""),
        password=backend_db.get("password", ""),
        source="backend-local",
    )
    return {"ok": True, "database": merged.model_dump(), "message": "已从后端本地配置解析数据库连接"}


def read_backend_local_database(
    backend_root: Path, config_profile: str
) -> dict[str, Any] | None:
    resource_root = backend_root / "src" / "main" / "resources"
    candidates = [
        resource_root / f"application-{config_profile}.yaml",
        resource_root / f"application-{config_profile}.yml",
        resource_root / "application-local.yaml",
        resource_root / "application-local.yml",
        resource_root / "application.yaml",
        resource_root / "application.yml",
    ]

    for file_path in candidates:
        if not file_path.exists():
            continue
        raw_data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        resolved = extract_database_from_spring_config(raw_data)
        if resolved:
            return resolved
    return None


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
            for candidate_name in ("master", "primary", "default"):
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
    username = raw_config.get("username")
    password = raw_config.get("password")
    if not all(isinstance(value, str) for value in [url, username, password]):
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
