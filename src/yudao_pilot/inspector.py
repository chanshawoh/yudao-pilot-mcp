from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import ProjectDetection, ProjectValidation, SUPPORTED_BACKEND_TYPES, SUPPORTED_FRONTEND_TYPES

if TYPE_CHECKING:
    from .config import WorkspaceConfig


@dataclass
class PomFacts:
    path: Path
    group_id: str | None = None
    artifact_id: str | None = None
    parent_group_id: str | None = None
    parent_artifact_id: str | None = None
    packaging: str | None = None
    properties: dict[str, str] = field(default_factory=dict)
    modules: list[str] = field(default_factory=list)
    dependencies: list[tuple[str, str]] = field(default_factory=list)
    dependency_management_imports: list[tuple[str, str]] = field(default_factory=list)
    plugins: list[str] = field(default_factory=list)


def validate_workspace_projects(
    workspace_root: str | Path, config: WorkspaceConfig
) -> dict[str, Any]:
    root = Path(workspace_root).expanduser().resolve()
    backend_validation = validate_backend_project(root, config.projects.backend.path, config.projects.backend.type)
    frontend_validations = [
        validate_frontend_project(root, frontend.path, frontend.type)
        for frontend in config.projects.frontend
    ]

    errors = [
        validation.model_dump()
        for validation in [backend_validation, *frontend_validations]
        if not validation.matches_expected
    ]
    return {
        "ok": not errors,
        "workspace_root": str(root),
        "backend": backend_validation.model_dump(),
        "frontends": [validation.model_dump() for validation in frontend_validations],
        "errors": errors,
    }


def inspect_project_path(project_path: str | Path) -> dict[str, Any]:
    path = Path(project_path).expanduser().resolve()
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "best_match": ProjectDetection(
                kind="unknown",
                supported=False,
                confidence=0.0,
                evidence=["项目路径不存在"],
            ).model_dump(),
            "backend": ProjectDetection(
                kind="backend",
                supported=False,
                confidence=0.0,
                evidence=["项目路径不存在"],
            ).model_dump(),
            "frontend": ProjectDetection(
                kind="frontend",
                supported=False,
                confidence=0.0,
                evidence=["项目路径不存在"],
            ).model_dump(),
            "supported_backend_types": list(SUPPORTED_BACKEND_TYPES),
            "supported_frontend_types": list(SUPPORTED_FRONTEND_TYPES),
        }

    backend_detection = inspect_backend_project(path)
    frontend_detection = inspect_frontend_project(path)

    candidates = [backend_detection, frontend_detection]
    best = max(candidates, key=lambda item: item.confidence)
    if best.confidence <= 0:
        best = ProjectDetection(
            kind="unknown",
            supported=False,
            confidence=0.0,
            evidence=["未发现 pom.xml 或 package.json 可识别指纹"],
        )

    return {
        "path": str(path),
        "exists": True,
        "best_match": best.model_dump(),
        "backend": backend_detection.model_dump(),
        "frontend": frontend_detection.model_dump(),
        "supported_backend_types": list(SUPPORTED_BACKEND_TYPES),
        "supported_frontend_types": list(SUPPORTED_FRONTEND_TYPES),
    }


def validate_backend_project(
    workspace_root: Path, configured_path: str, expected_type: str
) -> ProjectValidation:
    project_path = resolve_project_path(workspace_root, configured_path)
    if not project_path.exists():
        return ProjectValidation(
            kind="backend",
            project_type=expected_type,
            path=str(project_path),
            exists=False,
            matches_expected=False,
            error_code="backend_path_not_found",
            reason=f"后端项目路径不存在: {project_path}",
        )

    detection = inspect_backend_project(project_path)
    matches_expected = detection.supported and detection.detected_type == expected_type
    error_code = None
    reason = None
    if not detection.supported:
        error_code = "backend_not_supported"
        reason = "当前后端项目未识别为受支持的 yudao 后端类型"
    elif detection.detected_type != expected_type:
        error_code = "backend_type_mismatch"
        reason = f"后端项目类型不匹配，期望 {expected_type}，实际识别为 {detection.detected_type or 'unknown'}"

    return ProjectValidation(
        kind="backend",
        project_type=expected_type,
        path=str(project_path),
        exists=True,
        matches_expected=matches_expected,
        detected_type=detection.detected_type,
        confidence=detection.confidence,
        evidence=detection.evidence,
        error_code=error_code,
        reason=reason,
    )


