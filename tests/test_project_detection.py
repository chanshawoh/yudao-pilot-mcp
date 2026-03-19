from __future__ import annotations

from pathlib import Path

from yudao_pilot.inspector import inspect_project_path


def test_inspect_backend_project_by_fingerprint(repo_root: Path) -> None:
    result = inspect_project_path(repo_root / "yudao-projects" / "ruoyi-vue-pro-jdk17")
    assert result["exists"] is True
    assert result["best_match"]["detected_type"] == "ruoyi-vue-pro-jdk17"
    assert result["backend"]["supported"] is True


def test_inspect_frontend_vben_by_fingerprint(repo_root: Path) -> None:
    result = inspect_project_path(repo_root / "yudao-projects" / "yudao-ui-admin-vben")
    assert result["exists"] is True
    assert result["best_match"]["detected_type"] == "yudao-ui-admin-vben"
    assert result["frontend"]["supported"] is True
