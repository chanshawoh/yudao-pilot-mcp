from __future__ import annotations

from pathlib import Path

from .config import WorkspaceConfig
from .inspector import resolve_project_path
from .models import GeneratedFile, WriteResult


def write_generated_files(
    workspace_root: str | Path,
    config: WorkspaceConfig,
    files: list[GeneratedFile],
) -> dict[str, object]:
    root = Path(workspace_root).expanduser().resolve()
    results: list[WriteResult] = []

    for generated_file in files:
        base_dir = resolve_target_base_dir(root, config, generated_file.target_kind, generated_file.target_type)
        if base_dir is None:
            results.append(
                WriteResult(
                    target_kind=generated_file.target_kind,
                    target_type=generated_file.target_type,
                    path=generated_file.relative_path,
                    written=False,
                    reason=f"未找到目标项目: {generated_file.target_type}",
                )
            )
            continue

        output_path = (base_dir / generated_file.relative_path).resolve()
        if not is_relative_to(output_path, base_dir):
            results.append(
                WriteResult(
                    target_kind=generated_file.target_kind,
                    target_type=generated_file.target_type,
                    path=str(output_path),
                    written=False,
                    reason="目标路径越界，拒绝写入",
                )
            )
            continue

        if output_path.exists() and not generated_file.overwrite:
            results.append(
                WriteResult(
                    target_kind=generated_file.target_kind,
                    target_type=generated_file.target_type,
                    path=str(output_path),
                    written=False,
                    reason="文件已存在且 overwrite=false",
                )
            )
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generated_file.content, encoding="utf-8")
        results.append(
            WriteResult(
                target_kind=generated_file.target_kind,
                target_type=generated_file.target_type,
                path=str(output_path),
                written=True,
            )
        )

    return {
        "ok": all(result.written for result in results),
        "results": [result.model_dump() for result in results],
    }


def resolve_target_base_dir(
    workspace_root: Path,
    config: WorkspaceConfig,
    target_kind: str,
    target_type: str,
) -> Path | None:
    if target_kind == "backend" and config.projects.backend.type == target_type:
        return resolve_project_path(workspace_root, config.projects.backend.path)

    if target_kind == "frontend":
        for frontend in config.projects.frontend:
            if frontend.type == target_type:
                return resolve_project_path(workspace_root, frontend.path)
    return None


def is_relative_to(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False