def validate_frontend_project(
    workspace_root: Path, configured_path: str, expected_type: str
) -> ProjectValidation:
    project_path = resolve_project_path(workspace_root, configured_path)
    if not project_path.exists():
        return ProjectValidation(
            kind="frontend",
            project_type=expected_type,
            path=str(project_path),
            exists=False,
            matches_expected=False,
            error_code="frontend_path_not_found",
            reason=f"前端项目路径不存在: {project_path}",
        )

    detection = inspect_frontend_project(project_path)
    matches_expected = detection.supported and detection.detected_type == expected_type
    error_code = None
    reason = None
    if not detection.supported:
        error_code = "frontend_not_supported"
        reason = "当前前端项目未识别为受支持的后台前端类型"
    elif detection.detected_type != expected_type:
        error_code = "frontend_type_mismatch"
        reason = f"前端项目类型不匹配，期望 {expected_type}，实际识别为 {detection.detected_type or 'unknown'}"

    return ProjectValidation(
        kind="frontend",
        project_type=expected_type,
        path=str(project_path),
        exists=True,
        matches_expected=matches_expected,
        detected_type=detection.detected_type,
        confidence=detection.confidence,
        evidence=detection.evidence,
        error_code=error_code,
        reason=reason,
    )


def resolve_project_path(workspace_root: Path, configured_path: str) -> Path:
    return (workspace_root / configured_path).resolve()


def resolve_backend_repo_root(project_path: Path) -> Path:
    if (project_path / "yudao-server").exists():
        return project_path
    if project_path.name == "yudao-server" and project_path.parent.exists():
        return project_path.parent
    return project_path


def resolve_backend_server_root(project_path: Path) -> Path:
    if (project_path / "src" / "main" / "resources").exists():
        return project_path
    if (project_path / "yudao-server" / "src" / "main" / "resources").exists():
        return project_path / "yudao-server"
    return project_path


def inspect_backend_project(project_path: Path) -> ProjectDetection:
    repo_root = resolve_backend_repo_root(project_path)
    server_root = resolve_backend_server_root(project_path)
    root_pom_path = project_path / "pom.xml"
    if not root_pom_path.exists():
        return ProjectDetection(
            kind="backend",
            supported=False,
            confidence=0.0,
            evidence=["未找到根 pom.xml"],
        )

    root_facts = parse_pom(root_pom_path)
    effective_root_facts = root_facts
    if (
        root_facts.artifact_id == "yudao-server"
        and root_facts.parent_group_id == "cn.iocoder.boot"
        and root_facts.parent_artifact_id == "yudao"
    ):
        parent_pom_path = project_path.parent / "pom.xml"
        if parent_pom_path.exists():
            effective_root_facts = parse_pom(parent_pom_path)

    module_facts = collect_module_poms(repo_root, effective_root_facts.modules)
    server_pom_path = server_root / "pom.xml"
    server_facts = parse_pom(server_pom_path) if server_pom_path.exists() and server_pom_path != effective_root_facts.path else None
    facts = [effective_root_facts, *module_facts]
    if server_facts is not None:
        facts.append(server_facts)

    all_dependencies = flatten_dependency_artifacts(facts)
    imported_boms = flatten_imported_boms(facts)
    java_version = resolve_property_value(effective_root_facts.properties, "java.version")
    spring_boot_version = resolve_property_value(effective_root_facts.properties, "spring.boot.version")

    evidence: list[str] = []
    yudao_score = 0
    if effective_root_facts.packaging == "pom":
        yudao_score += 1
        evidence.append("根 pom 的 packaging 为 pom")
    if effective_root_facts.group_id == "cn.iocoder.boot" and effective_root_facts.artifact_id == "yudao":
        yudao_score += 2
        evidence.append("根 pom 的 groupId/artifactId 为 cn.iocoder.boot:yudao")
    elif root_facts.artifact_id == "yudao-server" and root_facts.parent_artifact_id == "yudao":
        yudao_score += 2
        evidence.append("当前 pom 为 yudao-server，且父工程为 cn.iocoder.boot:yudao")
    if ("cn.iocoder.boot", "yudao-dependencies") in imported_boms:
        yudao_score += 3
        evidence.append("dependencyManagement 引入了 cn.iocoder.boot:yudao-dependencies")
    if "yudao-spring-boot-starter-protection" in all_dependencies:
        yudao_score += 2
        evidence.append("依赖中包含 yudao-spring-boot-starter-protection")
    if "yudao-module-system" in all_dependencies:
        yudao_score += 1
        evidence.append("依赖中包含 yudao-module-system")
    if "yudao-module-infra" in all_dependencies:
        yudao_score += 1
        evidence.append("依赖中包含 yudao-module-infra")

    if yudao_score < 5:
        return ProjectDetection(
            kind="backend",
            supported=False,
            confidence=min(0.49, 0.08 * yudao_score),
            evidence=evidence or ["pom.xml 存在，但未识别到足够的 yudao 后端指纹"],
        )

    cloud_markers = collect_cloud_markers(imported_boms, all_dependencies)
    boot3_markers = collect_boot3_markers(effective_root_facts, all_dependencies, spring_boot_version, java_version)
    boot2_markers = collect_boot2_markers(effective_root_facts, all_dependencies, spring_boot_version, java_version)

    evidence.extend(cloud_markers["evidence"])
    evidence.extend(boot3_markers["evidence"])
    evidence.extend(boot2_markers["evidence"])

    detected_type: str | None = None
    if cloud_markers["score"] >= 2:
        detected_type = "yudao-cloud"
    elif boot3_markers["score"] > boot2_markers["score"] and boot3_markers["score"] >= 3:
        detected_type = "ruoyi-vue-pro-jdk17"
    elif boot2_markers["score"] >= 3:
        detected_type = "ruoyi-vue-pro"

    confidence = 0.55 + min(0.4, 0.04 * yudao_score)
    confidence += 0.05 * max(cloud_markers["score"], boot3_markers["score"], boot2_markers["score"])
    confidence = min(confidence, 0.99)

    return ProjectDetection(
        kind="backend",
        detected_type=detected_type,
        supported=detected_type in SUPPORTED_BACKEND_TYPES,
        confidence=confidence if detected_type else min(confidence, 0.79),
        evidence=deduplicate_preserve_order(evidence),
    )


