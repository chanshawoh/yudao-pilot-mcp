from __future__ import annotations

import re
from datetime import datetime
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
    frontend_targets_seen: set[str] = set()

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
        if generated_file.target_kind == "frontend":
            frontend_targets_seen.add(generated_file.target_type)

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

        if generated_file.target_kind == "frontend" and is_frontend_dict_file(generated_file.relative_path):
            merged, merge_reason = merge_frontend_dict_type_file(output_path, generated_file.content)
            results.append(
                WriteResult(
                    target_kind=generated_file.target_kind,
                    target_type=generated_file.target_type,
                    path=str(output_path),
                    written=merged,
                    reason=None if merged else merge_reason,
                )
            )
            continue

        if output_path.exists() and not generated_file.overwrite:
            prompt = (
                f"目标文件已存在：{output_path}。该文件属于必须不存在才能新建的代码生成文件，"
                "请询问用户是否覆盖；如用户确认覆盖，请将该文件的 overwrite 设为 true 后重试。"
            )
            results.append(
                WriteResult(
                    target_kind=generated_file.target_kind,
                    target_type=generated_file.target_type,
                    path=str(output_path),
                    written=False,
                    reason="目标文件已存在，需要用户确认是否覆盖",
                    error_code="generated_file_exists",
                    should_stop=True,
                    next_action_prompt=prompt,
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

    for target_type in sorted(frontend_targets_seen):
        base_dir = resolve_target_base_dir(root, config, "frontend", target_type)
        if base_dir is None:
            continue
        repair_dict_result = repair_frontend_dict_type_file(base_dir / "src" / "utils" / "dict.ts")
        if repair_dict_result is None:
            continue
        repaired, repair_reason = repair_dict_result
        results.append(
            WriteResult(
                target_kind="frontend",
                target_type=target_type,
                path=str((base_dir / "src" / "utils" / "dict.ts").resolve()),
                written=repaired,
                reason=None if repaired else repair_reason,
            )
        )

    return {
        "ok": all(result.written for result in results),
        "results": [result.model_dump() for result in results],
    }


def write_preview_generated_files(
    workspace_root: str | Path,
    files: list[GeneratedFile],
    *,
    table_name: str,
) -> dict[str, object]:
    root = Path(workspace_root).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    preview_root = root / ".yudao-pilot" / "previews" / f"{normalize_preview_name(table_name)}-{timestamp}"
    results: list[dict[str, object]] = []

    for generated_file in files:
        relative_path = Path(generated_file.target_kind) / generated_file.target_type / generated_file.relative_path
        output_path = (preview_root / relative_path).resolve()
        if not is_relative_to(output_path, preview_root.resolve()):
            results.append(
                {
                    "target_kind": generated_file.target_kind,
                    "target_type": generated_file.target_type,
                    "path": str(output_path),
                    "written": False,
                    "reason": "预览路径越界，拒绝写入",
                }
            )
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generated_file.content, encoding="utf-8")
        results.append(
            {
                "target_kind": generated_file.target_kind,
                "target_type": generated_file.target_type,
                "path": str(output_path),
                "written": True,
            }
        )

    return {
        "ok": all(bool(result["written"]) for result in results),
        "mode": "preview",
        "preview_root": str(preview_root),
        "results": results,
    }


def normalize_preview_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return normalized.strip("-") or "codegen"


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


def is_frontend_dict_file(relative_path: str) -> bool:
    return Path(relative_path).as_posix() == "src/utils/dict.ts"


def merge_frontend_dict_type_file(file_path: Path, additions: str) -> tuple[bool, str | None]:
    constants = parse_dict_type_additions(additions)
    if not file_path.exists():
        return False, "前端字典常量文件不存在，无法合并 DICT_TYPE"

    text = file_path.read_text(encoding="utf-8")
    existing_names = set(re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*=", text, flags=re.MULTILINE))
    existing_values = set(re.findall(r"=\s*['\"]([^'\"]+)['\"]\s*,?", text))
    missing = [
        (name, value, comment)
        for name, value, comment in constants
        if name not in existing_names and value not in existing_values
    ]

    lines = text.splitlines()
    enum_start = next(
        (index for index, line in enumerate(lines) if re.match(r"\s*export\s+enum\s+DICT_TYPE\s*\{", line)),
        None,
    )
    if enum_start is None:
        return False, "未找到 export enum DICT_TYPE，无法合并字典常量"

    enum_end = next(
        (index for index in range(enum_start + 1, len(lines)) if lines[index].strip() == "}"),
        None,
    )
    if enum_end is None:
        return False, "DICT_TYPE enum 未找到结束位置，无法合并字典常量"

    lines, repaired = repair_enum_member_commas(lines, enum_start, enum_end)
    insert_lines = [
        f"  {name} = '{value}'," + (f" // {comment}" if comment else "")
        for name, value, comment in missing
    ]
    if missing:
        updated = lines[:enum_end] + insert_lines + lines[enum_end:]
    else:
        updated = lines
    if missing or repaired:
        file_path.write_text("\n".join(updated) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return True, None


def repair_frontend_dict_type_file(file_path: Path) -> tuple[bool, str | None] | None:
    if not file_path.exists():
        return None

    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    enum_start = next(
        (index for index, line in enumerate(lines) if re.match(r"\s*export\s+enum\s+DICT_TYPE\s*\{", line)),
        None,
    )
    if enum_start is None:
        return False, "未找到 export enum DICT_TYPE，无法修复字典常量"
    enum_end = next(
        (index for index in range(enum_start + 1, len(lines)) if lines[index].strip() == "}"),
        None,
    )
    if enum_end is None:
        return False, "DICT_TYPE enum 未找到结束位置，无法修复字典常量"

    repaired_lines, repaired = repair_enum_member_commas(lines, enum_start, enum_end)
    if repaired:
        file_path.write_text(
            "\n".join(repaired_lines) + ("\n" if text.endswith("\n") else ""),
            encoding="utf-8",
        )
    return True, None


def parse_dict_type_additions(content: str) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    pattern = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*'([^']+)'\s*,?\s*(?://\s*(.*))?$")
    for line in content.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        result.append((match.group(1), match.group(2), (match.group(3) or "").strip()))
    return result


def repair_enum_member_commas(lines: list[str], enum_start: int, enum_end: int) -> tuple[list[str], bool]:
    repaired = False
    updated = list(lines)
    for index in range(enum_start + 1, enum_end):
        if not is_enum_member_line(updated[index]):
            continue
        next_member = next(
            (
                next_index
                for next_index in range(index + 1, enum_end)
                if updated[next_index].strip()
                and not updated[next_index].lstrip().startswith("//")
            ),
            None,
        )
        if next_member is None or not is_enum_member_line(updated[next_member]):
            continue
        repaired_line = ensure_enum_member_trailing_comma(updated[index])
        if repaired_line != updated[index]:
            updated[index] = repaired_line
            repaired = True
    return updated, repaired


def is_enum_member_line(line: str) -> bool:
    return bool(re.match(r"\s*[A-Z][A-Z0-9_]*\s*=\s*['\"][^'\"]+['\"]", line))


def ensure_enum_member_trailing_comma(line: str) -> str:
    code, separator, comment = line.partition("//")
    stripped_code = code.rstrip()
    if stripped_code.endswith(","):
        return line
    repaired = f"{stripped_code},"
    if separator:
        repaired += f" {separator}{comment}"
    return repaired
