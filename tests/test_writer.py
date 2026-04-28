from __future__ import annotations

from pathlib import Path

from yudao_pilot.config import WorkspaceConfig
from yudao_pilot.models import GeneratedFile
from yudao_pilot.writer import resolve_target_base_dir, write_generated_files


def test_backend_target_base_dir_resolves_repo_root_when_configured_to_yudao_server(repo_root: Path) -> None:
    backend_server_path = repo_root / "yudao-projects" / "ruoyi-vue-pro-jdk17" / "yudao-server"
    config = WorkspaceConfig.model_validate(
        {
            "projects": {
                "backend": {
                    "path": str(backend_server_path),
                    "type": "ruoyi-vue-pro-jdk17",
                },
                "frontend": [],
            },
            "codegen": {"routing": {"mode": "auto"}},
        }
    )

    resolved = resolve_target_base_dir(repo_root, config, "backend", "ruoyi-vue-pro-jdk17")

    assert resolved == backend_server_path.parent


def test_backend_writer_skips_when_module_does_not_exist(repo_root: Path, tmp_path: Path) -> None:
    config = WorkspaceConfig.model_validate(
        {
            "projects": {
                "backend": {
                    "path": str(repo_root / "yudao-projects" / "ruoyi-vue-pro-jdk17"),
                    "type": "ruoyi-vue-pro-jdk17",
                },
                "frontend": [],
            },
            "codegen": {"routing": {"mode": "auto"}},
        }
    )
    result = write_generated_files(
        tmp_path,
        config,
        [
            GeneratedFile(
                target_kind="backend",
                target_type="ruoyi-vue-pro-jdk17",
                relative_path="yudao-module-not-exists/src/main/java/demo/Test.java",
                content="class Test {}",
            )
        ],
    )

    assert result["ok"] is False
    assert result["results"][0]["reason"] == "目标后端模块不存在，拒绝创建新的模块结构"


