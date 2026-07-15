from __future__ import annotations

from pathlib import Path
import sys
from textwrap import dedent

import yaml

from yudao_pilot import schema as schema_module
from yudao_pilot.database import apply_menu_plan_to_database
from yudao_pilot.inspector import scan_backend_table_entities
from yudao_pilot.models import TableResolution
from yudao_pilot.server import (
    generate_codegen_scaffold_tool,
    generate_codegen_sql_tool,
    infer_table_resolution,
    inspect_codegen_context_tool,
    inspect_table_schema_tool,
    resolve_database_config_tool,
    snake_to_pascal,
    _create_module_scaffold,
    _ensure_module_enabled,
)
from yudao_pilot.codegen import (
    build_codegen_context,
    build_frontend_business_path,
    build_generated_file_plan,
    normalize_backend_business_name,
    normalize_backend_module_dir,
    resolve_backend_codegen_target,
    resolve_backend_business_name,
    resolve_backend_codegen_defaults,
    resolve_frontend_codegen_targets,
    write_mysql_migration,
)
from yudao_pilot.config import WorkspaceConfig
from yudao_pilot.scaffold import (
    generate_scaffold_files,
    render_backend_file,
    render_vue3_form_item,
    render_vue3_query_item,
    render_frontend_file,
    build_vue3_dict_import_line,
    render_vue3_dict_options_expr,
    render_vue3_dict_type_expr,
)
from yudao_pilot.sql_codegen import build_dict_plan, merge_sql_snippet, resolve_h2_sql_plan


def test_missing_backend_codegen_config_returns_safe_defaults(tmp_path: Path) -> None:
    defaults = resolve_backend_codegen_defaults(tmp_path / "backend", "local")

    assert defaults["resolved"] is False
    assert defaults["base_package"] == "cn.iocoder.yudao"
    assert defaults["db_schemas"] == []
    assert defaults["unit_test_enable"] is False


