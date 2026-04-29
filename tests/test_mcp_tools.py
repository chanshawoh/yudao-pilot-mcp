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
    build_frontend_business_path,
    build_generated_file_plan,
    normalize_backend_business_name,
    resolve_backend_codegen_target,
)
from yudao_pilot.scaffold import render_backend_file, render_frontend_file
from yudao_pilot.sql_codegen import merge_sql_snippet, resolve_h2_sql_plan


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


def test_inspect_table_schema_tool_returns_columns(workspace_builder) -> None:
    workspace_root = workspace_builder(
        manual_rules_yaml="""
- module: yudao
  table_rules:
    - table: yudao_demo01_contact
      business: demo01_contact
      entity: Demo01Contact
""".strip()
    )
    result = inspect_table_schema_tool("yudao_demo01_contact", str(workspace_root))

    assert result["ok"] is True
    columns = result["data"]["columns"]
    assert any(column["column_name"] == "name" for column in columns)
    assert any(column["column_name"] == "birthday" for column in columns)


def test_inspect_codegen_context_contains_schema_and_plan(workspace_builder) -> None:
    workspace_root = workspace_builder()
    result = inspect_codegen_context_tool("member_user", str(workspace_root))

    assert result["ok"] is True
    data = result["data"]
    assert data["permission_prefix"] == "member:user"
    assert "table_schema" in data
    assert "generated_file_plan" in data
    assert data["migration_plan"]["directory"].endswith("/sql/mysql/migrations")
    assert data.get("codegen_sql", {}).get("menu_mode") == "auto"
    assert data.get("codegen_sql", {}).get("dict_mode") == "auto"
    assert all("yudao-module-member/src/" in path for path in data["generated_file_plan"]["backend"])
    assert all("yudao-module-member-server/" not in path for path in data["generated_file_plan"]["backend"])


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
    assert "请配置数据库连接" in result["message"]


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
    assert result["error_code"] == "table_schema_missing"
    assert "表不存在" in result["message"]
    assert "迁移SQL" in result["message"]


def test_inspect_table_schema_tool_applies_migration_sql_and_reports_execution(
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

    parsed_results = [
        None,
        {
            "resolved": True,
            "table_name": "missing_table",
            "table_comment": "缺失表",
            "sql_dump_path": None,
            "schema_source": "database",
            "database_name": "demo",
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
                    "auto_increment": False,
                    "is_base_column": False,
                    "in_do": True,
                    "in_save": False,
                    "in_resp": True,
                    "in_list": True,
                    "in_query": True,
                }
            ],
        },
    ]

    def fake_parse_from_database(database_config, table_name):
        return parsed_results.pop(0)

    monkeypatch.setattr(schema_module, "parse_table_schema_from_database", fake_parse_from_database)

    executed_sql: list[str] = []

    class FakeCursor:
        def execute(self, sql, params=None):
            executed_sql.append(" ".join(sql.split()))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeConnection:
        def __init__(self) -> None:
            self.committed = False
            self.rolled_back = False

        def cursor(self):
            return FakeCursor()

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

    result = inspect_table_schema_tool("missing_table", str(workspace_root))

    assert result["ok"] is True
    assert fake_connection.committed is True
    assert fake_connection.rolled_back is False
    assert any("CREATE TABLE `missing_table`" in sql for sql in executed_sql)
    assert result["data"]["executed_migration_sqls"] == [
        str(backend_root / "sql" / "mysql" / "migrations" / migration_filename)
    ]
    assert migration_filename in result["data"]["message"]


def test_infer_merchant_user_from_manual_rules(workspace_builder) -> None:
    workspace_root = workspace_builder()
    result = inspect_codegen_context_tool("merchant_user", str(workspace_root))

    assert result["ok"] is True
    data = result["data"]
    assert data["module_name"] == "member"
    assert data["business_name"] == "merchant_user"
    assert data["entity_name"] == "MerchantUser"
    assert data["permission_prefix"] == "member:merchant-user"


def test_infer_merchant_from_manual_rules(workspace_builder) -> None:
    workspace_root = workspace_builder()
    result = inspect_codegen_context_tool("merchant", str(workspace_root))

    assert result["ok"] is True
    data = result["data"]
    assert data["module_name"] == "member"
    assert data["business_name"] == "merchant"
    assert data["entity_name"] == "Merchant"
    assert data["permission_prefix"] == "member:merchant"