def test_backend_writer_rejects_paths_that_escape_module(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    module_root = repo_root / "yudao-module-member"
    module_root.mkdir(parents=True)
    root_pom = repo_root / "pom.xml"
    root_pom.write_text("original", encoding="utf-8")
    config = WorkspaceConfig.model_validate(
        {
            "projects": {
                "backend": {
                    "path": str(repo_root),
                    "type": "ruoyi-vue-pro-jdk17",
                },
                "frontend": [],
            },
            "codegen": {"routing": {"mode": "auto"}},
        }
    )

    result = write_generated_files(
        tmp_path,
        config,
        [
            GeneratedFile(
                target_kind="backend",
                target_type="ruoyi-vue-pro-jdk17",
                relative_path="yudao-module-member/../pom.xml",
                content="overwritten",
            )
        ],
    )

    assert result["ok"] is False
    assert result["results"][0]["reason"] == "目标路径越界，拒绝写入"
    assert root_pom.read_text(encoding="utf-8") == "original"


def test_backend_writer_rejects_manual_error_code_path_escape(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    module_root = repo_root / "yudao-module-member"
    module_root.mkdir(parents=True)
    outside_root = tmp_path / "outside"
    outside_range = outside_root / "yudao-framework/yudao-common/src/main/java/cn/iocoder/yudao/framework/common/exception/enums/ServiceErrorCodeRange.java"
    outside_range.parent.mkdir(parents=True, exist_ok=True)
    outside_range.write_text(
        """package cn.iocoder.yudao.framework.common.exception.enums;

public class ServiceErrorCodeRange {

    // 模块 member 错误码区间 [1-004-000-000 ~ 1-005-000-000)

}
""",
        encoding="utf-8",
    )
    config = WorkspaceConfig.model_validate(
        {
            "projects": {
                "backend": {
                    "path": str(repo_root),
                    "type": "ruoyi-vue-pro-jdk17",
                },
                "frontend": [],
            },
            "codegen": {"routing": {"mode": "auto"}},
        }
    )

    result = write_generated_files(
        tmp_path,
        config,
        [
            GeneratedFile(
                target_kind="backend",
                target_type="ruoyi-vue-pro-jdk17",
                relative_path="yudao-module-member/../../outside/src/main/java/cn/iocoder/yudao/module/member/enums/ErrorCodeConstants_手动操作.java",
                content="""package cn.iocoder.yudao.module.member.enums;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;

// Yudao Pilot Section: 商户
public interface ErrorCodeConstants_手动操作 {

    ErrorCode MERCHANT_NOT_EXISTS = new ErrorCode(0, "商户不存在");
}
""",
            )
        ],
    )

    assert result["ok"] is False
    assert result["results"][0]["reason"] == "目标路径越界，拒绝写入"
    assert not (
        outside_root
        / "src/main/java/cn/iocoder/yudao/module/member/enums/ErrorCodeConstants.java"
    ).exists()


def test_backend_writer_merges_manual_error_code_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    constants_path = repo_root / "yudao-module-member/src/main/java/cn/iocoder/yudao/module/member/enums/ErrorCodeConstants.java"
    constants_path.parent.mkdir(parents=True, exist_ok=True)
    constants_path.write_text(
        """package cn.iocoder.yudao.module.member.enums;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;

/**
 * Member 错误码枚举类
 *
 * member 系统，使用 1-004-000-000 段
 */
public interface ErrorCodeConstants {

    // ========== 用户相关 1-004-001-000 ==========
    ErrorCode USER_NOT_EXISTS = new ErrorCode(1_004_001_000, "用户不存在");
}
""",
        encoding="utf-8",
    )
    range_path = repo_root / "yudao-framework/yudao-common/src/main/java/cn/iocoder/yudao/framework/common/exception/enums/ServiceErrorCodeRange.java"
    range_path.parent.mkdir(parents=True, exist_ok=True)
    range_path.write_text(
        """package cn.iocoder.yudao.framework.common.exception.enums;

public class ServiceErrorCodeRange {

    // 模块 member 错误码区间 [1-004-000-000 ~ 1-005-000-000)

}
""",
        encoding="utf-8",
    )
    config = WorkspaceConfig.model_validate(
        {
            "projects": {
                "backend": {
                    "path": str(repo_root),
                    "type": "ruoyi-vue-pro-jdk17",
                },
                "frontend": [],
            },
            "codegen": {"routing": {"mode": "auto"}},
        }
    )

    result = write_generated_files(
        tmp_path,
        config,
        [
            GeneratedFile(
                target_kind="backend",
                target_type="ruoyi-vue-pro-jdk17",
                relative_path="yudao-module-member/src/main/java/cn/iocoder/yudao/module/member/enums/ErrorCodeConstants_手动操作.java",
                content="""package cn.iocoder.yudao.module.member.enums;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;

// Yudao Pilot Section: 商户
public interface ErrorCodeConstants_手动操作 {

    ErrorCode MERCHANT_NOT_EXISTS = new ErrorCode(0, "商户不存在");
    ErrorCode MERCHANT_NAME_EXISTS = new ErrorCode(0, "商户名称已存在");
}
""",
            )
        ],
    )

    assert result["ok"] is True
    merged_text = constants_path.read_text(encoding="utf-8")
    assert "商户 1-004-002-000" in merged_text
    assert 'ErrorCode MERCHANT_NOT_EXISTS = new ErrorCode(1_004_002_000, "商户不存在");' in merged_text
    assert 'ErrorCode MERCHANT_NAME_EXISTS = new ErrorCode(1_004_002_001, "商户名称已存在");' in merged_text
    assert not (repo_root / "yudao-module-member/src/main/java/cn/iocoder/yudao/module/member/enums/ErrorCodeConstants_手动操作.java").exists()


def test_backend_writer_updates_existing_manual_error_code_message(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    constants_path = repo_root / "yudao-module-member/src/main/java/cn/iocoder/yudao/module/member/enums/ErrorCodeConstants.java"
    constants_path.parent.mkdir(parents=True, exist_ok=True)
    constants_path.write_text(
        """package cn.iocoder.yudao.module.member.enums;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;

/**
 * Member 错误码枚举类
 *
 * member 系统，使用 1-004-000-000 段
 */
public interface ErrorCodeConstants {

    // ========== 商家表 1-004-013-000 ==========
    ErrorCode MERCHANT_NOT_EXISTS = new ErrorCode(1_004_013_000, "商家表不存在");
}
""",
        encoding="utf-8",
    )
    range_path = repo_root / "yudao-framework/yudao-common/src/main/java/cn/iocoder/yudao/framework/common/exception/enums/ServiceErrorCodeRange.java"
    range_path.parent.mkdir(parents=True, exist_ok=True)
    range_path.write_text(
        """package cn.iocoder.yudao.framework.common.exception.enums;

public class ServiceErrorCodeRange {

    // 模块 member 错误码区间 [1-004-000-000 ~ 1-005-000-000)

}
""",
        encoding="utf-8",
    )
    config = WorkspaceConfig.model_validate(
        {
            "projects": {
                "backend": {
                    "path": str(repo_root),
                    "type": "ruoyi-vue-pro-jdk17",
                },
                "frontend": [],
            },
            "codegen": {"routing": {"mode": "auto"}},
        }
    )

    result = write_generated_files(
        tmp_path,
        config,
        [
            GeneratedFile(
                target_kind="backend",
                target_type="ruoyi-vue-pro-jdk17",
                relative_path="yudao-module-member/src/main/java/cn/iocoder/yudao/module/member/enums/ErrorCodeConstants_手动操作.java",
                content="""package cn.iocoder.yudao.module.member.enums;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;

// Yudao Pilot Section: 商家
public interface ErrorCodeConstants_手动操作 {

    ErrorCode MERCHANT_NOT_EXISTS = new ErrorCode(0, "商家不存在");
}
""",
            )
        ],
    )

    assert result["ok"] is True
    merged_text = constants_path.read_text(encoding="utf-8")
    assert "商家 1-004-013-000" in merged_text
    assert 'ErrorCode MERCHANT_NOT_EXISTS = new ErrorCode(1_004_013_000, "商家不存在");' in merged_text


def test_backend_writer_treats_existing_manual_error_code_as_success(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    constants_path = repo_root / "yudao-module-hotel/src/main/java/cn/iocoder/yudao/module/hotel/enums/ErrorCodeConstants.java"
    constants_path.parent.mkdir(parents=True, exist_ok=True)
    constants_path.write_text(
        """package cn.iocoder.yudao.module.hotel.enums;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;

/**
 * Hotel 错误码枚举类
 *
 * hotel 系统，使用 1-023-000-000 段
 */
public interface ErrorCodeConstants {

    // ========== 酒店品牌 1-023-001-000 ==========
    ErrorCode HOTEL_BRAND_NOT_EXISTS = new ErrorCode(1_023_001_000, "酒店品牌不存在");
}
""",
        encoding="utf-8",
    )
    range_path = repo_root / "yudao-framework/yudao-common/src/main/java/cn/iocoder/yudao/framework/common/exception/enums/ServiceErrorCodeRange.java"
    range_path.parent.mkdir(parents=True, exist_ok=True)
    range_path.write_text(
        """package cn.iocoder.yudao.framework.common.exception.enums;

public class ServiceErrorCodeRange {

    // 模块 hotel 错误码区间 [1-023-000-000 ~ 1-024-000-000)

}
""",
        encoding="utf-8",
    )
    config = WorkspaceConfig.model_validate(
        {
            "projects": {
                "backend": {
                    "path": str(repo_root),
                    "type": "ruoyi-vue-pro-jdk17",
                },
                "frontend": [],
            },
            "codegen": {"routing": {"mode": "auto"}},
        }
    )

    result = write_generated_files(
        tmp_path,
        config,
        [
            GeneratedFile(
                target_kind="backend",
                target_type="ruoyi-vue-pro-jdk17",
                relative_path="yudao-module-hotel/src/main/java/cn/iocoder/yudao/module/hotel/enums/ErrorCodeConstants_手动操作.java",
                content="""package cn.iocoder.yudao.module.hotel.enums;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;

// Yudao Pilot Section: 酒店品牌
public interface ErrorCodeConstants_手动操作 {

    ErrorCode HOTEL_BRAND_NOT_EXISTS = new ErrorCode(0, "酒店品牌不存在");
}
""",
            )
        ],
    )

    assert result["ok"] is True
    assert result["results"][0]["written"] is True
