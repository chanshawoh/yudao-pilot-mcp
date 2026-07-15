from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


FRONTEND_PATHS = {
    "VUE3_ELEMENT_PLUS": "yudao-ui-admin-vue3",
    "VUE3_VBEN5_ANTD_SCHEMA": "yudao-ui-admin-vben",
    "VUE3_VBEN5_ANTD_GENERAL": "yudao-ui-admin-vben",
    "VUE3_VBEN5_EP_SCHEMA": "yudao-ui-admin-vben",
    "VUE3_VBEN5_EP_GENERAL": "yudao-ui-admin-vben",
    "VUE3_ADMIN_UNIAPP_WOT": "yudao-ui-admin-uniapp",
}


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def workspace_builder(tmp_path: Path):
    def _build(
        *,
        backend_path: str = "backend",
        backend_type: str = "ruoyi-vue-pro-jdk17",
        frontend_types: tuple[str, ...] = ("VUE3_ELEMENT_PLUS",),
        manual_rules_yaml: str | None = None,
    ) -> Path:
        workspace_root = tmp_path / "workspace"
        (workspace_root / ".yudao-pilot").mkdir(parents=True, exist_ok=True)

        backend_root = workspace_root / backend_path
        (backend_root / "yudao-server").mkdir(parents=True, exist_ok=True)
        (backend_root / "yudao-module-member").mkdir(parents=True, exist_ok=True)
        (backend_root / "sql" / "mysql" / "migrations").mkdir(parents=True, exist_ok=True)
        (backend_root / "pom.xml").write_text(
            dedent(
                """\
                <project>
                  <groupId>cn.iocoder.boot</groupId>
                  <artifactId>yudao</artifactId>
                  <packaging>pom</packaging>
                  <properties><java.version>17</java.version><spring.boot.version>3.2.0</spring.boot.version></properties>
                  <modules><module>yudao-server</module><module>yudao-module-member</module></modules>
                </project>
                """
            ),
            encoding="utf-8",
        )
        (backend_root / "yudao-server" / "pom.xml").write_text(
            "<project><artifactId>yudao-server</artifactId><dependencies><dependency><groupId>cn.iocoder.boot</groupId><artifactId>yudao-module-member</artifactId></dependency></dependencies></project>",
            encoding="utf-8",
        )
        resources_root = backend_root / "yudao-server" / "src" / "main" / "resources"
        resources_root.mkdir(parents=True, exist_ok=True)
        (resources_root / "application-local.yaml").write_text(
            dedent(
                """\
                spring:
                  datasource:
                    url: jdbc:mysql://127.0.0.1:3306/demo?useSSL=false
                    username: root
                    password: 123456
                yudao:
                  codegen:
                    base-package: cn.iocoder.yudao
                    unit-test-enable: false
                """
            ),
            encoding="utf-8",
        )

        frontend_roots: dict[str, Path] = {}
        for frontend_type in frontend_types:
            frontend_root = workspace_root / "frontend" / FRONTEND_PATHS[frontend_type]
            frontend_root.mkdir(parents=True, exist_ok=True)
            frontend_roots[frontend_type] = frontend_root
            package_json = '{"dependencies":{"vue":"^3.4.0","element-plus":"^2.0.0"}}'
            if "VBEN5" in frontend_type:
                package_json = '{"scripts":{"dev":"turbo run dev"},"dependencies":{"@vben/common-ui":"workspace:*"}}'
            elif "UNIAPP" in frontend_type:
                package_json = '{"dependencies":{"vue":"^3.4.0","@dcloudio/uni-app":"^3.0.0"}}'
            (frontend_root / "package.json").write_text(package_json, encoding="utf-8")
            (frontend_root / "src" / "utils").mkdir(parents=True, exist_ok=True)
            (frontend_root / "src" / "utils" / "dict.ts").write_text(
                "export enum DICT_TYPE {\n}\n", encoding="utf-8"
            )

        frontend_yaml = "\n".join(
            dedent(
                f"""\
                - type: {frontend_type}
                  path: {frontend_roots[frontend_type]}
                """
            ).rstrip()
            for frontend_type in frontend_types
        )
        manual_rules_section = manual_rules_yaml or dedent(
            """\
            - module: member
              table_prefixes:
                - merchant_user
                - merchant
                - member_user
                - member
              table_rules:
                - table: merchant_user
                  business: merchant_user
                  entity: MerchantUser
                - table: merchant
                  business: merchant
                  entity: Merchant
                - table: member_user
                  business: member_user
                  entity: MemberUser
            """
        ).rstrip()
        raw_config = {
            "version": 1,
            "workspace": {"name": "pytest-workspace"},
            "projects": {
                "backend": {
                    "path": str(backend_root),
                    "type": backend_type,
                    "config_profile": "local",
                },
                "frontend": yaml.safe_load(frontend_yaml),
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
                "routing": {"mode": "manual"},
                "manual_rules": yaml.safe_load(manual_rules_section),
            },
        }
        config_path = workspace_root / ".yudao-pilot" / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return workspace_root

    return _build
