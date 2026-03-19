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
    "yudao-ui-admin-vue3": "yudao-ui-admin-vue3",
    "yudao-ui-admin-vben": "yudao-ui-admin-vben",
    "yudao-ui-admin-uniapp": "yudao-ui-admin-uniapp",
}


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def workspace_builder(tmp_path: Path, repo_root: Path):
    def _build(
        *,
        backend_path: str = "yudao-projects/ruoyi-vue-pro-jdk17",
        backend_type: str = "ruoyi-vue-pro-jdk17",
        frontend_types: tuple[str, ...] = ("yudao-ui-admin-vue3",),
        manual_rules_yaml: str | None = None,
    ) -> Path:
        workspace_root = tmp_path / "workspace"
        (workspace_root / ".yudao-pilot").mkdir(parents=True, exist_ok=True)

        frontend_yaml = "\n".join(
            dedent(
                f"""\
                - type: {frontend_type}
                  path: {repo_root / "yudao-projects" / FRONTEND_PATHS[frontend_type]}
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
                    "path": str(repo_root / backend_path),
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
