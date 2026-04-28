from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import GeneratedFile


MANUAL_ERROR_CODE_FILENAME = "ErrorCodeConstants_手动操作.java"
TARGET_ERROR_CODE_FILENAME = "ErrorCodeConstants.java"
SERVICE_RANGE_RELATIVE_PATH = Path(
    "yudao-framework/yudao-common/src/main/java/cn/iocoder/yudao/framework/common/exception/enums/ServiceErrorCodeRange.java"
)

SECTION_META_RE = re.compile(r"//\s*Yudao Pilot Section:\s*(?P<title>.+)")
SECTION_COMMENT_RE = re.compile(
    r"^[ \t]*//\s*=+\s*(?P<title>.*?)\s+1-(?P<system>\d{3})-(?P<section>\d{3})-000\s*=+.*?$",
    re.M,
)
CONSTANT_RE = re.compile(
    r'ErrorCode\s+(?P<name>[A-Z0-9_]+)\s*=\s*new ErrorCode\([^,]+,\s*"(?P<message>(?:[^"\\]|\\.)*)"\);'
)
MODULE_RANGE_RE = re.compile(
    r"//\s*模块\s+(?P<module>[a-zA-Z0-9_-]+)\s+错误码区间\s+\[1-(?P<system>\d{3})-000-000 ~ 1-(?P<next>\d{3})-000-000\)"
)
SYSTEM_PREFIX_RE = re.compile(r"使用\s+1-(?P<system>\d{3})-000-000\s+段")


@dataclass
class ErrorCodeConstant:
    name: str
    message: str


@dataclass
class SectionMatch:
    title: str
    section: int
    body_start: int
    body_end: int


def is_manual_error_code_file(relative_path: str) -> bool:
    return relative_path.endswith(MANUAL_ERROR_CODE_FILENAME)


def merge_manual_error_code_file(
    repo_root: Path, generated_file: GeneratedFile
) -> tuple[bool, str, str | None]:
    repo_root = repo_root.resolve()
    manual_path = (repo_root / generated_file.relative_path).resolve()
    actual_path = resolve_actual_error_code_path(repo_root, generated_file.relative_path)
    if not is_within_root(manual_path, repo_root) or not is_within_root(actual_path, repo_root):
        return False, str(actual_path), "目标路径越界，拒绝写入"
    module_name = resolve_module_name_from_relative_path(generated_file.relative_path)
    if module_name is None:
        return False, str(actual_path), "无法从错误码文件路径中解析模块名"

    service_range_path = repo_root / SERVICE_RANGE_RELATIVE_PATH
    if not service_range_path.exists():
        return False, str(actual_path), "未找到 ServiceErrorCodeRange.java，无法维护错误码范围"

    section_title, constants = parse_manual_error_code_content(generated_file.content)
    if not constants:
        return False, str(actual_path), "错误码占位文件中未解析到可合并的 ErrorCode 常量"

    system_segment, range_updated = ensure_module_system_segment(
        module_name, actual_path, service_range_path
    )
    constants_text = load_or_create_error_constants_text(actual_path, module_name, system_segment)
    merged_text, merged, reason = merge_constants_text(
        constants_text, section_title, system_segment, constants
    )
    if not merged:
        if reason == "目标 ErrorCodeConstants.java 中已存在同名错误码常量":
            if manual_path.exists():
                manual_path.unlink()
            return True, str(actual_path), "错误码常量已存在，跳过合并"
        return False, str(actual_path), reason

    actual_path.parent.mkdir(parents=True, exist_ok=True)
    actual_path.write_text(merged_text, encoding="utf-8")
    if manual_path.exists():
        manual_path.unlink()
    merged_reason = "已合并到 ErrorCodeConstants.java"
    if range_updated:
        merged_reason += "，并更新 ServiceErrorCodeRange.java"
    return True, str(actual_path), merged_reason


def resolve_actual_error_code_path(repo_root: Path, relative_path: str) -> Path:
    return (repo_root / relative_path.replace(MANUAL_ERROR_CODE_FILENAME, TARGET_ERROR_CODE_FILENAME)).resolve()


