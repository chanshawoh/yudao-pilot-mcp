from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


BackendType = Literal["ruoyi-vue-pro", "ruoyi-vue-pro-jdk17", "yudao-cloud"]
FrontendType = Literal[
    "yudao-ui-admin-vue3",
    "yudao-ui-admin-vben",
    "yudao-ui-admin-uniapp",
]
ProjectKind = Literal["backend", "frontend", "unknown"]
RoutingMode = Literal["auto", "ask", "manual"]
DatabaseMode = Literal["auto", "manual"]
TargetKind = Literal["backend", "frontend"]

SUPPORTED_BACKEND_TYPES = ("ruoyi-vue-pro", "ruoyi-vue-pro-jdk17", "yudao-cloud")
SUPPORTED_FRONTEND_TYPES = (
    "yudao-ui-admin-vue3",
    "yudao-ui-admin-vben",
    "yudao-ui-admin-uniapp",
)


class WorkspaceConfigFile(BaseModel):
    path: str = Field(..., description="配置文件路径，基于当前工作区根目录")
    exists: bool
    content: str | None = None
    template: str | None = None


class DatabaseConfig(BaseModel):
    mode: DatabaseMode = "auto"
    host: str = ""
    port: int = 3306
    database: str = ""
    username: str = ""
    password: str = ""
    source: Literal["config", "backend-local", "none"] = "none"

    def has_manual_values(self) -> bool:
        return bool(self.host and self.database and self.username)


class ProjectDetection(BaseModel):
    kind: ProjectKind = "unknown"
    detected_type: str | None = None
    supported: bool = False
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class ProjectValidation(BaseModel):
    kind: ProjectKind
    project_type: str
    path: str
    exists: bool
    matches_expected: bool
    detected_type: str | None = None
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    error_code: str | None = None
    reason: str | None = None


class TableResolution(BaseModel):
    module: str
    matched_by: Literal["exact", "prefix", "fallback"]
    matched_table: str | None = None
    matched_prefix: str | None = None
    business: str
    entity: str


class CodegenTarget(BaseModel):
    kind: TargetKind
    project_type: str
    path: str


class CodegenPlan(BaseModel):
    table_name: str
    routing_mode: RoutingMode
    resolution: TableResolution
    backend: CodegenTarget | None = None
    frontends: list[CodegenTarget] = Field(default_factory=list)


class GeneratedFile(BaseModel):
    target_kind: TargetKind
    target_type: str
    relative_path: str
    content: str
    overwrite: bool = True


class WriteResult(BaseModel):
    target_kind: TargetKind
    target_type: str
    path: str
    written: bool
    reason: str | None = None


class WorkspaceContext(BaseModel):
    root: Path
    config_path: Path
