from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .inspector import discover_workspace_projects
from .models import DatabaseConfig, FrontendType, RoutingMode, SqlAssetMode, WorkspaceConfigFile


CONFIG_DIR_NAME = ".yudao-pilot"
CONFIG_FILE_NAME = "config.yaml"


class WorkspaceInfo(BaseModel):
    name: str = "my-yudao-workspace"


class BackendProject(BaseModel):
    path: str
    type: str
    config_profile: str = "local"


class FrontendProject(BaseModel):
    type: FrontendType
    path: str


class ProjectsConfig(BaseModel):
    backend: BackendProject
    frontend: list[FrontendProject] = Field(default_factory=list)

    @field_validator("frontend")
    @classmethod
    def validate_unique_frontend_types(
        cls, frontend_projects: list[FrontendProject]
    ) -> list[FrontendProject]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for project in frontend_projects:
            if project.type in seen:
                duplicates.add(project.type)
            seen.add(project.type)
        if duplicates:
            duplicate_text = ", ".join(sorted(duplicates))
            raise ValueError(f"projects.frontend 存在重复的 type: {duplicate_text}")
        return frontend_projects


class ManualTableRule(BaseModel):
    table: str
    business: str
    entity: str


class ManualRule(BaseModel):
    module: str
    table_prefixes: list[str] = Field(default_factory=list)
    table_rules: list[ManualTableRule] = Field(default_factory=list)

    @field_validator("table_prefixes")
    @classmethod
    def sort_prefixes_desc(cls, prefixes: list[str]) -> list[str]:
        return sorted(prefixes, key=len, reverse=True)


class RoutingConfig(BaseModel):
    mode: RoutingMode = "manual"


class CodegenConfig(BaseModel):
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    manual_rules: list[ManualRule] = Field(default_factory=list)
    apply_to_database: bool = False
    menu_sql_mode: SqlAssetMode = "auto"
    dict_sql_mode: SqlAssetMode = "auto"

    @model_validator(mode="after")
    def validate_manual_mode(self) -> "CodegenConfig":
        if self.routing.mode == "manual" and not self.manual_rules:
            raise ValueError("routing.mode=manual 时，manual_rules 不能为空")
        return self


class WorkspaceConfig(BaseModel):
    version: int = 1
    workspace: WorkspaceInfo = Field(default_factory=WorkspaceInfo)
    projects: ProjectsConfig
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    codegen: CodegenConfig = Field(default_factory=CodegenConfig)


def default_config_template() -> str:
    return dedent(
        """\
        version: 1

        workspace:
          name: my-yudao-workspace

        projects:
          backend:
            path: ../yudao-server
            type: ruoyi-vue-pro-jdk17 # 可选：ruoyi-vue-pro、ruoyi-vue-pro-jdk17、yudao-cloud
            config_profile: local # 读取后端本地配置时使用的环境名

          frontend:
            - type: VUE3_ELEMENT_PLUS # 可选：VUE3_ELEMENT_PLUS、VUE3_VBEN5_ANTD_SCHEMA、VUE3_VBEN5_ANTD_GENERAL、VUE3_VBEN5_EP_SCHEMA、VUE3_VBEN5_EP_GENERAL、VUE3_ADMIN_UNIAPP_WOT
              path: ../yudao-ui-admin-vue3
            - type: VUE3_VBEN5_ANTD_SCHEMA
              path: ../yudao-ui-admin-vben
            - type: VUE3_VBEN5_EP_GENERAL
              path: ../yudao-ui-admin-vben
            - type: VUE3_ADMIN_UNIAPP_WOT
              path: ../yudao-ui-admin-uniapp
            # 约束：
            # 1. backend 只能有一个
            # 2. frontend 中 type 不能重复，重复直接报错
            # 3. path 必须存在，且识别结果必须和 type 对应的真实前端项目匹配，否则报错
            # 4. 同一个 yudao-ui-admin-vben 路径可以配置多个不同枚举，分别产出 web-antd / web-ele 的代码

        database:
          mode: auto # auto | manual
          host: ""
          port: 3306
          database: ""
          username: ""
          password: ""
          # 规则：
          # 1. mode=manual 时，直接使用这里的数据库连接
          # 2. mode=auto 时，如果这里未填写，则优先从 backend 的本地配置中读取
          # 3. MCP 读取成功后，可以回填到本配置文件中

        codegen:
          # 是否允许将菜单/字典 SQL 实际执行到数据库。默认 false，仅生成迁移 SQL，不写库。
          apply_to_database: false

          routing:
            mode: manual # auto | ask | manual
            # auto: MCP 自动分析目标位置，并告诉 AI 先生成代码，再调用 MCP 写入
            # ask: MCP 返回候选位置，由 AI 询问用户后再继续
            # manual: 按 manual_rules 规则解析，不让用户每次重复确认

          # 菜单 SQL：auto / migration_only 均生成迁移 SQL；disabled 不生成菜单 SQL
          menu_sql_mode: auto # auto | migration_only | disabled
          # 字典 SQL：同上
          dict_sql_mode: auto # auto | migration_only | disabled

          manual_rules:
            - module: member
              table_prefixes:
                - merchant_user
                - merchant
                - member
              table_rules:
                - table: member
                  business: member
                  entity: Member

                - table: member_user
                  business: member_user
                  entity: MemberUser

                - table: member_user_login_log
                  business: member_user_login_log
                  entity: MemberUserLoginLog

                - table: merchant
                  business: merchant
                  entity: Merchant
              # 规则：
              # 1. 先按 table_rules.table 精确匹配
              # 2. 若未命中，再按 table_prefixes 做最长前缀匹配
              # 3. 最长前缀优先，例如 merchant_user 优先于 merchant
              # 4. business 用于业务目录、菜单、路由等
              # 5. entity 用于实体类、VO、DTO、TS 类型名等
              # 6. 最终生成目标严格按 projects 中已配置的后端和前端类型执行
        """
    )