def inspect_frontend_project(project_path: Path) -> ProjectDetection:
    package_json_path = project_path / "package.json"
    if not package_json_path.exists():
        return ProjectDetection(
            kind="frontend",
            supported=False,
            confidence=0.0,
            evidence=["未找到 package.json"],
        )

    package_data = load_package_json(package_json_path)
    dependencies = coerce_dependency_map(package_data.get("dependencies"))
    dev_dependencies = coerce_dependency_map(package_data.get("devDependencies"))
    scripts = coerce_dependency_map(package_data.get("scripts"))
    all_dependency_names = set(dependencies) | set(dev_dependencies)
    package_manager = str(package_data.get("packageManager", ""))

    vben_evidence: list[str] = []
    vben_score = 0
    if any(name.startswith("@vben/") for name in all_dependency_names):
        vben_score += 4
        vben_evidence.append("依赖中存在 @vben/* 工作空间包")
    if any("turbo" in script for script in scripts.values()):
        vben_score += 2
        vben_evidence.append("scripts 中存在 turbo / turbo-run 指令")
    if any(value == "workspace:*" for value in dev_dependencies.values()):
        vben_score += 1
        vben_evidence.append("devDependencies 中存在 workspace:* 版本约束")

    uniapp_evidence: list[str] = []
    uniapp_score = 0
    if "@dcloudio/uni-app" in dependencies:
        uniapp_score += 4
        uniapp_evidence.append("dependencies 中存在 @dcloudio/uni-app")
    dcloud_dependencies = [name for name in all_dependency_names if name.startswith("@dcloudio/uni-")]
    if len(dcloud_dependencies) >= 3:
        uniapp_score += 2
        uniapp_evidence.append("存在多个 @dcloudio/uni-* 依赖")
    if "@dcloudio/vite-plugin-uni" in dev_dependencies:
        uniapp_score += 2
        uniapp_evidence.append("devDependencies 中存在 @dcloudio/vite-plugin-uni")
    if any(name.startswith("@uni-helper/") for name in all_dependency_names):
        uniapp_score += 1
        uniapp_evidence.append("存在 @uni-helper/* 生态依赖")

    vue3_evidence: list[str] = []
    vue3_score = 0
    vue_version = dependencies.get("vue", "")
    if "element-plus" in dependencies:
        vue3_score += 4
        vue3_evidence.append("dependencies 中存在 element-plus")
    if extract_major_version(vue_version) == 3:
        vue3_score += 2
        vue3_evidence.append(f"vue 主版本为 3（{vue_version}）")
    if "@vitejs/plugin-vue" in dev_dependencies:
        vue3_score += 2
        vue3_evidence.append("devDependencies 中存在 @vitejs/plugin-vue")
    if "vite" in dev_dependencies:
        vue3_score += 1
        vue3_evidence.append("devDependencies 中存在 vite")
    if "pinia" in dependencies and "vue-router" in dependencies:
        vue3_score += 1
        vue3_evidence.append("dependencies 中同时存在 pinia 和 vue-router")

    candidates = [
        ("yudao-ui-admin-vben", vben_score, vben_evidence),
        ("yudao-ui-admin-uniapp", uniapp_score, uniapp_evidence),
        ("yudao-ui-admin-vue3", vue3_score, vue3_evidence),
    ]
    detected_type, best_score, best_evidence = max(candidates, key=lambda item: item[1])
    if best_score < 4:
        return ProjectDetection(
            kind="frontend",
            supported=False,
            confidence=min(0.49, 0.08 * best_score),
            evidence=best_evidence or ["package.json 存在，但未识别到足够的前端项目指纹"],
        )

    confidence = min(0.99, 0.52 + 0.06 * best_score)
    return ProjectDetection(
        kind="frontend",
        detected_type=detected_type,
        supported=detected_type in SUPPORTED_FRONTEND_TYPES,
        confidence=confidence,
        evidence=best_evidence,
    )