def _rewrite_backend_path(workspace_root: Path, backend_path: Path) -> None:
    config_path = workspace_root / ".yudao-pilot" / "config.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_config["projects"]["backend"]["path"] = str(backend_path)
    config_path.write_text(
        yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _create_fake_backend(
    root: Path,
    *,
    database_name: str = "demo",
    migration_files: dict[str, str] | None = None,
) -> Path:
    backend_root = root / "fake-backend"
    resources_root = backend_root / "src" / "main" / "resources"
    resources_root.mkdir(parents=True, exist_ok=True)
    (backend_root / "sql" / "mysql" / "migrations").mkdir(parents=True, exist_ok=True)
    (resources_root / "application-local.yaml").write_text(
        dedent(
            f"""\
            spring:
              datasource:
                url: jdbc:mysql://127.0.0.1:3306/{database_name}?useSSL=false
                username: root
                password: 123456
            """
        ),
        encoding="utf-8",
    )
    for filename, content in (migration_files or {}).items():
        (backend_root / "sql" / "mysql" / "migrations" / filename).write_text(
            content,
            encoding="utf-8",
        )
    return backend_root


def test_resolve_database_config_from_backend_local(workspace_builder) -> None:
    workspace_root = workspace_builder()
    result = resolve_database_config_tool(str(workspace_root))

    assert result["ok"] is True
    assert result["data"]["database"]["host"] == "127.0.0.1"
    assert result["data"]["database"]["database"]
    assert result["data"]["database"]["source"] == "backend-local"


def test_resolve_database_config_supports_partial_override(workspace_builder) -> None:
    workspace_root = workspace_builder()
    config_path = workspace_root / ".yudao-pilot" / "config.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_config["database"]["database"] = "ruoyi-vue-pro-260319"
    config_path.write_text(
        yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = resolve_database_config_tool(str(workspace_root))

    assert result["ok"] is True
    assert result["data"]["database"]["host"] == "127.0.0.1"
    assert result["data"]["database"]["database"] == "ruoyi-vue-pro-260319"
    assert result["data"]["database"]["source"] == "config"


def test_inspect_codegen_context_tool_stops_when_database_connection_fails(
    workspace_builder,
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_root = workspace_builder()
    backend_root = _create_fake_backend(tmp_path)
    _rewrite_backend_path(workspace_root, backend_root)

    monkeypatch.setattr(schema_module, "resolve_mysql_schema_dump", lambda repo_root: None)

    def fail_connect(database_config, table_name):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(schema_module, "parse_table_schema_from_database", fail_connect)

    result = inspect_codegen_context_tool("missing_table", str(workspace_root))

    assert result["ok"] is False
    assert result["error_code"] == "database_connection_required"
    assert "真实数据库" in result["message"]
    assert "目标表结构" in result["message"]


def test_generate_codegen_scaffold_tool_stops_when_table_and_migration_are_missing(
    workspace_builder,
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_root = workspace_builder()
    backend_root = _create_fake_backend(tmp_path)
    _rewrite_backend_path(workspace_root, backend_root)

    monkeypatch.setattr(schema_module, "resolve_mysql_schema_dump", lambda repo_root: None)
    monkeypatch.setattr(schema_module, "parse_table_schema_from_database", lambda *args, **kwargs: None)

    result = generate_codegen_scaffold_tool("missing_table", str(workspace_root))

    assert result["ok"] is False
    assert result["error_code"] == "database_table_missing"
    assert "真实数据库" in result["message"]
    assert "目标表" in result["message"]


def test_inspect_table_schema_tool_requires_database_even_when_migration_sql_exists(
    workspace_builder,
    tmp_path: Path,
    monkeypatch,
) -> None:
    migration_filename = "2026_04_07_120000_create_missing_table.sql"
    workspace_root = workspace_builder()
    backend_root = _create_fake_backend(
        tmp_path,
        migration_files={
            migration_filename: dedent(
                """\
                -- create missing table
                CREATE TABLE `unrelated_table` (
                  `id` bigint NOT NULL,
                  PRIMARY KEY (`id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='不相关表';

                CREATE TABLE `missing_table` (
                  `id` bigint NOT NULL,
                  PRIMARY KEY (`id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='缺失表';
                """
            ),
        },
    )
    _rewrite_backend_path(workspace_root, backend_root)

    monkeypatch.setattr(schema_module, "resolve_mysql_schema_dump", lambda repo_root: None)

    parse_calls: list[str] = []

    def fake_parse_from_database(database_config, table_name):
        parse_calls.append(table_name)
        return None

    def fail_apply(*args, **kwargs):
        raise AssertionError("inspect_table_schema must not execute local migration SQL")

    monkeypatch.setattr(schema_module, "parse_table_schema_from_database", fake_parse_from_database)
    monkeypatch.setattr(schema_module, "apply_migration_sqls_to_database", fail_apply)

    result = inspect_table_schema_tool("missing_table", str(workspace_root))

    assert result["ok"] is False
    assert result["error_code"] == "database_table_missing"
    assert parse_calls == ["missing_table"]
    assert "真实数据库" in result["message"]
    assert "目标表" in result["message"]


def test_codegen_stops_when_database_does_not_contain_table(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder()

    monkeypatch.setattr(schema_module, "parse_table_schema_from_database", lambda *args, **kwargs: None)

    result = generate_codegen_scaffold_tool("merchant", str(workspace_root))

    assert result["ok"] is False
    assert result["error_code"] == "database_table_missing"
    assert "真实数据库" in result["message"]
    assert "目标表" in result["message"]


def test_vben_child_app_frontend_path_generates_app_local_paths(tmp_path: Path) -> None:
    web_ele = tmp_path / "frontend" / "apps" / "web-ele"
    web_ele.mkdir(parents=True)
    config = WorkspaceConfig.model_validate(
        {
            "projects": {
                "backend": {
                    "path": str(tmp_path / "backend"),
                    "type": "ruoyi-vue-pro-jdk17",
                },
                "frontend": [
                    {"type": "VUE3_VBEN5_EP_SCHEMA", "path": str(web_ele)},
                ],
            },
            "codegen": {
                "routing": {"mode": "manual"},
                "manual_rules": [
                    {
                        "module": "member",
                        "table_prefixes": ["merchant"],
                        "table_rules": [],
                    }
                ],
            },
        }
    )

    frontend_targets = resolve_frontend_codegen_targets(tmp_path, config)
    plan = build_generated_file_plan(
        table_name="merchant",
        module_name="member",
        business_name="merchant",
        entity_name="Merchant",
        base_package="cn.iocoder.yudao",
        frontend_targets=frontend_targets,
        unit_test_enable=False,
    )

    paths = plan["frontends"][0]["relative_paths"]
    assert "src/views/member/merchant/data.ts" in paths
    assert not any(path.startswith("apps/web-ele/") for path in paths)


def test_frontend_business_path_uses_lower_camel_segments() -> None:
    assert build_frontend_business_path(
        business_name="sim_spu",
        table_name="travel_sim_spu",
    ) == "simSpu"
    assert build_frontend_business_path(
        business_name="merchant",
        table_name="merchant_user",
    ) == "merchant/user"


def test_generated_frontend_paths_use_lower_camel_business_name() -> None:
    plan = build_generated_file_plan(
        table_name="travel_sim_spu",
        module_name="travel",
        business_name="sim_spu",
        entity_name="TravelSimSpu",
        base_package="cn.iocoder.yudao",
        frontend_targets=[
            {
                "project_type": "VUE3_ELEMENT_PLUS",
                "default_front_type": 20,
                "default_front_type_label": "Vue3 Element Plus",
                "ambiguous": False,
            }
        ],
        unit_test_enable=False,
    )

    assert plan["frontend_business_path"] == "simSpu"
    assert "src/views/travel/simSpu/index.vue" in plan["frontends"][0]["relative_paths"]
    assert "src/views/travel/simSpu/simSpuForm.vue" in plan["frontends"][0]["relative_paths"]
    assert "src/api/travel/simSpu/index.ts" in plan["frontends"][0]["relative_paths"]
    assert not any("sim_spu" in path for path in plan["frontends"][0]["relative_paths"])


def test_vue3_index_imports_lower_camel_form_file() -> None:
    plan = build_generated_file_plan(
        table_name="travel_sim_spu",
        module_name="travel",
        business_name="sim_spu",
        entity_name="TravelSimSpu",
        base_package="cn.iocoder.yudao",
        frontend_targets=[
            {
                "project_type": "VUE3_ELEMENT_PLUS",
                "default_front_type": 20,
                "default_front_type_label": "Vue3 Element Plus",
                "ambiguous": False,
            }
        ],
        unit_test_enable=False,
    )
    context = {
        "table_name": "travel_sim_spu",
        "module_name": "travel",
        "business_name": "sim_spu",
        "entity_name": "TravelSimSpu",
        "menu_name": "仿真商品",
        "permission_prefix": "travel:sim-spu",
        "backend_project": {"type": "ruoyi-vue-pro-jdk17"},
        "backend_codegen_defaults": {"base_package": "cn.iocoder.yudao"},
        "table_schema": {"columns": []},
        "generated_file_plan": plan,
    }

    content = render_frontend_file(
        "src/views/travel/simSpu/index.vue",
        plan["frontends"][0],
        context,
    )

    assert "import SimSpuForm from './simSpuForm.vue'" in content
    assert "<SimSpuForm ref=\"formRef\" @success=\"getList\" />" in content
    assert "TravelSimSpuForm.vue" not in content


def test_vue3_generated_dict_uses_dict_type_constant() -> None:
    field = {
        "java_field": "sourceType",
        "column_comment": "来源类型",
        "java_type": "Integer",
        "ts_type": "number",
        "html_type": "select",
        "generated_dict_type": "sim_spu_source_type",
    }

    assert "DICT_TYPE.SIM_SPU_SOURCE_TYPE" in render_vue3_dict_options_expr(field)
    assert render_vue3_dict_type_expr(field) == "DICT_TYPE.SIM_SPU_SOURCE_TYPE"
    assert "'sim_spu_source_type'" not in render_vue3_dict_options_expr(field)


def test_vue3_dict_import_line_only_imports_used_helpers() -> None:
    option_fields = [
        {
            "java_field": "status",
            "column_comment": "状态",
            "java_type": "Integer",
            "ts_type": "number",
            "html_type": "select",
            "generated_dict_type": "travel_sim_status",
        },
        {
            "java_field": "specType",
            "column_comment": "规格类型",
            "java_type": "Boolean",
            "ts_type": "boolean",
            "html_type": "select",
            "generated_dict_type": "travel_sim_spec_type",
        },
    ]
    type_fields = option_fields + [
        {
            "java_field": "cardType",
            "column_comment": "卡类型",
            "java_type": "Integer",
            "ts_type": "number",
            "html_type": "input",
            "generated_dict_type": "travel_sim_card_type",
        }
    ]

    line = build_vue3_dict_import_line(option_fields, type_fields)

    assert line == "import { getIntDictOptions, getBoolDictOptions, DICT_TYPE } from '@/utils/dict'"
    assert "getStrDictOptions" not in line


def test_vue3_empty_select_control_is_self_closing() -> None:
    field = {
        "java_field": "cancelType",
        "column_comment": "取消类型",
        "java_type": "Integer",
        "ts_type": "number",
        "html_type": "select",
        "nullable": True,
    }

    content = render_vue3_form_item(field)

    assert '<el-select v-model="formData.cancelType" placeholder="请选择取消类型" clearable class="!w-240px" />' in content
    assert "</el-select>" not in content


def test_vue3_empty_radio_group_is_self_closing() -> None:
    field = {
        "java_field": "beforeStatus",
        "column_comment": "操作前状态",
        "java_type": "Integer",
        "ts_type": "number",
        "html_type": "radio",
        "nullable": True,
    }

    content = render_vue3_form_item(field)

    assert '<el-radio-group v-model="formData.beforeStatus" />' in content
    assert "</el-radio-group>" not in content


def test_vue3_query_select_without_dict_keeps_all_option() -> None:
    field = {
        "java_field": "networkType",
        "column_comment": "网络类型",
        "java_type": "String",
        "ts_type": "string",
        "html_type": "select",
        "nullable": True,
        "in_query": True,
    }

    content = render_vue3_query_item(field)

    assert '<el-option label="全部" value="" />' in content
    assert "</el-select>" in content


def test_scaffold_includes_vue3_dict_type_constant_update_file() -> None:
    plan = build_generated_file_plan(
        table_name="travel_sim_spu",
        module_name="travel",
        business_name="sim_spu",
        entity_name="TravelSimSpu",
        base_package="cn.iocoder.yudao",
        frontend_targets=[
            {
                "project_type": "VUE3_ELEMENT_PLUS",
                "default_front_type": 20,
                "default_front_type_label": "Vue3 Element Plus",
                "ambiguous": False,
            }
        ],
        unit_test_enable=False,
    )
    context = {
        "table_name": "travel_sim_spu",
        "module_name": "travel",
        "business_name": "sim_spu",
        "entity_name": "TravelSimSpu",
        "menu_name": "仿真商品",
        "permission_prefix": "travel:sim-spu",
        "backend_project": {"type": "ruoyi-vue-pro-jdk17"},
        "backend_codegen_defaults": {"base_package": "cn.iocoder.yudao"},
        "table_schema": {
            "columns": [
                {
                    "java_field": "sourceType",
                    "column_comment": "来源类型",
                    "java_type": "Integer",
                    "ts_type": "number",
                    "html_type": "select",
                    "generated_dict_type": "sim_spu_source_type",
                    "generated_dict_name": "来源类型",
                }
            ]
        },
        "generated_file_plan": plan,
    }

    files = generate_scaffold_files(context, include_backend=False)
    dict_file = next(file for file in files if file.relative_path == "src/utils/dict.ts")

    assert "SIM_SPU_SOURCE_TYPE = 'sim_spu_source_type'" in dict_file.content
    assert "来源类型" in dict_file.content


def test_build_dict_plan_reuses_common_status_from_existing_catalog() -> None:
    context = {
        "table_name": "hotel_brand",
        "table_schema": {
            "table_comment": "酒店品牌",
            "columns": [
                {
                    "column_name": "status",
                    "column_comment": "状态: 0-开启, 1-禁用",
                    "java_field": "status",
                    "ts_type": "number",
                    "primary_key": False,
                    "is_base_column": False,
                }
            ],
        },
    }

    result = build_dict_plan(
        context,
        database_dict_catalog={
            "dict_types": {
                "common_status": {
                    "id": 1,
                    "name": "通用状态",
                    "type": "common_status",
                }
            },
            "dict_data": {
                "common_status": [
                    {"id": 11, "sort": 0, "label": "开启", "value": "0", "dict_type": "common_status"},
                    {"id": 12, "sort": 1, "label": "禁用", "value": "1", "dict_type": "common_status"},
                ]
            },
        },
    )

    assert result["catalog_source"] == "database"
    assert result["dict_types"][0]["dict_type"] == "common_status"
    assert result["dict_types"][0]["reuse_existing"] is True
    assert result["dict_types"][0]["all_complete"] is True
    assert result["dict_types"][0]["reuse_match"]["match_kind"] == "known_public_dict"


def test_build_dict_plan_exposes_ai_candidate_matches() -> None:
    context = {
        "table_name": "travel_sim_sku",
        "table_schema": {
            "table_comment": "旅游手机卡 SKU",
            "columns": [
                {
                    "column_name": "card_type",
                    "column_comment": "卡类型: 1-实物SIM卡, 2-eSIM流量包",
                    "java_field": "cardType",
                    "ts_type": "number",
                    "primary_key": False,
                    "is_base_column": False,
                }
            ],
        },
    }

    result = build_dict_plan(
        context,
        database_dict_catalog={
            "dict_types": {
                "travel_card_type": {
                    "id": 2,
                    "name": "卡类型",
                    "type": "travel_card_type",
                }
            },
            "dict_data": {
                "travel_card_type": [
                    {"id": 21, "sort": 0, "label": "实物SIM卡", "value": "1", "dict_type": "travel_card_type"},
                    {"id": 22, "sort": 1, "label": "eSIM流量包", "value": "2", "dict_type": "travel_card_type"},
                ]
            },
        },
    )

    assert result["ai_assist"]["available"] is True
    assert result["dict_types"][0]["candidate_matches"]
    assert result["dict_types"][0]["candidate_matches"][0]["dict_type"] == "travel_card_type"
    assert result["dict_types"][0]["reuse_existing"] is True


def test_scaffold_marks_new_code_files_as_non_overwrite_by_default() -> None:
    plan = build_generated_file_plan(
        table_name="travel_sim_spu",
        module_name="travel",
        business_name="sim_spu",
        entity_name="TravelSimSpu",
        base_package="cn.iocoder.yudao",
        frontend_targets=[
            {
                "project_type": "VUE3_ELEMENT_PLUS",
                "default_front_type": 20,
                "default_front_type_label": "Vue3 Element Plus",
                "ambiguous": False,
            }
        ],
        unit_test_enable=False,
    )
    context = {
        "table_name": "travel_sim_spu",
        "module_name": "travel",
        "business_name": "sim_spu",
        "entity_name": "TravelSimSpu",
        "menu_name": "仿真商品",
        "permission_prefix": "travel:sim-spu",
        "backend_project": {
            "type": "ruoyi-vue-pro-jdk17",
            "codegen_target": plan["backend_target"],
        },
        "backend_codegen_defaults": {"base_package": "cn.iocoder.yudao"},
        "table_schema": {"columns": []},
        "generated_file_plan": plan,
    }

    files = generate_scaffold_files(context)
    ordinary_files = [file for file in files if file.relative_path != "src/utils/dict.ts"]

    assert ordinary_files
    assert all(file.overwrite is False for file in ordinary_files)


def test_backend_business_name_removes_underscores() -> None:
    assert normalize_backend_business_name("sim_spu") == "simspu"
    assert normalize_backend_business_name("hotel/room_type") == "hotel/roomtype"


def test_backend_business_name_strips_module_prefix_by_default() -> None:
    assert resolve_backend_business_name(
        module_name="sim",
        business_name="simspu",
        table_name="sim_spu",
    ) == "spu"
    assert resolve_backend_business_name(
        module_name="sim",
        business_name="sim_spu",
        table_name="sim_spu",
        preserve_business_name=True,
    ) == "spu"


def test_generated_backend_paths_use_compact_business_name() -> None:
    plan = build_generated_file_plan(
        table_name="travel_sim_spu",
        module_name="travel",
        business_name="sim_spu",
        entity_name="TravelSimSpu",
        base_package="cn.iocoder.yudao",
        frontend_targets=[],
        unit_test_enable=False,
    )

    assert plan["backend_business_name"] == "simspu"
    assert any("/controller/admin/simspu/" in path for path in plan["backend"])
    assert any("/dal/dataobject/simspu/" in path for path in plan["backend"])
    assert not any("/sim_spu/" in path for path in plan["backend"])


def test_generated_backend_paths_strip_module_prefix_from_business_name() -> None:
    plan = build_generated_file_plan(
        table_name="sim_spu",
        module_name="sim",
        business_name="simspu",
        entity_name="SimSpu",
        base_package="cn.iocoder.yudao",
        frontend_targets=[],
        unit_test_enable=False,
    )

    assert plan["backend_business_name"] == "spu"
    assert any("/controller/admin/spu/" in path for path in plan["backend"])
    assert not any("/controller/admin/simspu/" in path for path in plan["backend"])


def test_generated_backend_paths_strip_package_module_prefix_from_preserved_business_name() -> None:
    plan = build_generated_file_plan(
        table_name="travel_sim_sku",
        module_name="sim",
        business_name="sim_sku",
        entity_name="TravelSimSku",
        base_package="cn.iocoder.yudao",
        frontend_targets=[],
        unit_test_enable=False,
        preserve_business_name=True,
    )

    assert plan["backend_business_name"] == "sku"
    assert any("/controller/admin/sku/" in path for path in plan["backend"])
    assert any("/dal/dataobject/sku/" in path for path in plan["backend"])
    assert not any("/controller/admin/simsku/" in path for path in plan["backend"])


def test_rendered_backend_and_frontend_use_split_business_names() -> None:
    plan = build_generated_file_plan(
        table_name="travel_sim_spu",
        module_name="travel",
        business_name="sim_spu",
        entity_name="TravelSimSpu",
        base_package="cn.iocoder.yudao",
        frontend_targets=[
            {
                "project_type": "VUE3_ELEMENT_PLUS",
                "default_front_type": 20,
                "default_front_type_label": "Vue3 Element Plus",
                "ambiguous": False,
            }
        ],
        unit_test_enable=False,
    )
    context = {
        "table_name": "travel_sim_spu",
        "module_name": "travel",
        "business_name": "sim_spu",
        "entity_name": "TravelSimSpu",
        "menu_name": "商品",
        "permission_prefix": "travel:sim-spu",
        "backend_project": {"type": "ruoyi-vue-pro-jdk17"},
        "backend_codegen_defaults": {"base_package": "cn.iocoder.yudao"},
        "table_schema": {"columns": []},
        "generated_file_plan": plan,
    }

    controller_path = next(path for path in plan["backend"] if path.endswith("Controller.java"))
    controller_java = render_backend_file(controller_path, context)
    frontend_plan = plan["frontends"][0]
    frontend_api = render_frontend_file(
        "src/api/travel/simSpu/index.ts",
        frontend_plan,
        context,
    )

    assert ".controller.admin.simspu." in controller_java
    assert '@RequestMapping("/travel/simspu")' in controller_java
    assert "/admin-api/travel/simspu/page" in frontend_api
    assert "@/api/travel/simSpu" not in frontend_api


def test_generate_codegen_scaffold_adds_table_id_to_primary_key_do_field(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder(
        frontend_types=("VUE3_ELEMENT_PLUS",),
        manual_rules_yaml="""
- module: travel
  table_prefixes:
    - travel_sim
  table_rules:
    - table: travel_sim_sku
      business: sim_sku
      entity: TravelSimSku
""".strip(),
    )
    fake_schema = {
        "resolved": True,
        "table_name": "travel_sim_sku",
        "table_comment": "旅游手机卡 SKU",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
            {
                "column_name": "sku_name",
                "column_comment": "SKU 名称",
                "sql_type": "varchar",
                "raw_type": "varchar(64)",
                "java_field": "skuName",
                "java_type": "String",
                "ts_type": "string",
                "html_type": "input",
                "nullable": False,
                "primary_key": False,
                "auto_increment": False,
                "is_base_column": False,
                "in_do": True,
                "in_save": True,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_scaffold_tool("travel_sim_sku", str(workspace_root))

    assert result["ok"] is True
    data_object = next(
        item
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("dal/dataobject/simsku/TravelSimSkuDO.java")
    )

    assert "import com.baomidou.mybatisplus.annotation.TableId;" in data_object["content"]
    assert (
        '    @Schema(description = "编号")\n'
        "    @TableId\n"
        "    private Long id;"
    ) in data_object["content"]
    assert "@TableId\n    private String skuName;" not in data_object["content"]

    for item in result["data"]["generated_files"]:
        if item["relative_path"].endswith(("PageReqVO.java", "RespVO.java", "SaveReqVO.java")):
            assert "@TableId" not in item["content"]


def test_generate_codegen_scaffold_adds_controller_permissions_and_swagger_annotations(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder(
        frontend_types=("VUE3_ELEMENT_PLUS",),
        manual_rules_yaml="""
- module: system
  table_prefixes:
    - system
  table_rules:
    - table: system_tourism_location
      business: tourism_location
      entity: SystemTourismLocation
""".strip(),
    )
    fake_schema = {
        "resolved": True,
        "table_name": "system_tourism_location",
        "table_comment": "景点位置",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            }
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_scaffold_tool("system_tourism_location", str(workspace_root))

    assert result["ok"] is True
    controller_java = next(
        item
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith(
            "controller/admin/tourismlocation/SystemTourismLocationController.java"
        )
    )

    assert '@Tag(name = "管理后台 - 景点位置")' in controller_java["content"]
    assert "@Operation(summary = \"新增景点位置\")" in controller_java["content"]
    assert "@Operation(summary = \"修改景点位置\")" in controller_java["content"]
    assert "@Operation(summary = \"删除景点位置\")" in controller_java["content"]
    assert "@Operation(summary = \"获得景点位置详情\")" in controller_java["content"]
    assert "@Operation(summary = \"获得景点位置分页\")" in controller_java["content"]
    assert '@Parameter(name = "id", description = "编号", required = true, example = "1024")' in controller_java["content"]
    assert "@PreAuthorize(\"@ss.hasPermission('system:tourism-location:create')\")" in controller_java["content"]
    assert "@PreAuthorize(\"@ss.hasPermission('system:tourism-location:update')\")" in controller_java["content"]
    assert "@PreAuthorize(\"@ss.hasPermission('system:tourism-location:delete')\")" in controller_java["content"]
    assert controller_java["content"].count(
        "@PreAuthorize(\"@ss.hasPermission('system:tourism-location:query')\")"
    ) == 2


def test_generate_codegen_scaffold_normalizes_vue3_api_file_indentation(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder(
        frontend_types=("VUE3_ELEMENT_PLUS",),
        manual_rules_yaml="""
- module: system
  table_prefixes:
    - system
  table_rules:
    - table: system_tourism_location
      business: tourism_location
      entity: SystemTourismLocation
""".strip(),
    )
    fake_schema = {
        "resolved": True,
        "table_name": "system_tourism_location",
        "table_comment": "景点位置",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            }
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_scaffold_tool("system_tourism_location", str(workspace_root))

    assert result["ok"] is True
    vue3_api = next(
        item
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("src/api/system/tourismLocation/index.ts")
        and item["target_type"] == "VUE3_ELEMENT_PLUS"
    )

    first_line = vue3_api["content"].splitlines()[0]
    assert first_line == "import request from '@/config/axios'"
    assert not first_line.startswith(" ")
    assert "\n        export const" not in vue3_api["content"]


def test_generate_codegen_scaffold_vue3_renders_common_field_types_with_upstream_controls(
    workspace_builder,
    monkeypatch,
) -> None:
    workspace_root = workspace_builder(
        frontend_types=("VUE3_ELEMENT_PLUS",),
        manual_rules_yaml="""
- module: hotel
  table_prefixes:
    - hotel
  table_rules:
    - table: hotel_brand
      business: brand
      entity: HotelBrand
""".strip(),
    )
    fake_schema = {
        "resolved": True,
        "table_name": "hotel_brand",
        "table_comment": "酒店品牌",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
            {
                "column_name": "status",
                "column_comment": "状态: 0-启用, 1-禁用",
                "sql_type": "tinyint",
                "raw_type": "tinyint",
                "java_field": "status",
                "java_type": "Integer",
                "ts_type": "number",
                "html_type": "radio",
                "nullable": False,
                "primary_key": False,
                "auto_increment": False,
                "is_base_column": False,
                "in_do": True,
                "in_save": True,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
            {
                "column_name": "sort",
                "column_comment": "排序",
                "sql_type": "int",
                "raw_type": "int",
                "java_field": "sort",
                "java_type": "Integer",
                "ts_type": "number",
                "html_type": "inputNumber",
                "nullable": False,
                "primary_key": False,
                "auto_increment": False,
                "is_base_column": False,
                "in_do": True,
                "in_save": True,
                "in_resp": True,
                "in_list": True,
                "in_query": False,
            },
            {
                "column_name": "cover_url",
                "column_comment": "封面图",
                "sql_type": "varchar",
                "raw_type": "varchar(255)",
                "java_field": "coverUrl",
                "java_type": "String",
                "ts_type": "string",
                "html_type": "imageUpload",
                "nullable": True,
                "primary_key": False,
                "auto_increment": False,
                "is_base_column": False,
                "in_do": True,
                "in_save": True,
                "in_resp": True,
                "in_list": True,
                "in_query": False,
            },
            {
                "column_name": "content",
                "column_comment": "介绍",
                "sql_type": "text",
                "raw_type": "text",
                "java_field": "content",
                "java_type": "String",
                "ts_type": "string",
                "html_type": "editor",
                "nullable": True,
                "primary_key": False,
                "auto_increment": False,
                "is_base_column": False,
                "in_do": True,
                "in_save": True,
                "in_resp": True,
                "in_list": False,
                "in_query": False,
            },
            {
                "column_name": "create_time",
                "column_comment": "创建时间",
                "sql_type": "datetime",
                "raw_type": "datetime",
                "java_field": "createTime",
                "java_type": "LocalDateTime",
                "ts_type": "string",
                "html_type": "datetime",
                "nullable": True,
                "primary_key": False,
                "auto_increment": False,
                "is_base_column": True,
                "in_do": False,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_scaffold_tool("hotel_brand", str(workspace_root))

    assert result["ok"] is True
    index_vue = next(
        item["content"]
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("src/views/hotel/brand/index.vue")
    )
    form_vue = next(
        item["content"]
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("src/views/hotel/brand/brandForm.vue")
    )

    assert "from '@/utils/dict'" in index_vue
    assert "getIntDictOptions" in index_vue
    assert "DICT_TYPE" in index_vue
    assert "v-for=\"dict in getIntDictOptions(DICT_TYPE.COMMON_STATUS)\"" in index_vue
    assert "<dict-tag :type=\"DICT_TYPE.COMMON_STATUS\" :value=\"scope.row.status\" />" in index_vue
    assert ":formatter=\"dateFormatter\"" in index_vue
    assert "<el-radio-group v-model=\"formData.status\">" in form_vue
    assert "v-for=\"dict in getIntDictOptions(DICT_TYPE.COMMON_STATUS)\"" in form_vue
    assert "<el-input-number" in form_vue
    assert "<UploadImg v-model=\"formData.coverUrl\" />" in form_vue
    assert "<Editor v-model=\"formData.content\" height=\"150px\" />" in form_vue


def test_generate_vben_schema_refines_field_rendering_rules(
    workspace_builder, monkeypatch
) -> None:
    def fake_parse_table_schema_from_database(database_config, table_name):
        assert table_name == "merchant_user"
        return {
            "resolved": True,
            "table_name": table_name,
            "table_comment": "商家用户",
            "schema_source": "database",
            "database_name": database_config.database,
            "message": "已从真实数据库解析表字段",
            "columns": [
                {
                    "column_name": "id",
                    "column_comment": "编号",
                    "sql_type": "bigint",
                    "raw_type": "bigint",
                    "java_field": "id",
                    "java_type": "Long",
                    "ts_type": "number",
                    "html_type": "input",
                    "nullable": False,
                    "primary_key": True,
                    "auto_increment": True,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": False,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": True,
                },
                {
                    "column_name": "merchant_id",
                    "column_comment": "关联商家ID",
                    "sql_type": "bigint",
                    "raw_type": "bigint",
                    "java_field": "merchantId",
                    "java_type": "Long",
                    "ts_type": "number",
                    "html_type": "input",
                    "nullable": False,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": True,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": True,
                },
                {
                    "column_name": "account_id",
                    "column_comment": "关联账号ID(merchant_account.id)",
                    "sql_type": "bigint",
                    "raw_type": "bigint",
                    "java_field": "accountId",
                    "java_type": "Long",
                    "ts_type": "number",
                    "html_type": "input",
                    "nullable": False,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": True,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": True,
                },
                {
                    "column_name": "role_type",
                    "column_comment": "角色: 1-管理员, 2-员工",
                    "sql_type": "tinyint",
                    "raw_type": "tinyint",
                    "java_field": "roleType",
                    "java_type": "Integer",
                    "ts_type": "number",
                    "html_type": "select",
                    "nullable": False,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": True,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": False,
                },
                {
                    "column_name": "status",
                    "column_comment": "状态: 0-启用, 1-禁用",
                    "sql_type": "tinyint",
                    "raw_type": "tinyint",
                    "java_field": "status",
                    "java_type": "Integer",
                    "ts_type": "number",
                    "html_type": "radio",
                    "nullable": False,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": True,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": True,
                },
                {
                    "column_name": "delete_token",
                    "column_comment": "逻辑唯一令牌(默认0,删除时改为雪花ID)",
                    "sql_type": "bigint",
                    "raw_type": "bigint",
                    "java_field": "deleteToken",
                    "java_type": "Long",
                    "ts_type": "number",
                    "html_type": "input",
                    "nullable": False,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": True,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": False,
                },
                {
                    "column_name": "create_time",
                    "column_comment": "创建时间",
                    "sql_type": "datetime",
                    "raw_type": "datetime",
                    "java_field": "createTime",
                    "java_type": "LocalDateTime",
                    "ts_type": "string",
                    "html_type": "datetime",
                    "nullable": True,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": True,
                    "in_do": False,
                    "in_save": False,
                    "in_resp": True,
                    "in_list": False,
                    "in_query": True,
                },
            ],
        }

    monkeypatch.setattr(schema_module, "parse_table_schema_from_database", fake_parse_table_schema_from_database)
    workspace_root = workspace_builder(
        frontend_types=("VUE3_VBEN5_ANTD_SCHEMA", "VUE3_VBEN5_EP_SCHEMA")
    )
    result = generate_codegen_scaffold_tool(
        "merchant_user",
        str(workspace_root),
        include_backend=False,
        include_frontend=True,
    )

    assert result["ok"] is True
    generated_files = result["data"]["generated_files"]
    antd_data = next(
        item["content"]
        for item in generated_files
        if item["target_type"] == "VUE3_VBEN5_ANTD_SCHEMA"
        and item["relative_path"].endswith("/data.ts")
    )
    ep_data = next(
        item["content"]
        for item in generated_files
        if item["target_type"] == "VUE3_VBEN5_EP_SCHEMA"
        and item["relative_path"].endswith("/data.ts")
    )

    assert "DICT_TYPE.COMMON_STATUS" in antd_data
    assert "getRangePickerDefaultProps" in antd_data
    assert "deleteToken" not in antd_data
    assert "merchant_user_role_type" in antd_data
    assert "getDictOptions('merchant_user_role_type', 'number')" in antd_data
    assert "allowClear: true" in antd_data
    assert "clearable: true" in ep_data


def test_generate_vben_schema_uses_image_upload_for_logo_fields(
    workspace_builder, monkeypatch
) -> None:
    def fake_parse_table_schema_from_database(database_config, table_name):
        assert table_name == "merchant"
        return {
            "resolved": True,
            "table_name": table_name,
            "table_comment": "商家",
            "schema_source": "database",
            "database_name": database_config.database,
            "message": "已从真实数据库解析表字段",
            "columns": [
                {
                    "column_name": "id",
                    "column_comment": "商家编号",
                    "sql_type": "bigint",
                    "raw_type": "bigint",
                    "java_field": "id",
                    "java_type": "Long",
                    "ts_type": "number",
                    "html_type": "input",
                    "nullable": False,
                    "primary_key": True,
                    "auto_increment": True,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": False,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": True,
                },
                {
                    "column_name": "name",
                    "column_comment": "商家名称",
                    "sql_type": "varchar",
                    "raw_type": "varchar(64)",
                    "java_field": "name",
                    "java_type": "String",
                    "ts_type": "string",
                    "html_type": "input",
                    "nullable": False,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": True,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": True,
                },
                {
                    "column_name": "logo_url",
                    "column_comment": "商家Logo",
                    "sql_type": "varchar",
                    "raw_type": "varchar(255)",
                    "java_field": "logoUrl",
                    "java_type": "String",
                    "ts_type": "string",
                    "html_type": "imageUpload",
                    "nullable": True,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": True,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": False,
                },
                {
                    "column_name": "status",
                    "column_comment": "状态: 0-启用, 1-禁用",
                    "sql_type": "tinyint",
                    "raw_type": "tinyint",
                    "java_field": "status",
                    "java_type": "Integer",
                    "ts_type": "number",
                    "html_type": "radio",
                    "nullable": False,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": True,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": True,
                },
                {
                    "column_name": "delete_token",
                    "column_comment": "逻辑唯一令牌(默认0,删除时改为雪花ID)",
                    "sql_type": "bigint",
                    "raw_type": "bigint",
                    "java_field": "deleteToken",
                    "java_type": "Long",
                    "ts_type": "number",
                    "html_type": "input",
                    "nullable": False,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": True,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": False,
                },
            ],
        }

    monkeypatch.setattr(schema_module, "parse_table_schema_from_database", fake_parse_table_schema_from_database)
    workspace_root = workspace_builder(frontend_types=("VUE3_VBEN5_ANTD_SCHEMA",))
    result = generate_codegen_scaffold_tool(
        "merchant",
        str(workspace_root),
        include_backend=False,
        include_frontend=True,
    )

    assert result["ok"] is True
    data_ts = next(
        item["content"]
        for item in result["data"]["generated_files"]
        if item["target_type"] == "VUE3_VBEN5_ANTD_SCHEMA"
        and item["relative_path"].endswith("/data.ts")
    )

    assert "component: 'ImageUpload'" in data_ts
    assert "deleteToken" not in data_ts
    assert "options: getDictOptions(DICT_TYPE.COMMON_STATUS, 'number')" in data_ts


def test_generate_codegen_scaffold_falls_back_to_database_schema(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder()

    def fake_parse_table_schema_from_database(database_config, table_name):
        assert database_config.host == "127.0.0.1"
        assert table_name == "merchant"
        return {
            "resolved": True,
            "table_name": table_name,
            "table_comment": "商户",
            "schema_source": "database",
            "database_name": database_config.database,
            "message": "已从真实数据库解析表字段",
            "columns": [
                {
                    "column_name": "id",
                    "column_comment": "编号",
                    "sql_type": "bigint",
                    "raw_type": "bigint",
                    "java_field": "id",
                    "java_type": "Long",
                    "ts_type": "number",
                    "html_type": "input",
                    "nullable": False,
                    "primary_key": True,
                    "auto_increment": True,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": False,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": True,
                },
                {
                    "column_name": "name",
                    "column_comment": "商户名称",
                    "sql_type": "varchar",
                    "raw_type": "varchar(64)",
                    "java_field": "name",
                    "java_type": "String",
                    "ts_type": "string",
                    "html_type": "input",
                    "nullable": False,
                    "primary_key": False,
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": True,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": True,
                },
            ],
        }

    monkeypatch.setattr(schema_module, "parse_table_schema_from_database", fake_parse_table_schema_from_database)
    result = generate_codegen_scaffold_tool("merchant", str(workspace_root))

    assert result["ok"] is True
    assert result["data"]["context"]["table_schema"]["schema_source"] == "database"
    generated_files = result["data"]["generated_files"]
    save_req = next(
        item for item in generated_files if item["relative_path"].endswith("MerchantSaveReqVO.java")
    )
    assert "private String name;" in save_req["content"]


def test_generate_codegen_sql_tool_contains_mysql_and_h2_plan(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder()
    fake_schema = {
        "resolved": True,
        "table_name": "member_user",
        "table_comment": "会员用户",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
            {
                "column_name": "nickname",
                "column_comment": "昵称",
                "sql_type": "varchar",
                "raw_type": "varchar(30)",
                "java_field": "nickname",
                "java_type": "String",
                "ts_type": "string",
                "html_type": "input",
                "nullable": False,
                "primary_key": False,
                "auto_increment": False,
                "is_base_column": False,
                "in_do": True,
                "in_save": True,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_sql_tool(
        "member_user",
        str(workspace_root),
        module_menu_name="会员中心",
        menu_name="会员用户",
    )

    assert result["ok"] is True
    sql_bundle = result["data"]["sql_bundle"]
    assert sql_bundle["mysql"]["supported_db"] == "mysql"
    assert "INSERT INTO system_menu" in sql_bundle["mysql"]["content"]
    assert "会员用户管理" in sql_bundle["mysql"]["content"]
    assert "'ep:avatar'" in sql_bundle["mysql"]["content"]
    assert sql_bundle["menu_plan"]["business_menu"]["icon"] == "ep:avatar"
    assert sql_bundle["h2"]["resolved"] is True
    assert sql_bundle["h2"]["create_tables_path"].endswith(
        "yudao-module-member/src/test/resources/sql/create_tables.sql"
    )
    assert 'CREATE TABLE IF NOT EXISTS "member_user"' in sql_bundle["h2"]["create_sql"]
    assert 'DELETE FROM "member_user";' in sql_bundle["h2"]["clean_sql"]


def test_generate_codegen_sql_tool_menu_sql_mode_disabled(workspace_builder, monkeypatch) -> None:
    workspace_root = workspace_builder()
    config_path = workspace_root / ".yudao-pilot" / "config.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_config["codegen"]["menu_sql_mode"] = "disabled"
    config_path.write_text(
        yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    fake_schema = {
        "resolved": True,
        "table_name": "member_user",
        "table_comment": "会员用户",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_sql_tool("member_user", str(workspace_root))

    assert result["ok"] is True
    sql_bundle = result["data"]["sql_bundle"]
    assert sql_bundle["menu_plan"]["disabled"] is True
    assert "INSERT INTO system_menu" not in sql_bundle["mysql"]["content"]
    assert sql_bundle["codegen_sql_modes"]["menu"] == "disabled"


def test_generate_codegen_sql_tool_defaults_to_skip_database_apply_by_config(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder()
    fake_schema = {
        "resolved": True,
        "table_name": "member_user",
        "table_comment": "会员用户",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    apply_calls: list[dict[str, object]] = []

    def fake_apply_menu(database_config, menu_plan):
        apply_calls.append({"database": database_config, "menu_plan": menu_plan})
        return {"ok": True, "created": [], "updated": [], "skipped": []}

    monkeypatch.setattr("yudao_pilot.server.apply_menu_plan_to_database", fake_apply_menu)

    result = generate_codegen_sql_tool("member_user", str(workspace_root))

    assert result["ok"] is True
    assert result["data"]["context"]["codegen_sql"]["apply_to_database"] is False
    assert result["data"]["apply_result"]["skipped_reason"] == "apply_disabled_by_config"
    assert len(apply_calls) == 0


def test_generate_codegen_sql_tool_skips_database_apply_in_migration_only_mode(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder()
    config_path = workspace_root / ".yudao-pilot" / "config.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_config["codegen"]["apply_to_database"] = True
    raw_config["codegen"]["menu_sql_mode"] = "migration_only"
    config_path.write_text(
        yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    fake_schema = {
        "resolved": True,
        "table_name": "member_user",
        "table_comment": "会员用户",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr(
        "yudao_pilot.server.resolve_database_config",
        lambda *args, **kwargs: {
            "ok": True,
            "database": {
                "host": "127.0.0.1",
                "port": 3306,
                "database": "demo",
                "username": "root",
                "password": "123456",
            },
            "message": "ok",
        },
    )

    apply_calls: list[dict[str, object]] = []

    def fake_apply_menu(database_config, menu_plan):
        apply_calls.append({"database": database_config, "menu_plan": menu_plan})
        return {"ok": True, "created": [], "updated": [], "skipped": []}

    monkeypatch.setattr("yudao_pilot.server.apply_menu_plan_to_database", fake_apply_menu)

    result = generate_codegen_sql_tool("member_user", str(workspace_root))

    assert result["ok"] is True
    assert result["data"]["context"]["codegen_sql"]["apply_to_database"] is True
    assert result["data"]["apply_result"]["skipped_reason"] == "no_database_apply_needed"
    assert len(apply_calls) == 0


def test_generate_codegen_sql_tool_applies_when_config_enabled_and_auto_mode(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder()
    config_path = workspace_root / ".yudao-pilot" / "config.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_config["codegen"]["apply_to_database"] = True
    raw_config["codegen"]["menu_sql_mode"] = "auto"
    config_path.write_text(
        yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    fake_schema = {
        "resolved": True,
        "table_name": "member_user",
        "table_comment": "会员用户",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr(
        "yudao_pilot.server.resolve_database_config",
        lambda *args, **kwargs: {
            "ok": True,
            "database": {
                "host": "127.0.0.1",
                "port": 3306,
                "database": "demo",
                "username": "root",
                "password": "123456",
            },
            "message": "ok",
        },
    )

    apply_calls: list[dict[str, object]] = []

    def fake_apply_menu(database_config, menu_plan):
        apply_calls.append({"database": database_config, "menu_plan": menu_plan})
        return {"ok": True, "created": [], "updated": [], "skipped": []}

    monkeypatch.setattr("yudao_pilot.server.apply_menu_plan_to_database", fake_apply_menu)

    result = generate_codegen_sql_tool("member_user", str(workspace_root))

    assert result["ok"] is True
    assert result["data"]["context"]["codegen_sql"]["apply_to_database"] is True
    assert len(apply_calls) == 1


def test_generate_codegen_scaffold_tool_writes_sql_assets_and_applies_by_config(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder()
    config_path = workspace_root / ".yudao-pilot" / "config.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_config["codegen"]["apply_to_database"] = True
    raw_config["codegen"]["menu_sql_mode"] = "auto"
    raw_config["codegen"]["dict_sql_mode"] = "auto"
    config_path.write_text(
        yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    fake_schema = {
        "resolved": True,
        "table_name": "member_user",
        "table_comment": "会员用户",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr(
        "yudao_pilot.server.resolve_database_config",
        lambda *args, **kwargs: {
            "ok": True,
            "database": {
                "host": "127.0.0.1",
                "port": 3306,
                "database": "demo",
                "username": "root",
                "password": "123456",
            },
            "message": "ok",
        },
    )

    apply_calls: list[dict[str, object]] = []

    def fake_apply_menu(database_config, menu_plan):
        apply_calls.append({"database": database_config, "menu_plan": menu_plan})
        return {"ok": True, "created": ["业务菜单:会员用户管理"], "updated": [], "skipped": []}

    monkeypatch.setattr("yudao_pilot.server.apply_menu_plan_to_database", fake_apply_menu)
    monkeypatch.setattr(
        "yudao_pilot.server.write_generated_files",
        lambda *args, **kwargs: {"ok": True, "results": []},
    )
    monkeypatch.setattr(
        "yudao_pilot.server.write_codegen_sql_bundle",
        lambda *args, **kwargs: {
            "ok": True,
            "results": [
                {"ok": True, "kind": "mysql_migration", "written": True},
                {"ok": True, "kind": "h2_create_tables", "written": True},
                {"ok": True, "kind": "h2_clean", "written": True},
            ],
        },
    )

    result = generate_codegen_scaffold_tool("member_user", str(workspace_root), write_files=True)

    assert result["ok"] is True
    sql_result = result["data"]["sql_result"]
    assert sql_result["write_result"]["ok"] is True
    assert {
        item["kind"] for item in sql_result["write_result"]["results"]
    } == {"mysql_migration", "h2_create_tables", "h2_clean"}
    assert sql_result["sql_bundle"]["codegen_sql_modes"] == {"menu": "auto", "dict": "auto"}
    assert sql_result["apply_result"]["ok"] is True
    assert len(apply_calls) == 1


def test_generate_codegen_sql_tool_creates_root_menu_when_missing(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder(
        manual_rules_yaml="""
- module: custom
  table_prefixes:
    - custom_demo
  table_rules:
    - table: custom_demo
      business: custom_demo
      entity: CustomDemo
""".strip()
    )

    fake_schema = {
        "resolved": True,
        "table_name": "custom_demo",
        "table_comment": "自定义演示",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
            {
                "column_name": "name",
                "column_comment": "名称",
                "sql_type": "varchar",
                "raw_type": "varchar(64)",
                "java_field": "name",
                "java_type": "String",
                "ts_type": "string",
                "html_type": "input",
                "nullable": False,
                "primary_key": False,
                "auto_increment": False,
                "is_base_column": False,
                "in_do": True,
                "in_save": True,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }

    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_sql_tool(
        "custom_demo",
        str(workspace_root),
        module_menu_name="自定义模块",
        menu_name="自定义演示",
    )

    assert result["ok"] is True
    menu_plan = result["data"]["sql_bundle"]["menu_plan"]
    assert menu_plan["needs_create_root_menu"] is True
    assert menu_plan["root_menu"]["name"] == "自定义模块"
    assert menu_plan["root_menu"]["path"] == "/custom"
    assert menu_plan["business_menu"]["name"] == "自定义演示管理"


def test_generate_codegen_sql_tool_names_missing_root_menu_from_business(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder(
        manual_rules_yaml="""
- module: custom
  table_prefixes:
    - custom_demo
  table_rules:
    - table: custom_demo
      business: custom_demo
      entity: CustomDemo
""".strip()
    )

    fake_schema = {
        "resolved": True,
        "table_name": "custom_demo",
        "table_comment": "自定义演示",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }

    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_sql_tool("custom_demo", str(workspace_root))

    assert result["ok"] is True
    menu_plan = result["data"]["sql_bundle"]["menu_plan"]
    assert menu_plan["needs_create_root_menu"] is True
    assert menu_plan["root_menu"]["name"] == "自定义演示"
    assert menu_plan["root_menu"]["name"] != "custom"
    assert "'自定义演示'" in result["data"]["sql_bundle"]["mysql"]["content"]


def test_generate_codegen_sql_tool_uses_domain_names_for_travel_sim_sku(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder(
        manual_rules_yaml="""
- module: travel
  table_prefixes:
    - travel_sim
  table_rules:
    - table: travel_sim_sku
      business: sim_sku
      entity: TravelSimSku
""".strip()
    )

    fake_schema = {
        "resolved": True,
        "table_name": "travel_sim_sku",
        "table_comment": "旅游手机卡 SKU",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
            {
                "column_name": "card_type",
                "column_comment": "卡类型（1-实物SIM卡，2-eSIM/流量包）",
                "sql_type": "tinyint",
                "raw_type": "tinyint",
                "java_field": "cardType",
                "java_type": "Integer",
                "ts_type": "number",
                "html_type": "select",
                "nullable": False,
                "primary_key": False,
                "auto_increment": False,
                "is_base_column": False,
                "in_do": True,
                "in_save": True,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }

    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_sql_tool("travel_sim_sku", str(workspace_root))

    assert result["ok"] is True
    menu_plan = result["data"]["sql_bundle"]["menu_plan"]
    assert menu_plan["root_menu"]["name"] == "旅游管理"
    assert menu_plan["business_menu"]["name"] == "手机卡 SKU管理"
    assert [button["name"] for button in menu_plan["buttons"]] == [
        "手机卡 SKU查询",
        "手机卡 SKU创建",
        "手机卡 SKU更新",
        "手机卡 SKU删除",
        "手机卡 SKU导出",
    ]
    dict_plan = result["data"]["sql_bundle"]["dict_plan"]
    assert dict_plan["dict_types"][0]["dict_name"] == "旅游手机卡 SKU卡类型"
    sql = result["data"]["sql_bundle"]["mysql"]["content"]
    assert "'旅游管理'" in sql
    assert "'手机卡 SKU管理'" in sql
    assert "'旅游手机卡 SKU卡类型'" in sql


def test_generate_codegen_sql_tool_reuses_configured_root_for_nested_backend_module(
    workspace_builder,
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace_root = workspace_builder(
        manual_rules_yaml="""
- module: travel
  table_prefixes:
    - travel_sim
  table_rules:
    - table: travel_sim_sku
      business: sim_sku
      entity: TravelSimSku
""".strip()
    )
    backend_root = _create_fake_backend(tmp_path)
    _rewrite_backend_path(workspace_root, backend_root)
    sql_dump_path = backend_root / "sql" / "mysql" / "ruoyi-vue-pro.sql"
    sql_dump_path.parent.mkdir(parents=True, exist_ok=True)
    sql_dump_path.write_text(
        dedent(
            """\
            INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`) VALUES (5286, '旅游手机卡SPU管理', '', 2, 0, 5285, 'sim-spu', 'ep:apple', 'travel/sim_spu/index', 'SimSpu', 0, b'1', b'1', b'1', 'yudao-pilot', '2026-04-28 16:34:01', 'yudao-pilot', '2026-04-28 16:34:01', b'0');
            INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`) VALUES (5285, '旅游', '', 1, 510, 0, '/travel', 'ep:menu', NULL, NULL, 0, b'1', b'1', b'1', 'yudao-pilot', '2026-04-28 16:34:01', 'yudao-pilot', '2026-04-28 16:34:01', b'0');
            """
        ),
        encoding="utf-8",
    )

    fake_schema = {
        "resolved": True,
        "table_name": "travel_sim_sku",
        "table_comment": "旅游手机卡SKU",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            },
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_sql_tool(
        "travel_sim_sku",
        str(workspace_root),
        backend_module_dir="travel/sim",
        backend_package_module="sim",
    )

    assert result["ok"] is True
    menu_plan = result["data"]["sql_bundle"]["menu_plan"]
    assert menu_plan["needs_create_root_menu"] is False
    assert menu_plan["root_menu"]["id"] == 5285
    assert menu_plan["root_menu"]["path"] == "/travel"
    assert menu_plan["permission_prefix"] == "travel:sim-sku"
    assert [button["permission"] for button in menu_plan["buttons"]] == [
        "travel:sim-sku:query",
        "travel:sim-sku:create",
        "travel:sim-sku:update",
        "travel:sim-sku:delete",
        "travel:sim-sku:export",
    ]
    sql = result["data"]["sql_bundle"]["mysql"]["content"]
    assert "path = '/travel'" in sql
    assert "path = '/sim'" not in sql
    assert "'travel:sim-sku:query'" in sql
    assert "'sim:travel-sim-sku:query'" not in sql


def test_generate_codegen_sql_tool_supports_explicit_menu_icon_override(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder()
    fake_schema = {
        "resolved": True,
        "table_name": "merchant",
        "table_comment": "商家",
        "schema_source": "database",
        "message": "已模拟解析表结构",
        "columns": [
            {
                "column_name": "id",
                "column_comment": "编号",
                "sql_type": "bigint",
                "raw_type": "bigint",
                "java_field": "id",
                "java_type": "Long",
                "ts_type": "number",
                "html_type": "input",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
                "is_base_column": False,
                "in_do": True,
                "in_save": False,
                "in_resp": True,
                "in_list": True,
                "in_query": True,
            }
        ],
    }
    monkeypatch.setattr(schema_module, "inspect_table_schema", lambda *args, **kwargs: fake_schema)
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    result = generate_codegen_sql_tool(
        "merchant",
        str(workspace_root),
        module_menu_name="会员中心",
        menu_name="商家",
        menu_icon="lucide:store",
        module_menu_icon="lucide:users",
    )

    assert result["ok"] is True
    menu_plan = result["data"]["sql_bundle"]["menu_plan"]
    assert menu_plan["root_menu"]["icon"] == "lucide:users"
    assert menu_plan["business_menu"]["icon"] == "lucide:store"
    assert "'lucide:store'" in result["data"]["sql_bundle"]["mysql"]["content"]


def test_merge_sql_snippet_is_idempotent(tmp_path: Path) -> None:
    sql_file = tmp_path / "create_tables.sql"
    sql_file.write_text('CREATE TABLE IF NOT EXISTS "member_user" (\n    "id" bigint\n);\n', encoding="utf-8")

    first = merge_sql_snippet(
        sql_file,
        marker='CREATE TABLE IF NOT EXISTS "merchant"',
        content='CREATE TABLE IF NOT EXISTS "merchant" (\n    "id" bigint\n);\n',
    )
    second = merge_sql_snippet(
        sql_file,
        marker='CREATE TABLE IF NOT EXISTS "merchant"',
        content='CREATE TABLE IF NOT EXISTS "merchant" (\n    "id" bigint\n);\n',
    )

    assert first["ok"] is True
    assert first["written"] is True
    assert second["ok"] is True
    assert second["written"] is False
    assert sql_file.read_text(encoding="utf-8").count('CREATE TABLE IF NOT EXISTS "merchant"') == 1


def test_resolve_h2_sql_plan_auto_creates_missing_module_sql_files(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    module_root = backend_root / "yudao-module-hotel"
    module_root.mkdir(parents=True)

    result = resolve_h2_sql_plan(backend_root, "hotel")

    assert result["resolved"] is True
    assert "已自动创建基础文件" in result["message"]
    assert (module_root / "src/test/resources/sql/create_tables.sql").exists()
    assert (module_root / "src/test/resources/sql/clean.sql").exists()


def test_write_mysql_migration_reuses_existing_logical_migration(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    migration_dir = backend_root / "sql" / "mysql" / "migrations"
    migration_dir.mkdir(parents=True)
    existing_path = migration_dir / "2026_05_07_101010_add_travel_sim_sku_menus.sql"
    existing_path.write_text("-- existing\nSELECT 1;\n", encoding="utf-8")

    first = write_mysql_migration(
        backend_root,
        "add_travel_sim_sku_menus",
        "SELECT 2;",
    )
    content_after_first_write = existing_path.read_text(encoding="utf-8")
    second = write_mysql_migration(
        backend_root,
        "add_travel_sim_sku_menus",
        "SELECT 3;",
        overwrite=True,
    )

    migration_files = sorted(migration_dir.glob("*_add_travel_sim_sku_menus.sql"))
    assert len(migration_files) == 1
    assert first["ok"] is True
    assert first["written"] is False
    assert first["path"] == str(existing_path)
    assert content_after_first_write == "-- existing\nSELECT 1;\n"
    assert second["ok"] is True
    assert second["written"] is True
    assert second["path"] == str(existing_path)
    assert "SELECT 3;" in existing_path.read_text(encoding="utf-8")


def test_generate_codegen_sql_tool_continues_database_apply_when_file_write_fails(
    workspace_builder, monkeypatch
) -> None:
    workspace_root = workspace_builder()
    config_path = workspace_root / ".yudao-pilot" / "config.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_config["codegen"]["apply_to_database"] = True
    config_path.write_text(
        yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    apply_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "yudao_pilot.server.infer_table_resolution",
        lambda *args, **kwargs: TableResolution(
            module="hotel",
            matched_by="new_module",
            business="hotel_brand",
            entity="HotelBrand",
        ),
    )
    monkeypatch.setattr(
        "yudao_pilot.server.build_codegen_context",
        lambda *args, **kwargs: {
            "module_name": "hotel",
            "business_name": "hotel_brand",
            "entity_name": "HotelBrand",
            "table_name": "hotel_brand",
            "backend_project": {"repo_root": "/tmp/fake-backend"},
            "codegen_sql": {"apply_to_database": True, "menu_mode": "auto", "dict_mode": "auto"},
        },
    )
    monkeypatch.setattr(
        "yudao_pilot.server.build_codegen_sql_bundle",
        lambda *args, **kwargs: {
            "ok": True,
            "message": "ok",
            "backend_repo_root": "/tmp/fake-backend",
            "mysql": {
                "migration_name": "add_hotel_brand_menus",
                "content": "-- test\n",
            },
            "h2": {
                "resolved": False,
                "message": "未能唯一定位模块测试 SQL 文件，请检查后端模块结构",
            },
            "menu_plan": {
                "disabled": False,
                "all_menus_exist": False,
                "root_menu": {"name": "酒店管理"},
                "business_menu": {"name": "品牌管理"},
                "buttons": [],
            },
            "dict_plan": {
                "disabled": False,
                "has_dicts": False,
                "all_complete": True,
            },
        },
    )
    monkeypatch.setattr(
        "yudao_pilot.server.write_codegen_sql_bundle",
        lambda *args, **kwargs: {
            "ok": False,
            "results": [
                {
                    "ok": False,
                    "kind": "h2_create_tables",
                    "message": "未能唯一定位模块测试 SQL 文件，请检查后端模块结构",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "yudao_pilot.server.resolve_database_config",
        lambda *args, **kwargs: {
            "ok": True,
            "database": {
                "host": "127.0.0.1",
                "port": 3306,
                "database": "demo",
                "username": "root",
                "password": "123456",
            },
            "message": "ok",
        },
    )

    def fake_apply_menu(database_config, menu_plan):
        apply_calls.append({"database": database_config, "menu_plan": menu_plan})
        return {
            "ok": True,
            "created": ["业务菜单:品牌管理"],
            "updated": [],
            "skipped": [],
        }

    monkeypatch.setattr("yudao_pilot.server.apply_menu_plan_to_database", fake_apply_menu)

    result = generate_codegen_sql_tool(
        "hotel_brand",
        str(workspace_root),
        write_files=True,
    )

    assert result["ok"] is True
    assert result["message"] == "SQL 已生成并执行数据库写入，但部分文件写入失败"
    assert result["data"]["write_result"]["ok"] is False
    assert result["data"]["apply_result"]["ok"] is True
    assert len(apply_calls) == 1


def test_apply_menu_plan_to_database_is_idempotent(monkeypatch) -> None:
    statements: list[tuple[str, tuple[object, ...] | None]] = []
    fetch_queue = [
        None,
        {"max_sort": 30},
        None,
        None,
        None,
        None,
    ]

    class FakeCursor:
        def __init__(self) -> None:
            self.lastrowid = 100

        def execute(self, sql, params=None):
            statements.append((" ".join(sql.split()), params))
            normalized = " ".join(sql.split())
            if normalized.startswith("INSERT INTO system_menu"):
                self.lastrowid += 1

        def fetchone(self):
            return fetch_queue.pop(0) if fetch_queue else None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_obj = FakeCursor()
            self.committed = False
            self.rolled_back = False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            pass

    fake_connection = FakeConnection()

    class FakePyMySQL:
        class cursors:
            DictCursor = object

        @staticmethod
        def connect(**kwargs):
            return fake_connection

    monkeypatch.setitem(sys.modules, "pymysql", FakePyMySQL)

    menu_plan = {
        "root_menu": {
            "name": "会员中心",
            "sort": 40,
            "path": "/member",
            "icon": "ep:menu",
            "lookup_paths": ["/member", "member"],
        },
        "business_menu": {
            "name": "商家管理",
            "sort": 0,
            "path": "merchant",
            "icon": "",
            "component": "member/merchant/index",
            "component_name": "Merchant",
        },
        "buttons": [
            {
                "name": "商家查询",
                "permission": "member:merchant:query",
                "sort": 1,
            },
            {
                "name": "商家创建",
                "permission": "member:merchant:create",
                "sort": 2,
            },
        ],
    }

    result = apply_menu_plan_to_database(
        {
            "host": "127.0.0.1",
            "port": 3306,
            "database": "demo",
            "username": "root",
            "password": "123456",
        },
        menu_plan,
    )

    assert result["ok"] is True
    assert fake_connection.committed is True
    assert fake_connection.rolled_back is False
    assert "根菜单:会员中心" in result["created"]
    assert "业务菜单:商家管理" in result["created"]
    assert "按钮:member:merchant:query" in result["created"]
    assert any(
        "FROM system_menu WHERE deleted = b'0' AND parent_id = 0" in sql
        for sql, _ in statements
    )


def test_apply_menu_plan_to_database_updates_existing_menu_icon(monkeypatch) -> None:
    statements: list[tuple[str, tuple[object, ...] | None]] = []
    fetch_queue = [
        {"id": 2262, "name": "会员中心", "path": "/member", "icon": "ep:bicycle"},
        {
            "id": 6001,
            "parent_id": 2262,
            "name": "商家管理",
            "path": "merchant",
            "icon": "",
            "component": "member/merchant/index",
            "component_name": "Merchant",
        },
        None,
        None,
    ]

    class FakeCursor:
        def __init__(self) -> None:
            self.lastrowid = 6001

        def execute(self, sql, params=None):
            statements.append((" ".join(sql.split()), params))

        def fetchone(self):
            return fetch_queue.pop(0) if fetch_queue else None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_obj = FakeCursor()
            self.committed = False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("不应触发回滚")

        def close(self):
            pass

    fake_connection = FakeConnection()

    class FakePyMySQL:
        class cursors:
            DictCursor = object

        @staticmethod
        def connect(**kwargs):
            return fake_connection

    monkeypatch.setitem(sys.modules, "pymysql", FakePyMySQL)

    menu_plan = {
        "root_menu": {
            "name": "会员中心",
            "sort": 55,
            "path": "/member",
            "icon": "ep:bicycle",
            "lookup_paths": ["/member", "member"],
        },
        "business_menu": {
            "name": "商家管理",
            "sort": 0,
            "path": "merchant",
            "icon": "ep:shop",
            "component": "member/merchant/index",
            "component_name": "Merchant",
        },
        "buttons": [
            {
                "name": "商家查询",
                "permission": "member:merchant:query",
                "sort": 1,
            },
            {
                "name": "商家创建",
                "permission": "member:merchant:create",
                "sort": 2,
            },
        ],
    }

    result = apply_menu_plan_to_database(
        {
            "host": "127.0.0.1",
            "port": 3306,
            "database": "demo",
            "username": "root",
            "password": "123456",
        },
        menu_plan,
    )

    assert result["ok"] is True
    assert fake_connection.committed is True
    assert "根菜单:会员中心" in result["skipped"]
    assert "业务菜单:商家管理" in result["updated"]
    assert any(
        sql.startswith("UPDATE system_menu SET icon = %s, updater = %s WHERE id = %s")
        and params == ("ep:shop", "yudao-pilot", 6001)
        for sql, params in statements
    )


# ---------------------------------------------------------------------------
# scan_backend_table_entities
# ---------------------------------------------------------------------------


def test_scan_backend_table_entities_empty_on_missing_dir(tmp_path: Path) -> None:
    assert scan_backend_table_entities(tmp_path / "nonexistent") == []


# ---------------------------------------------------------------------------
# infer_table_resolution with backend_root (scan mode)
# ---------------------------------------------------------------------------

def test_infer_resolution_manual_exact_still_wins(workspace_builder) -> None:
    from yudao_pilot.config import load_workspace_config
    ws = workspace_builder()
    config = load_workspace_config(ws)
    backend_root = Path(yaml.safe_load((ws / ".yudao-pilot" / "config.yaml").read_text())["projects"]["backend"]["path"])
    r = infer_table_resolution("merchant", config, backend_root=backend_root)
    assert r.matched_by == "exact"
    assert r.module == "member"


def test_infer_resolution_manual_prefix_still_wins(workspace_builder) -> None:
    from yudao_pilot.config import load_workspace_config
    ws = workspace_builder()
    config = load_workspace_config(ws)
    backend_root = Path(yaml.safe_load((ws / ".yudao-pilot" / "config.yaml").read_text())["projects"]["backend"]["path"])
    r = infer_table_resolution("merchant_account", config, backend_root=backend_root)
    assert r.matched_by == "prefix"
    assert r.module == "member"
    assert r.business == "merchant"


def test_infer_resolution_no_backend_root_falls_back(workspace_builder) -> None:
    from yudao_pilot.config import load_workspace_config
    ws = workspace_builder(
        manual_rules_yaml="""\
- module: member
  table_prefixes: []
  table_rules: []
""",
    )
    config = load_workspace_config(ws)
    r = infer_table_resolution("completely_unknown_table", config)
    assert r.matched_by == "fallback"
    assert r.module == "completely"


def test_infer_resolution_does_not_create_new_module_by_default(workspace_builder, tmp_path: Path) -> None:
    from yudao_pilot.config import load_workspace_config

    backend_root = tmp_path / "fake-backend"
    backend_root.mkdir()
    (backend_root / "yudao-server").mkdir()
    root_pom = backend_root / "pom.xml"
    root_pom.write_text("<project><modules></modules></project>", encoding="utf-8")
    server_pom = backend_root / "yudao-server" / "pom.xml"
    server_pom.write_text("<project><dependencies></dependencies></project>", encoding="utf-8")

    ws = workspace_builder(
        manual_rules_yaml="""\
- module: member
  table_prefixes: []
  table_rules: []
""",
    )
    config = load_workspace_config(ws)

    r = infer_table_resolution("logistics_order", config, backend_root=backend_root)

    assert r.matched_by == "new_module"
    assert r.module == "logistics"
    assert not (backend_root / "yudao-module-logistics").exists()
    assert root_pom.read_text(encoding="utf-8") == "<project><modules></modules></project>"
    assert server_pom.read_text(encoding="utf-8") == "<project><dependencies></dependencies></project>"


# ---------------------------------------------------------------------------
# New module creation
# ---------------------------------------------------------------------------

def test_create_module_scaffold(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    backend_root.mkdir()
    _create_module_scaffold(backend_root, "order")
    module_root = backend_root / "yudao-module-order"
    assert module_root.is_dir()
    assert (module_root / "pom.xml").exists()
    pom_content = (module_root / "pom.xml").read_text()
    assert "yudao-module-order" in pom_content
    assert (module_root / "src" / "main" / "java" / "cn" / "iocoder" / "yudao" / "module" / "order" / "enums" / "ErrorCodeConstants.java").exists()
    assert (module_root / "src" / "main" / "resources" / "mapper").is_dir()
    assert (module_root / "src" / "test" / "resources" / "sql" / "create_tables.sql").exists()


def test_ensure_module_enabled_uncomments_root_pom(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    backend_root.mkdir()
    (backend_root / "yudao-server").mkdir()

    root_pom = backend_root / "pom.xml"
    root_pom.write_text(
        "<project>\n"
        "    <modules>\n"
        "        <module>yudao-module-system</module>\n"
        "<!--        <module>yudao-module-crm</module>-->\n"
        "    </modules>\n"
        "</project>\n",
        encoding="utf-8",
    )
    server_pom = backend_root / "yudao-server" / "pom.xml"
    server_pom.write_text(
        "<project>\n"
        "    <dependencies>\n"
        "        <dependency>\n"
        "            <groupId>cn.iocoder.boot</groupId>\n"
        "            <artifactId>yudao-module-system</artifactId>\n"
        "            <version>${revision}</version>\n"
        "        </dependency>\n"
        "    </dependencies>\n"
        "</project>\n",
        encoding="utf-8",
    )

    _ensure_module_enabled(backend_root, "crm")

    assert "<!--" not in root_pom.read_text()
    assert "<module>yudao-module-crm</module>" in root_pom.read_text()
    assert "<artifactId>yudao-module-crm</artifactId>" in server_pom.read_text()


def test_ensure_module_enabled_adds_new_module(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    backend_root.mkdir()
    (backend_root / "yudao-server").mkdir()

    root_pom = backend_root / "pom.xml"
    root_pom.write_text(
        "<project>\n"
        "    <modules>\n"
        "        <module>yudao-module-system</module>\n"
        "    </modules>\n"
        "</project>\n",
        encoding="utf-8",
    )
    server_pom = backend_root / "yudao-server" / "pom.xml"
    server_pom.write_text(
        "<project>\n"
        "    <dependencies>\n"
        "    </dependencies>\n"
        "</project>\n",
        encoding="utf-8",
    )

    _ensure_module_enabled(backend_root, "logistics")

    assert "<module>yudao-module-logistics</module>" in root_pom.read_text()
    assert "<artifactId>yudao-module-logistics</artifactId>" in server_pom.read_text()


def test_infer_resolution_new_module_creates_scaffold_when_requested(workspace_builder, tmp_path: Path) -> None:
    from yudao_pilot.config import load_workspace_config

    backend_root = tmp_path / "fake-backend"
    backend_root.mkdir()
    (backend_root / "yudao-server").mkdir()
    (backend_root / "pom.xml").write_text(
        "<project><modules></modules></project>", encoding="utf-8"
    )
    (backend_root / "yudao-server" / "pom.xml").write_text(
        "<project><dependencies></dependencies></project>", encoding="utf-8"
    )

    ws = workspace_builder(
        manual_rules_yaml="""\
- module: member
  table_prefixes: []
  table_rules: []
""",
    )
    config = load_workspace_config(ws)
    r = infer_table_resolution(
        "logistics_order",
        config,
        backend_root=backend_root,
        create_missing_module=True,
    )
    assert r.matched_by == "new_module"
    assert r.module == "logistics"
    assert (backend_root / "yudao-module-logistics" / "pom.xml").exists()
    assert "<module>yudao-module-logistics</module>" in (backend_root / "pom.xml").read_text()


def _write_pom(path: Path, artifact_id: str, *, packaging: str = "jar", modules: list[str] | None = None) -> None:
    modules_xml = ""
    if modules:
        modules_xml = "<modules>\n" + "\n".join(f"    <module>{module}</module>" for module in modules) + "\n  </modules>"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<project>
  <modelVersion>4.0.0</modelVersion>
  <artifactId>{artifact_id}</artifactId>
  <packaging>{packaging}</packaging>
  {modules_xml}
</project>
""",
        encoding="utf-8",
    )


def test_backend_codegen_target_uses_child_jar_for_aggregator_module(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_pom(
        backend_root / "yudao-module-travel" / "pom.xml",
        "yudao-module-travel",
        packaging="pom",
        modules=[
            "yudao-module-hotel-product",
            "yudao-module-hotel-trade",
            "yudao-module-hotel-trade-api",
            "yudao-module-car-rental-biz",
        ],
    )
    _write_pom(backend_root / "yudao-module-travel" / "yudao-module-hotel-product" / "pom.xml", "yudao-module-hotel-product")
    _write_pom(backend_root / "yudao-module-travel" / "yudao-module-hotel-trade" / "pom.xml", "yudao-module-hotel-trade")
    _write_pom(backend_root / "yudao-module-travel" / "yudao-module-hotel-trade-api" / "pom.xml", "yudao-module-hotel-trade-api")
    _write_pom(backend_root / "yudao-module-travel" / "yudao-module-car-rental-biz" / "pom.xml", "yudao-module-car-rental-biz")
    (
        backend_root
        / "yudao-module-travel/yudao-module-hotel-product/src/main/java/cn/iocoder/yudao/module/product/dal/dataobject/brand"
    ).mkdir(parents=True)
    (
        backend_root
        / "yudao-module-travel/yudao-module-car-rental-biz/src/main/java/cn/iocoder/yudao/module/rental/dal/dataobject/order"
    ).mkdir(parents=True)

    hotel_target = resolve_backend_codegen_target(
        backend_root,
        module_name="travel",
        business_name="hotel/brand",
        table_name="hotel_brand",
        entity_name="HotelBrand",
    )
    rental_target = resolve_backend_codegen_target(
        backend_root,
        module_name="travel",
        business_name="car/order",
        table_name="car_rental_order",
        entity_name="CarRentalOrder",
    )

    assert hotel_target["module_dir_name"] == "yudao-module-travel/yudao-module-hotel-product"
    assert hotel_target["package_module_name"] == "product"
    assert hotel_target["matched_by"] == "aggregator_child"
    assert rental_target["module_dir_name"] == "yudao-module-travel/yudao-module-car-rental-biz"
    assert rental_target["package_module_name"] == "rental"


def test_generated_backend_plan_uses_resolved_module_dir_and_package(tmp_path: Path) -> None:
    target = {
        "module_dir_name": "yudao-module-travel/yudao-module-hotel-product",
        "package_module_name": "product",
    }

    plan = build_generated_file_plan(
        table_name="hotel_brand",
        module_name="product",
        business_name="brand",
        entity_name="HotelBrand",
        base_package="cn.iocoder.yudao",
        frontend_targets=[],
        unit_test_enable=False,
        backend_target=target,
    )

    assert "yudao-module-travel/yudao-module-hotel-product/src/main/java/cn/iocoder/yudao/module/product/controller/admin/brand/vo/HotelBrandPageReqVO.java" in plan["backend"]
    assert "yudao-module-travel/src/main/java" not in "\n".join(plan["backend"])


def test_explicit_backend_codegen_target_supports_nested_new_module(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    target = resolve_backend_codegen_target(
        backend_root,
        module_name="travel",
        business_name="sim_spu",
        table_name="travel_sim_spu",
        entity_name="TravelSimSpu",
        backend_module_dir="travel/sim-spu",
        backend_package_module="simspu",
    )

    assert target == {
        "module_dir_name": "yudao-module-travel/yudao-module-sim-spu",
        "package_module_name": "simspu",
        "matched_by": "explicit",
    }


def test_normalize_backend_module_dir_accepts_prefixed_and_unprefixed_paths() -> None:
    assert normalize_backend_module_dir("A/B") == "yudao-module-a/yudao-module-b"
    assert (
        normalize_backend_module_dir("yudao-module-travel/yudao-module-sim-spu")
        == "yudao-module-travel/yudao-module-sim-spu"
    )


def test_codegen_context_accepts_explicit_backend_module_target(
    workspace_builder,
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_root = workspace_builder()
    backend_root = _create_fake_backend(tmp_path)
    _rewrite_backend_path(workspace_root, backend_root)
    fake_schema = {
        "resolved": True,
        "table_name": "merchant_user",
        "table_comment": "商户用户",
        "columns": [],
    }
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    from yudao_pilot.config import load_workspace_config

    context = build_codegen_context(
        workspace_root,
        load_workspace_config(workspace_root),
        "merchant_user",
        module_name="travel",
        business_name="sim_spu",
        entity_name="TravelSimSpu",
        backend_module_dir="travel/sim-spu",
        backend_package_module="simspu",
    )

    target = context["backend_project"]["codegen_target"]
    assert target["matched_by"] == "explicit"
    assert target["module_dir_name"] == "yudao-module-travel/yudao-module-sim-spu"
    assert target["package_module_name"] == "simspu"
    assert context["module_name"] == "simspu"
    assert context["configured_module_name"] == "travel"
    assert any(
        path.startswith(
            "yudao-module-travel/yudao-module-sim-spu/src/main/java/cn/iocoder/yudao/module/simspu/"
        )
        for path in context["generated_file_plan"]["backend"]
    )


def test_codegen_context_strips_package_module_prefix_from_backend_business_name(
    workspace_builder,
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_root = workspace_builder()
    backend_root = _create_fake_backend(tmp_path)
    _rewrite_backend_path(workspace_root, backend_root)
    fake_schema = {
        "resolved": True,
        "table_name": "travel_sim_sku",
        "table_comment": "旅游手机卡 SKU",
        "columns": [],
    }
    monkeypatch.setattr("yudao_pilot.codegen.inspect_table_schema", lambda *args, **kwargs: fake_schema)

    from yudao_pilot.config import load_workspace_config

    context = build_codegen_context(
        workspace_root,
        load_workspace_config(workspace_root),
        "travel_sim_sku",
        module_name="travel",
        business_name="sim_sku",
        entity_name="TravelSimSku",
        backend_module_dir="travel/sim",
        backend_package_module="sim",
        preserve_business_name=True,
    )

    target = context["backend_project"]["codegen_target"]
    assert target["package_module_name"] == "sim"
    assert context["module_name"] == "sim"
    assert context["configured_module_name"] == "travel"
    assert context["backend_business_name"] == "sku"
    assert any("/controller/admin/sku/" in path for path in context["generated_file_plan"]["backend"])
    assert any("/dal/dataobject/sku/" in path for path in context["generated_file_plan"]["backend"])
    assert not any("/controller/admin/simsku/" in path for path in context["generated_file_plan"]["backend"])


def test_scaffold_includes_pom_for_missing_explicit_nested_backend_module(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_pom(
        backend_root / "yudao-module-travel" / "pom.xml",
        "yudao-module-travel",
        packaging="pom",
        modules=[],
    )
    plan = build_generated_file_plan(
        table_name="travel_sim_spu",
        module_name="simspu",
        business_name="sim_spu",
        entity_name="TravelSimSpu",
        base_package="cn.iocoder.yudao",
        frontend_targets=[],
        unit_test_enable=False,
        backend_target={
            "module_dir_name": "yudao-module-travel/yudao-module-travel-sim",
            "package_module_name": "simspu",
            "matched_by": "explicit",
        },
    )
    context = {
        "table_name": "travel_sim_spu",
        "module_name": "simspu",
        "configured_module_name": "travel",
        "business_name": "sim_spu",
        "backend_business_name": "simspu",
        "entity_name": "TravelSimSpu",
        "menu_name": "商品",
        "permission_prefix": "travel:sim-spu",
        "backend_project": {
            "type": "ruoyi-vue-pro-jdk17",
            "repo_root": str(backend_root),
            "codegen_target": plan["backend_target"],
        },
        "backend_codegen_defaults": {"base_package": "cn.iocoder.yudao"},
        "table_schema": {"columns": []},
        "generated_file_plan": plan,
    }

    files = generate_scaffold_files(context, include_frontend=False)
    pom_file = next(
        file
        for file in files
        if file.relative_path == "yudao-module-travel/yudao-module-travel-sim/pom.xml"
    )

    assert pom_file.overwrite is False
    assert "<artifactId>yudao-module-travel</artifactId>" in pom_file.content
    assert "<relativePath>" not in pom_file.content
    assert "<artifactId>yudao-module-travel-sim</artifactId>" in pom_file.content