def is_within_root(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_module_name_from_relative_path(relative_path: str) -> str | None:
    normalized = relative_path.replace("\\", "/")
    match = re.search(r"/module/(?P<module>[a-zA-Z0-9_]+)/enums/", normalized)
    return match.group("module") if match else None


def parse_manual_error_code_content(content: str) -> tuple[str, list[ErrorCodeConstant]]:
    section_title = ""
    meta_match = SECTION_META_RE.search(content)
    if meta_match:
        section_title = meta_match.group("title").strip()
    constants = [
        ErrorCodeConstant(
            name=match.group("name"),
            message=match.group("message").replace('\\"', '"'),
        )
        for match in CONSTANT_RE.finditer(content)
    ]
    if not section_title and constants:
        section_title = infer_section_title(constants[0])
    return section_title or "未命名业务", constants


def infer_section_title(constant: ErrorCodeConstant) -> str:
    for splitter in ("不存在", "已存在", "不能为空", "不正确", "失败", "错误", "异常", "不可用"):
        if splitter in constant.message:
            prefix = constant.message.split(splitter, 1)[0].strip()
            if prefix:
                return prefix
    return snake_upper_to_title(constant.name)


def snake_upper_to_title(value: str) -> str:
    for suffix in ("_NOT_EXISTS", "_EXISTS", "_USED", "_DISABLED", "_ERROR", "_FAILURE", "_FAIL"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return "".join(part.capitalize() for part in value.lower().split("_"))


def ensure_module_system_segment(
    module_name: str, actual_path: Path, service_range_path: Path
) -> tuple[int, bool]:
    if actual_path.exists():
        system_segment = parse_system_segment_from_constants(actual_path.read_text(encoding="utf-8"))
        if system_segment is not None:
            return system_segment, False

    service_range_text = service_range_path.read_text(encoding="utf-8")
    module_ranges = {
        match.group("module"): int(match.group("system"))
        for match in MODULE_RANGE_RE.finditer(service_range_text)
    }
    if module_name in module_ranges:
        return module_ranges[module_name], False

    next_segment = max(module_ranges.values(), default=0) + 1
    service_range_path.write_text(
        append_module_range(service_range_text, module_name, next_segment),
        encoding="utf-8",
    )
    return next_segment, True


def parse_system_segment_from_constants(content: str) -> int | None:
    match = SYSTEM_PREFIX_RE.search(content)
    if match:
        return int(match.group("system"))
    match = re.search(r"1_(?P<system>\d{3})_(?P<section>\d{3})_(?P<offset>\d{3})", content)
    return int(match.group("system")) if match else None


def append_module_range(content: str, module_name: str, system_segment: int) -> str:
    line = (
        f"    // 模块 {module_name} 错误码区间 "
        f"[1-{system_segment:03d}-000-000 ~ 1-{system_segment + 1:03d}-000-000)"
    )
    closing = content.rfind("}")
    if closing == -1:
        return content.rstrip() + "\n\n" + line + "\n"
    prefix = content[:closing].rstrip()
    suffix = content[closing:]
    return prefix + "\n\n" + line + "\n\n" + suffix.lstrip()


def load_or_create_error_constants_text(actual_path: Path, module_name: str, system_segment: int) -> str:
    if actual_path.exists():
        return actual_path.read_text(encoding="utf-8")
    package_name = java_package_from_path(actual_path)
    return (
        f"package {package_name};\n\n"
        "import cn.iocoder.yudao.framework.common.exception.ErrorCode;\n\n"
        "/**\n"
        f" * {module_name.capitalize()} 错误码枚举类\n"
        " *\n"
        f" * {module_name} 系统，使用 1-{system_segment:03d}-000-000 段\n"
        " */\n"
        "public interface ErrorCodeConstants {\n\n"
        "}\n"
    )


def java_package_from_path(actual_path: Path) -> str:
    normalized = actual_path.as_posix()
    marker = "/src/main/java/"
    if marker not in normalized:
        return "cn.iocoder.yudao"
    return normalized.split(marker, 1)[1].rsplit("/", 1)[0].replace("/", ".")


def merge_constants_text(
    content: str,
    section_title: str,
    system_segment: int,
    constants: list[ErrorCodeConstant],
) -> tuple[str, bool, str | None]:
    updated_content = content
    changed = False
    existing_names = set(re.findall(r"ErrorCode\s+([A-Z0-9_]+)\s*=", updated_content))
    existing_constants = [constant for constant in constants if constant.name in existing_names]
    new_constants = [constant for constant in constants if constant.name not in existing_names]

    if existing_constants:
        updated_content, section_changed = update_existing_section_title(
            updated_content, section_title, existing_constants, system_segment
        )
        changed = changed or section_changed
        updated_content, message_changed = update_existing_constant_messages(
            updated_content, existing_constants
        )
        changed = changed or message_changed

    if not new_constants:
        if changed:
            return updated_content, True, None
        return updated_content, False, "目标 ErrorCodeConstants.java 中已存在同名错误码常量"

    section_match = find_section_by_title(updated_content, section_title, system_segment)
    if section_match is None:
        section_number = next_section_number(updated_content, system_segment)
        block = render_section_block(section_title, system_segment, section_number, 0, new_constants)
        return insert_before_closing_brace(updated_content, block), True, None

    next_offset = next_section_offset(
        updated_content[section_match.body_start:section_match.body_end],
        system_segment,
        section_match.section,
    )
    addition = render_constant_lines(system_segment, section_match.section, next_offset, new_constants)
    merged = (
        updated_content[:section_match.body_end].rstrip()
        + "\n"
        + addition
        + "\n"
        + updated_content[section_match.body_end:]
    )
    return merged, True, None


def update_existing_section_title(
    content: str,
    section_title: str,
    constants: list[ErrorCodeConstant],
    system_segment: int,
) -> tuple[str, bool]:
    first_pos = None
    for constant in constants:
        match = re.search(rf"ErrorCode\s+{re.escape(constant.name)}\s*=", content)
        if match:
            first_pos = match.start()
            break
    if first_pos is None:
        return content, False

    matches = list(SECTION_COMMENT_RE.finditer(content))
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else content.rfind("}")
        if not (start <= first_pos < end):
            continue
        if int(match.group("system")) != system_segment:
            return content, False
        old_title = match.group("title").strip()
        if old_title == section_title:
            return content, False
        old_line = match.group(0)
        new_line = old_line.replace(old_title, section_title, 1)
        return content[: match.start()] + new_line + content[match.end():], True
    return content, False


def update_existing_constant_messages(
    content: str, constants: list[ErrorCodeConstant]
) -> tuple[str, bool]:
    changed = False
    updated = content
    for constant in constants:
        pattern = re.compile(
            rf'(ErrorCode\s+{re.escape(constant.name)}\s*=\s*new ErrorCode\([^,]+,\s*")(?P<message>(?:[^"\\]|\\.)*)("\);)'
        )
        replacement = constant.message.replace('"', '\\"')

        def repl(match: re.Match[str]) -> str:
            nonlocal changed
            if match.group("message") == replacement:
                return match.group(0)
            changed = True
            return match.group(1) + replacement + match.group(3)

        updated = pattern.sub(repl, updated, count=1)
    return updated, changed


def find_section_by_title(content: str, section_title: str, system_segment: int) -> SectionMatch | None:
    matches = list(SECTION_COMMENT_RE.finditer(content))
    for index, match in enumerate(matches):
        if match.group("title").strip() != section_title or int(match.group("system")) != system_segment:
            continue
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else content.rfind("}")
        return SectionMatch(
            title=match.group("title").strip(),
            section=int(match.group("section")),
            body_start=body_start,
            body_end=body_end,
        )
    return None


def next_section_number(content: str, system_segment: int) -> int:
    pattern = re.compile(rf"1_{system_segment:03d}_(?P<section>\d{{3}})_(?P<offset>\d{{3}})")
    values = [int(match.group("section")) for match in pattern.finditer(content)]
    return (max(values) + 1) if values else 1


def next_section_offset(content: str, system_segment: int, section_number: int) -> int:
    pattern = re.compile(rf"1_{system_segment:03d}_{section_number:03d}_(?P<offset>\d{{3}})")
    values = [int(match.group("offset")) for match in pattern.finditer(content)]
    return (max(values) + 1) if values else 0


def render_section_block(
    section_title: str,
    system_segment: int,
    section_number: int,
    start_offset: int,
    constants: list[ErrorCodeConstant],
) -> str:
    title_line = f"    // ========== {section_title} 1-{system_segment:03d}-{section_number:03d}-000 =========="
    return title_line + "\n" + render_constant_lines(system_segment, section_number, start_offset, constants)


def render_constant_lines(
    system_segment: int,
    section_number: int,
    start_offset: int,
    constants: list[ErrorCodeConstant],
) -> str:
    lines: list[str] = []
    for index, constant in enumerate(constants):
        code = f"1_{system_segment:03d}_{section_number:03d}_{start_offset + index:03d}"
        message = constant.message.replace('"', '\\"')
        lines.append(f'    ErrorCode {constant.name} = new ErrorCode({code}, "{message}");')
    return "\n".join(lines)


def insert_before_closing_brace(content: str, block: str) -> str:
    closing = content.rfind("}")
    if closing == -1:
        return content.rstrip() + "\n\n" + block + "\n"
    prefix = content[:closing].rstrip()
    suffix = content[closing:]
    return prefix + "\n\n" + block + "\n\n" + suffix.lstrip()