def test_generate_codegen_scaffold_includes_field_level_content(workspace_builder) -> None:
    workspace_root = workspace_builder(
        manual_rules_yaml="""
- module: yudao
  table_rules:
    - table: yudao_demo01_contact
      business: demo01_contact
      entity: Demo01Contact
""".strip()
    )
    result = generate_codegen_scaffold_tool("yudao_demo01_contact", str(workspace_root))

    assert result["ok"] is True
    generated_files = result["data"]["generated_files"]
    save_req = next(
        item
        for item in generated_files
        if item["relative_path"].endswith("Demo01ContactSaveReqVO.java")
    )
    form_vue = next(
        item
        for item in generated_files
        if item["relative_path"].endswith("Demo01ContactForm.vue")
    )

    assert "private String name;" in save_req["content"]
    assert "private LocalDateTime birthday;" in save_req["content"]
    assert 'v-model="formData.description"' in form_vue["content"]


def test_generate_codegen_scaffold_outputs_all_configured_frontends(workspace_builder) -> None:
    workspace_root = workspace_builder(
        frontend_types=(
            "VUE3_ELEMENT_PLUS",
            "VUE3_VBEN5_ANTD_SCHEMA",
            "VUE3_ADMIN_UNIAPP_WOT",
        )
    )
    result = generate_codegen_scaffold_tool("merchant", str(workspace_root))

    assert result["ok"] is True
    generated_files = result["data"]["generated_files"]
    summary: dict[str, int] = {}
    for item in generated_files:
        summary[item["target_type"]] = summary.get(item["target_type"], 0) + 1

    assert summary["VUE3_ELEMENT_PLUS"] == 3
    assert summary["VUE3_VBEN5_ANTD_SCHEMA"] == 4
    assert summary["VUE3_ADMIN_UNIAPP_WOT"] == 5


def test_generate_codegen_scaffold_supports_all_vben_variants(workspace_builder) -> None:
    workspace_root = workspace_builder(
        frontend_types=(
            "VUE3_VBEN5_ANTD_SCHEMA",
            "VUE3_VBEN5_ANTD_GENERAL",
            "VUE3_VBEN5_EP_SCHEMA",
            "VUE3_VBEN5_EP_GENERAL",
        )
    )
    result = generate_codegen_scaffold_tool("merchant", str(workspace_root))

    assert result["ok"] is True
    generated_files = result["data"]["generated_files"]
    grouped_paths: dict[str, list[str]] = {}
    for item in generated_files:
        grouped_paths.setdefault(item["target_type"], []).append(item["relative_path"])

    assert len(grouped_paths["VUE3_VBEN5_ANTD_SCHEMA"]) == 4
    assert len(grouped_paths["VUE3_VBEN5_ANTD_GENERAL"]) == 3
    assert len(grouped_paths["VUE3_VBEN5_EP_SCHEMA"]) == 4
    assert len(grouped_paths["VUE3_VBEN5_EP_GENERAL"]) == 3

    assert all(
        path.startswith("apps/web-antd/")
        for path in grouped_paths["VUE3_VBEN5_ANTD_SCHEMA"]
    )
    assert all(
        path.startswith("apps/web-antd/")
        for path in grouped_paths["VUE3_VBEN5_ANTD_GENERAL"]
    )
    assert all(
        path.startswith("apps/web-ele/")
        for path in grouped_paths["VUE3_VBEN5_EP_SCHEMA"]
    )
    assert all(
        path.startswith("apps/web-ele/")
        for path in grouped_paths["VUE3_VBEN5_EP_GENERAL"]
    )

    assert any(
        path.endswith("/data.ts")
        for path in grouped_paths["VUE3_VBEN5_ANTD_SCHEMA"]
    )
    assert not any(
        path.endswith("/data.ts")
        for path in grouped_paths["VUE3_VBEN5_ANTD_GENERAL"]
    )
    assert any(
        path.endswith("/data.ts")
        for path in grouped_paths["VUE3_VBEN5_EP_SCHEMA"]
    )
    assert not any(
        path.endswith("/data.ts")
        for path in grouped_paths["VUE3_VBEN5_EP_GENERAL"]
    )