def resolve_config_path(workspace_root: str | Path) -> Path:
    root = Path(workspace_root).expanduser().resolve()
    return root / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def load_workspace_config_file(workspace_root: str | Path) -> WorkspaceConfigFile:
    config_path = resolve_config_path(workspace_root)
    if not config_path.exists():
        return WorkspaceConfigFile(
            path=str(config_path),
            exists=False,
            template=default_config_template(),
        )
    return WorkspaceConfigFile(
        path=str(config_path),
        exists=True,
        content=config_path.read_text(encoding="utf-8"),
    )


def load_workspace_config(workspace_root: str | Path) -> WorkspaceConfig:
    config_path = resolve_config_path(workspace_root)
    raw_text = config_path.read_text(encoding="utf-8")
    raw_data = yaml.safe_load(raw_text) or {}
    return WorkspaceConfig.model_validate(raw_data)


def init_workspace_config(
    workspace_root: str | Path, *, overwrite: bool = False
) -> WorkspaceConfigFile:
    config_path = resolve_config_path(workspace_root)
    if config_path.exists() and not overwrite:
        return WorkspaceConfigFile(
            path=str(config_path),
            exists=True,
            content=config_path.read_text(encoding="utf-8"),
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)
    content = default_config_template()
    config_path.write_text(content, encoding="utf-8")
    return WorkspaceConfigFile(path=str(config_path), exists=True, content=content)


def auto_init_workspace_config(
    workspace_root: str | Path,
    *,
    overwrite: bool = False,
    scan_depth: int = 3,
) -> WorkspaceConfigFile:
    config_path = resolve_config_path(workspace_root)
    if config_path.exists() and not overwrite:
        return WorkspaceConfigFile(
            path=str(config_path),
            exists=True,
            content=config_path.read_text(encoding="utf-8"),
        )

    root = Path(workspace_root).expanduser().resolve()
    discovered = discover_workspace_projects(root, max_depth=scan_depth)
    content = render_auto_config(root, discovered)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content, encoding="utf-8")
    return WorkspaceConfigFile(path=str(config_path), exists=True, content=content)


def render_auto_config(workspace_root: Path, discovered: dict) -> str:
    backend = discovered.get("backend") or {}
    backend_path = str(backend.get("path") or "../yudao-server")
    backend_type = str(backend.get("type") or "ruoyi-vue-pro-jdk17")
    frontend_projects = discovered.get("frontend") or []

    raw_config = {
        "version": 1,
        "workspace": {"name": workspace_root.name or "my-yudao-workspace"},
        "projects": {
            "backend": {
                "path": backend_path,
                "type": backend_type,
                "config_profile": "local",
            },
            "frontend": [
                {"type": item["type"], "path": item["path"]}
                for item in frontend_projects
            ],
        },
        "database": {
            "mode": "auto",
            "host": "",
            "port": 3306,
            "database": "",
            "username": "",
            "password": "",
        },
        "codegen": {
            "apply_to_database": False,
            "routing": {"mode": "manual"},
            "menu_sql_mode": "auto",
            "dict_sql_mode": "auto",
            "manual_rules": [
                {
                    "module": "member",
                    "table_prefixes": ["merchant_user", "merchant", "member"],
                    "table_rules": [
                        {
                            "table": "member",
                            "business": "member",
                            "entity": "Member",
                        }
                    ],
                }
            ],
        },
    }
    return yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True)
