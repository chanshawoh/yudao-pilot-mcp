from __future__ import annotations

from pathlib import Path

from .config import WorkspaceConfig
from .error_codes import is_manual_error_code_file, merge_manual_error_code_file
from .inspector import resolve_backend_repo_root, resolve_project_path
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
        base_dir = base_dir.resolve()
        output_path = (base_dir / generated_file.relative_path).resolve()

        if generated_file.target_kind == "backend":
            backend_module_dir = resolve_backend_module_dir(base_dir, generated_file.relative_path)
            if backend_module_dir is None or not is_relative_to(output_path, backend_module_dir):
                results.append(
                    WriteResult(
                        target_kind=generated_file.target_kind,
                        target_type=generated_file.target_type,
                        path=str(output_path),
                        written=False,
                        reason=(
                            "目标后端模块不存在，拒绝创建新的模块结构"
                            if backend_module_dir is None
                            else "目标路径越界，拒绝写入"
                        ),
                    )
                )
                continue
            if is_manual_error_code_file(generated_file.relative_path):
                merged, merged_path, merge_reason = merge_manual_error_code_file(base_dir, generated_file)
                results.append(
                    WriteResult(
                        target_kind=generated_file.target_kind,
                        target_type=generated_file.target_type,
                        path=merged_path,
                        written=merged,
                        reason=None if merged else merge_reason,
                    )
                )
                continue

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
        backend_path = resolve_project_path(workspace_root, config.projects.backend.path)
        return resolve_backend_repo_root(backend_path)

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


def resolve_backend_module_dir(base_dir: Path, relative_path: str) -> Path | None:
    relative = Path(relative_path)
    parts = relative.parts
    if not parts:
        return None
    module_dir = (base_dir / parts[0]).resolve()
    if not module_dir.exists() or not module_dir.is_dir():
        return None
    return module_dir