def parse_pom(pom_path: Path) -> PomFacts:
    text = pom_path.read_text(encoding="utf-8", errors="ignore")
    root = ET.fromstring(text)
    namespace = namespace_prefix(root.tag)

    facts = PomFacts(
        path=pom_path,
        group_id=find_text(root, f"{namespace}groupId") or find_text(root, f"{namespace}parent/{namespace}groupId"),
        artifact_id=find_text(root, f"{namespace}artifactId"),
        parent_group_id=find_text(root, f"{namespace}parent/{namespace}groupId"),
        parent_artifact_id=find_text(root, f"{namespace}parent/{namespace}artifactId"),
        packaging=find_text(root, f"{namespace}packaging") or "jar",
        properties=read_properties(root, namespace),
        modules=[value for value in find_text_list(root, f"{namespace}modules/{namespace}module") if value],
        dependencies=read_dependencies(root, namespace),
        dependency_management_imports=read_imported_boms(root, namespace),
        plugins=find_text_list(root, f".//{namespace}plugin/{namespace}artifactId"),
    )
    return facts


def collect_module_poms(project_path: Path, modules: list[str]) -> list[PomFacts]:
    collected: list[PomFacts] = []
    for module in modules:
        module_pom_path = (project_path / module / "pom.xml").resolve()
        if module_pom_path.exists():
            collected.append(parse_pom(module_pom_path))
    return collected


def flatten_dependency_artifacts(facts_list: list[PomFacts]) -> set[str]:
    artifacts: set[str] = set()
    for facts in facts_list:
        for _, artifact_id in facts.dependencies:
            artifacts.add(artifact_id)
    return artifacts


def flatten_imported_boms(facts_list: list[PomFacts]) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for facts in facts_list:
        for dependency in facts.dependency_management_imports:
            result.add(dependency)
    return result


def collect_cloud_markers(
    imported_boms: set[tuple[str, str]], dependency_artifacts: set[str]
) -> dict[str, Any]:
    score = 0
    evidence: list[str] = []
    cloud_boms = {
        ("org.springframework.cloud", "spring-cloud-dependencies"),
        ("com.alibaba.cloud", "spring-cloud-alibaba-dependencies"),
    }
    for bom in cloud_boms:
        if bom in imported_boms:
            score += 2
            evidence.append(f"dependencyManagement 引入了 {bom[0]}:{bom[1]}")

    cloud_artifacts = {
        "spring-cloud-starter-gateway",
        "spring-cloud-starter-bootstrap",
        "spring-cloud-starter-openfeign",
        "spring-cloud-starter-loadbalancer",
        "spring-cloud-starter-alibaba-nacos-discovery",
        "spring-cloud-starter-alibaba-nacos-config",
        "spring-cloud-starter-alibaba-sentinel",
    }
    for artifact in sorted(cloud_artifacts & dependency_artifacts):
        score += 1
        evidence.append(f"依赖中包含 {artifact}")
    return {"score": score, "evidence": evidence}


def collect_boot3_markers(
    root_facts: PomFacts,
    dependency_artifacts: set[str],
    spring_boot_version: str | None,
    java_version: str | None,
) -> dict[str, Any]:
    score = 0
    evidence: list[str] = []
    if extract_major_version(spring_boot_version or "") == 3:
        score += 3
        evidence.append(f"spring.boot.version 为 3.x（{spring_boot_version}）")
    if parse_java_version(java_version) >= 17:
        score += 2
        evidence.append(f"java.version 为 {java_version}")

    artifact_markers = {
        "druid-spring-boot-3-starter",
        "mybatis-plus-spring-boot3-starter",
        "dynamic-datasource-spring-boot3-starter",
        "knife4j-openapi3-jakarta-spring-boot-starter",
        "springdoc-openapi-starter-webmvc-ui",
    }
    for artifact in sorted(artifact_markers & dependency_artifacts):
        score += 1
        evidence.append(f"依赖中包含 {artifact}")

    if "maven-compiler-plugin" in root_facts.plugins and parse_java_version(java_version) >= 17:
        score += 1
    return {"score": score, "evidence": evidence}