def test_generate_codegen_scaffold_uses_suffix_subdirectory_when_frontend_business_collides(
    workspace_builder,
) -> None:
    workspace_root = workspace_builder(
        frontend_types=("VUE3_VBEN5_ANTD_SCHEMA",),
        manual_rules_yaml="""
- module: member
  table_prefixes:
    - merchant
  table_rules:
    - table: merchant
      business: merchant
      entity: Merchant
    - table: merchant_user
      business: merchant
      entity: MerchantUser
""".strip(),
    )
    result = generate_codegen_scaffold_tool("merchant_user", str(workspace_root))

    assert result["ok"] is True
    generated_files = result["data"]["generated_files"]
    frontend_paths = [
        item["relative_path"]
        for item in generated_files
        if item["target_kind"] == "frontend" and item["target_type"] == "VUE3_VBEN5_ANTD_SCHEMA"
    ]

    assert all("/member/merchant/user/" in path for path in frontend_paths)
    assert result["data"]["context"]["generated_file_plan"]["frontend_business_path"] == "merchant/user"


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
    assert "src/api/travel/simSpu/index.ts" in plan["frontends"][0]["relative_paths"]
    assert not any("sim_spu" in path for path in plan["frontends"][0]["relative_paths"])


def test_backend_business_name_removes_underscores() -> None:
    assert normalize_backend_business_name("sim_spu") == "simspu"
    assert normalize_backend_business_name("hotel/room_type") == "hotel/roomtype"


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


