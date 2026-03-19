from __future__ import annotations

from pathlib import Path

from yudao_pilot.config import load_workspace_config
from yudao_pilot.inspector import validate_workspace_projects


def test_dev_workspace_fixture_config_is_valid(repo_root: Path) -> None:
    workspace_root = repo_root / "tests" / "fixtures" / "dev-workspace"
    config = load_workspace_config(workspace_root)

    assert config.projects.backend.type == "ruoyi-vue-pro-jdk17"
    assert [frontend.type for frontend in config.projects.frontend] == [
        "yudao-ui-admin-vue3",
        "yudao-ui-admin-vben",
        "yudao-ui-admin-uniapp",
    ]

    result = validate_workspace_projects(workspace_root, config)
    assert result["ok"] is True