def collect_boot2_markers(
    root_facts: PomFacts,
    dependency_artifacts: set[str],
    spring_boot_version: str | None,
    java_version: str | None,
) -> dict[str, Any]:
    score = 0
    evidence: list[str] = []
    if extract_major_version(spring_boot_version or "") == 2:
        score += 3
        evidence.append(f"spring.boot.version 为 2.x（{spring_boot_version}）")
    if parse_java_version(java_version) == 8:
        score += 2
        evidence.append(f"java.version 为 {java_version}")

    artifact_markers = {
        "druid-spring-boot-starter",
        "mybatis-plus-boot-starter",
        "dynamic-datasource-spring-boot-starter",
        "knife4j-openapi3-spring-boot-starter",
        "springdoc-openapi-ui",
        "spring-framework-bom",
        "spring-security-bom",
    }
    imported_or_dependencies = dependency_artifacts | {artifact_id for _, artifact_id in root_facts.dependency_management_imports}
    for artifact in sorted(artifact_markers & imported_or_dependencies):
        score += 1
        evidence.append(f"依赖中包含 {artifact}")
    return {"score": score, "evidence": evidence}


def namespace_prefix(root_tag: str) -> str:
    if root_tag.startswith("{"):
        namespace = root_tag.split("}", 1)[0].strip("{")
        return f"{{{namespace}}}"
    return ""


def read_properties(root: ET.Element, namespace: str) -> dict[str, str]:
    properties_node = root.find(f"{namespace}properties")
    if properties_node is None:
        return {}
    result: dict[str, str] = {}
    for child in properties_node:
        tag = child.tag.split("}", 1)[-1]
        result[tag] = (child.text or "").strip()
    return result


def read_dependencies(root: ET.Element, namespace: str) -> list[tuple[str, str]]:
    dependencies: list[tuple[str, str]] = []
    for node in root.findall(f".//{namespace}dependency"):
        group_id = find_text(node, f"{namespace}groupId")
        artifact_id = find_text(node, f"{namespace}artifactId")
        if group_id and artifact_id:
            dependencies.append((group_id, artifact_id))
    return dependencies


def read_imported_boms(root: ET.Element, namespace: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for node in root.findall(f".//{namespace}dependencyManagement/{namespace}dependencies/{namespace}dependency"):
        group_id = find_text(node, f"{namespace}groupId")
        artifact_id = find_text(node, f"{namespace}artifactId")
        scope = find_text(node, f"{namespace}scope")
        dep_type = find_text(node, f"{namespace}type")
        if group_id and artifact_id and scope == "import" and dep_type == "pom":
            result.append((group_id, artifact_id))
    return result


def find_text(node: ET.Element, path: str) -> str | None:
    target = node.find(path)
    if target is None or target.text is None:
        return None
    return target.text.strip()


def find_text_list(node: ET.Element, path: str) -> list[str]:
    result: list[str] = []
    for target in node.findall(path):
        if target.text:
            result.append(target.text.strip())
    return result


def resolve_property_value(properties: dict[str, str], key: str) -> str | None:
    raw_value = properties.get(key)
    if not raw_value:
        return raw_value

    match = re.fullmatch(r"\$\{([^}]+)\}", raw_value)
    if match:
        return properties.get(match.group(1), raw_value)
    return raw_value


def parse_java_version(java_version: str | None) -> int:
    if not java_version:
        return 0
    normalized = java_version.strip()
    if normalized.startswith("1."):
        normalized = normalized.split(".", 1)[1]
    major_text = normalized.split(".", 1)[0]
    try:
        return int(major_text)
    except ValueError:
        return 0


def extract_major_version(version: str) -> int:
    match = re.search(r"(\d+)", version)
    if not match:
        return 0
    return int(match.group(1))


def load_package_json(package_json: Path) -> dict[str, Any]:
    try:
        return json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def coerce_dependency_map(raw_value: Any) -> dict[str, str]:
    if not isinstance(raw_value, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw_value.items():
        if isinstance(key, str) and isinstance(value, str):
            result[key] = value
    return result


def deduplicate_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