def test_generate_codegen_scaffold_uses_simple_class_name_for_vue3_form_import(
    workspace_builder,
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

    result = generate_codegen_scaffold_tool("hotel_brand", str(workspace_root))

    assert result["ok"] is True
    index_vue = next(
        item
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("src/views/hotel/brand/index.vue")
    )

    assert "import BrandForm from './BrandForm.vue'" in index_vue["content"]
    assert "<BrandForm ref=\"formRef\" @success=\"getList\" />" in index_vue["content"]
    assert "import HotelBrandForm from './BrandForm.vue'" not in index_vue["content"]


def test_generate_codegen_scaffold_uses_business_name_for_controller_route(
    workspace_builder,
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

    result = generate_codegen_scaffold_tool("hotel_brand", str(workspace_root))

    assert result["ok"] is True
    controller_java = next(
        item
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("controller/admin/brand/HotelBrandController.java")
    )

    assert '@RequestMapping("/hotel/brand")' in controller_java["content"]
    assert '@RequestMapping("/hotel/hotel-brand")' not in controller_java["content"]


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
            "controller/admin/tourism_location/SystemTourismLocationController.java"
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


def test_generate_codegen_scaffold_uses_business_name_for_frontend_api_route(
    workspace_builder,
) -> None:
    workspace_root = workspace_builder(
        frontend_types=("VUE3_ELEMENT_PLUS", "VUE3_VBEN5_ANTD_SCHEMA"),
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

    result = generate_codegen_scaffold_tool("hotel_brand", str(workspace_root))

    assert result["ok"] is True
    vue3_api = next(
        item
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("src/api/hotel/brand/index.ts")
        and item["target_type"] == "VUE3_ELEMENT_PLUS"
    )
    vben_api = next(
        item
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("apps/web-antd/src/api/hotel/brand/index.ts")
        and item["target_type"] == "VUE3_VBEN5_ANTD_SCHEMA"
    )

    assert "/admin-api/hotel/brand/page" in vue3_api["content"]
    assert "/admin-api/hotel/hotel-brand/page" not in vue3_api["content"]
    assert "/hotel/brand/page" in vben_api["content"]
    assert "/hotel/hotel-brand/page" not in vben_api["content"]


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
        if item["relative_path"].endswith("src/api/system/tourism_location/index.ts")
        and item["target_type"] == "VUE3_ELEMENT_PLUS"
    )

    first_line = vue3_api["content"].splitlines()[0]
    assert first_line == "import request from '@/config/axios'"
    assert not first_line.startswith(" ")
    assert "\n        export const" not in vue3_api["content"]


def test_generate_codegen_scaffold_vue3_api_includes_export_method(
    workspace_builder,
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

    result = generate_codegen_scaffold_tool("hotel_brand", str(workspace_root))

    assert result["ok"] is True
    vue3_api = next(
        item
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("src/api/hotel/brand/index.ts")
        and item["target_type"] == "VUE3_ELEMENT_PLUS"
    )

    assert "export const exportHotelBrand = async (params: any) => {" in vue3_api["content"]
    assert "request.download({ url: '/admin-api/hotel/brand/export-excel', params })" in vue3_api["content"]


def test_generate_codegen_scaffold_vue3_index_replaces_todo_with_upstream_style_flows(
    workspace_builder,
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

    result = generate_codegen_scaffold_tool("hotel_brand", str(workspace_root))

    assert result["ok"] is True
    index_vue = next(
        item
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("src/views/hotel/brand/index.vue")
    )

    assert "TODO Yudao Pilot" not in index_vue["content"]
    assert "const queryParams = reactive({" in index_vue["content"]
    assert "const getList = async () => {" in index_vue["content"]
    assert "const handleQuery = () => {" in index_vue["content"]
    assert "const resetQuery = () => {" in index_vue["content"]
    assert "const handleDelete = async (id: number) => {" in index_vue["content"]
    assert "const handleExport = async () => {" in index_vue["content"]
    assert "await exportHotelBrand(queryParams)" in index_vue["content"]
    assert "v-hasPermi=\"['hotel:brand:export']\"" in index_vue["content"]


def test_generate_codegen_scaffold_vue3_form_replaces_todo_with_upstream_style_submit_flow(
    workspace_builder,
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

    result = generate_codegen_scaffold_tool("hotel_brand", str(workspace_root))

    assert result["ok"] is True
    form_vue = next(
        item
        for item in result["data"]["generated_files"]
        if item["relative_path"].endswith("src/views/hotel/brand/BrandForm.vue")
    )

    assert "TODO Yudao Pilot" not in form_vue["content"]
    assert "import { createHotelBrand, getHotelBrand, updateHotelBrand } from '@/api/hotel/brand'" in form_vue["content"]
    assert "const formLoading = ref(false)" in form_vue["content"]
    assert "const formType = ref('')" in form_vue["content"]
    assert "const resetForm = () => {" in form_vue["content"]
    assert "const open = async (type: string, id?: number) => {" in form_vue["content"]
    assert "formData.value = await getHotelBrand(id)" in form_vue["content"]
    assert "const submitForm = async () => {" in form_vue["content"]
    assert "if (formType.value === 'create') {" in form_vue["content"]
    assert "await createHotelBrand(data)" in form_vue["content"]
    assert "await updateHotelBrand(data)" in form_vue["content"]


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
        if item["relative_path"].endswith("src/views/hotel/brand/BrandForm.vue")
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


def test_generate_codegen_scaffold_vben_includes_export_contract_and_toolbar_action(
    workspace_builder,
) -> None:
    workspace_root = workspace_builder(
        frontend_types=("VUE3_VBEN5_ANTD_SCHEMA",),
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

    result = generate_codegen_scaffold_tool("hotel_brand", str(workspace_root))

    assert result["ok"] is True
    api_ts = next(
        item["content"]
        for item in result["data"]["generated_files"]
        if item["target_type"] == "VUE3_VBEN5_ANTD_SCHEMA"
        and item["relative_path"].endswith("apps/web-antd/src/api/hotel/brand/index.ts")
    )
    index_vue = next(
        item["content"]
        for item in result["data"]["generated_files"]
        if item["target_type"] == "VUE3_VBEN5_ANTD_SCHEMA"
        and item["relative_path"].endswith("apps/web-antd/src/views/hotel/brand/index.vue")
    )

    assert "export function exportHotelBrand(params" in api_ts
    assert "requestClient.download('/hotel/brand/export-excel'" in api_ts
    assert "import { deleteHotelBrand, exportHotelBrand, getHotelBrandPage }" in index_vue
    assert "auth: ['hotel:brand:export']" in index_vue


def test_generate_codegen_scaffold_uniapp_replaces_placeholder_pages_with_data_flows(
    workspace_builder,
) -> None:
    workspace_root = workspace_builder(
        frontend_types=("VUE3_ADMIN_UNIAPP_WOT",),
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

    result = generate_codegen_scaffold_tool("hotel_brand", str(workspace_root))

    assert result["ok"] is True
    api_ts = next(
        item["content"]
        for item in result["data"]["generated_files"]
        if item["target_type"] == "VUE3_ADMIN_UNIAPP_WOT"
        and item["relative_path"].endswith("src/api/hotel/brand/index.ts")
    )
    index_vue = next(
        item["content"]
        for item in result["data"]["generated_files"]
        if item["target_type"] == "VUE3_ADMIN_UNIAPP_WOT"
        and item["relative_path"].endswith("src/pages-hotel/brand/index.vue")
    )
    search_vue = next(
        item["content"]
        for item in result["data"]["generated_files"]
        if item["target_type"] == "VUE3_ADMIN_UNIAPP_WOT"
        and item["relative_path"].endswith("src/pages-hotel/brand/components/search-form.vue")
    )
    form_vue = next(
        item["content"]
        for item in result["data"]["generated_files"]
        if item["target_type"] == "VUE3_ADMIN_UNIAPP_WOT"
        and item["relative_path"].endswith("src/pages-hotel/brand/form/index.vue")
    )
    detail_vue = next(
        item["content"]
        for item in result["data"]["generated_files"]
        if item["target_type"] == "VUE3_ADMIN_UNIAPP_WOT"
        and item["relative_path"].endswith("src/pages-hotel/brand/detail/index.vue")
    )

    assert "export function exportHotelBrand" in api_ts
    assert "http.download" in api_ts
    assert "SearchForm @search=\"handleQuery\" @reset=\"handleReset\"" in index_vue
    assert "const loadMoreState = ref<LoadMoreState>('loading')" in index_vue
    assert "async function getList()" in index_vue
    assert "function handleAdd()" in index_vue
    assert "function handleDetail(item: HotelBrand)" in index_vue
    assert "wd-search" in search_vue
    assert "emit('search'" in search_vue
    assert "emit('reset')" in search_vue
    assert "async function handleSubmit()" in form_vue
    assert "await createHotelBrand" in form_vue
    assert "await updateHotelBrand" in form_vue
    assert "detail.value = await getHotelBrand(props.id)" in detail_vue
    assert "const detail = ref<HotelBrand | null>(null)" in detail_vue


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


def test_generate_codegen_scaffold_write_files_outputs_frontend_artifacts(
    tmp_path: Path, repo_root: Path
) -> None:
    workspace_root = tmp_path / "workspace"
    config_dir = workspace_root / ".yudao-pilot"
    config_dir.mkdir(parents=True, exist_ok=True)

    vue3_root = tmp_path / "frontend-vue3"
    vben_root = tmp_path / "frontend-vben"
    uniapp_root = tmp_path / "frontend-uniapp"
    vue3_root.mkdir(parents=True, exist_ok=True)
    vben_root.mkdir(parents=True, exist_ok=True)
    uniapp_root.mkdir(parents=True, exist_ok=True)

    raw_config = {
        "version": 1,
        "workspace": {"name": "write-files-workspace"},
        "projects": {
            "backend": {
                "path": str(repo_root / "yudao-projects" / "ruoyi-vue-pro-jdk17"),
                "type": "ruoyi-vue-pro-jdk17",
                "config_profile": "local",
            },
            "frontend": [
                {"type": "VUE3_ELEMENT_PLUS", "path": str(vue3_root)},
                {"type": "VUE3_VBEN5_ANTD_GENERAL", "path": str(vben_root)},
                {"type": "VUE3_VBEN5_ANTD_SCHEMA", "path": str(vben_root)},
                {"type": "VUE3_VBEN5_EP_GENERAL", "path": str(vben_root)},
                {"type": "VUE3_VBEN5_EP_SCHEMA", "path": str(vben_root)},
                {"type": "VUE3_ADMIN_UNIAPP_WOT", "path": str(uniapp_root)},
            ],
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
            "manual_rules": [
                {
                    "module": "member",
                    "table_prefixes": ["merchant"],
                    "table_rules": [
                        {
                            "table": "merchant",
                            "business": "merchant",
                            "entity": "Merchant",
                        }
                    ],
                }
            ],
        },
    }
    (config_dir / "config.yaml").write_text(
        yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = generate_codegen_scaffold_tool(
        "merchant",
        str(workspace_root),
        include_backend=False,
        include_frontend=True,
        write_files=True,
        overwrite=True,
    )

    assert result["ok"] is True
    assert (vue3_root / "src/views/member/merchant/index.vue").exists()
    assert (vue3_root / "src/api/member/merchant/index.ts").exists()
    assert (vben_root / "apps/web-antd/src/views/member/merchant/data.ts").exists()
    assert (vben_root / "apps/web-antd/src/views/member/merchant/index.vue").exists()
    assert (vben_root / "apps/web-ele/src/views/member/merchant/data.ts").exists()
    assert (vben_root / "apps/web-ele/src/views/member/merchant/index.vue").exists()
    assert (uniapp_root / "src/pages-member/merchant/index.vue").exists()
    assert (uniapp_root / "src/api/member/merchant/index.ts").exists()

    web_antd_index = (vben_root / "apps/web-antd/src/views/member/merchant/index.vue").read_text(
        encoding="utf-8"
    )
    web_ele_index = (vben_root / "apps/web-ele/src/views/member/merchant/index.vue").read_text(
        encoding="utf-8"
    )
    web_ele_form = (vben_root / "apps/web-ele/src/views/member/merchant/modules/form.vue").read_text(
        encoding="utf-8"
    )
    assert "import { useGridColumns, useGridFormSchema } from './data'" in web_antd_index
    assert "import { useGridColumns, useGridFormSchema } from './data'" in web_ele_index
    assert "import { ElLoading, ElMessage } from 'element-plus';" in web_ele_index
    assert "link: true" in web_ele_index
    assert "import { ElMessage } from 'element-plus';" in web_ele_form


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


def test_generate_codegen_sql_tool_applies_when_config_enabled_even_in_migration_only_mode(
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

def test_scan_backend_table_entities_finds_do_files(repo_root: Path) -> None:
    backend_root = repo_root / "yudao-projects" / "ruoyi-vue-pro-jdk17"
    entities = scan_backend_table_entities(backend_root)
    table_names = {e.table_name for e in entities}
    assert "hotel_brand" in table_names
    hotel_brand = next(e for e in entities if e.table_name == "hotel_brand")
    assert hotel_brand.module_name == "hotel"
    assert hotel_brand.business_dir == "brand"


def test_scan_backend_table_entities_empty_on_missing_dir(tmp_path: Path) -> None:
    assert scan_backend_table_entities(tmp_path / "nonexistent") == []


# ---------------------------------------------------------------------------
# infer_table_resolution with backend_root (scan mode)
# ---------------------------------------------------------------------------

def test_infer_resolution_manual_exact_still_wins(workspace_builder, repo_root: Path) -> None:
    from yudao_pilot.config import load_workspace_config
    ws = workspace_builder()
    config = load_workspace_config(ws)
    backend_root = (repo_root / "yudao-projects" / "ruoyi-vue-pro-jdk17")
    r = infer_table_resolution("merchant", config, backend_root=backend_root)
    assert r.matched_by == "exact"
    assert r.module == "member"


def test_infer_resolution_manual_prefix_still_wins(workspace_builder, repo_root: Path) -> None:
    from yudao_pilot.config import load_workspace_config
    ws = workspace_builder()
    config = load_workspace_config(ws)
    backend_root = (repo_root / "yudao-projects" / "ruoyi-vue-pro-jdk17")
    r = infer_table_resolution("merchant_account", config, backend_root=backend_root)
    assert r.matched_by == "prefix"
    assert r.module == "member"
    assert r.business == "merchant"


def test_infer_resolution_scan_matches_existing_do(workspace_builder, repo_root: Path) -> None:
    from yudao_pilot.config import load_workspace_config
    ws = workspace_builder(
        manual_rules_yaml="""\
- module: member
  table_prefixes: []
  table_rules: []
""",
    )
    config = load_workspace_config(ws)
    backend_root = (repo_root / "yudao-projects" / "ruoyi-vue-pro-jdk17")
    r = infer_table_resolution("system_notice_template", config, backend_root=backend_root)
    assert r.matched_by == "scan"
    assert r.module == "system"


def test_infer_resolution_scan_uses_suffix_business_when_table_prefixed_by_module(
    workspace_builder, repo_root: Path
) -> None:
    from yudao_pilot.config import load_workspace_config

    ws = workspace_builder(
        manual_rules_yaml="""\
- module: member
  table_prefixes: []
  table_rules: []
""",
    )
    config = load_workspace_config(ws)
    backend_root = repo_root / "yudao-projects" / "ruoyi-vue-pro-jdk17"
    r = infer_table_resolution("hotel_brand", config, backend_root=backend_root)

    assert r.matched_by in {"scan", "new_module"}
    assert r.module == "hotel"
    assert r.business == "brand"


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
