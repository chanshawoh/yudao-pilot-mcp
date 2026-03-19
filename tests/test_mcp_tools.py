from __future__ import annotations

import yaml

from yudao_pilot import schema as schema_module
from yudao_pilot.server import (
    generate_codegen_scaffold_tool,
    inspect_codegen_context_tool,
    inspect_table_schema_tool,
    resolve_database_config_tool,
)


def test_resolve_database_config_from_backend_local(workspace_builder) -> None:
    workspace_root = workspace_builder()
    result = resolve_database_config_tool(str(workspace_root))

    assert result["ok"] is True
    assert result["data"]["database"]["host"] == "127.0.0.1"
    assert result["data"]["database"]["database"] == "ruoyi-vue-pro"
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
    assert all("yudao-module-member/src/" in path for path in data["generated_file_plan"]["backend"])
    assert all("yudao-module-member-server/" not in path for path in data["generated_file_plan"]["backend"])


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
