from __future__ import annotations

from pathlib import Path

import yaml

from yudao_pilot.config import auto_init_workspace_config, load_workspace_config
from yudao_pilot.server import load_workspace_config_tool, validate_workspace_projects_tool


def _write_backend_project(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "yudao-server").mkdir()
    (path / "pom.xml").write_text(
        """<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>cn.iocoder.boot</groupId>
  <artifactId>yudao</artifactId>
  <packaging>pom</packaging>
  <properties>
    <java.version>17</java.version>
    <spring.boot.version>3.2.0</spring.boot.version>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>cn.iocoder.boot</groupId>
        <artifactId>yudao-dependencies</artifactId>
        <version>${revision}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <modules>
    <module>yudao-server</module>
  </modules>
</project>
""",
        encoding="utf-8",
    )
    (path / "yudao-server" / "pom.xml").write_text(
        """<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>cn.iocoder.boot</groupId>
    <artifactId>yudao</artifactId>
  </parent>
  <artifactId>yudao-server</artifactId>
  <dependencies>
    <dependency>
      <groupId>cn.iocoder.boot</groupId>
      <artifactId>yudao-module-system</artifactId>
    </dependency>
    <dependency>
      <groupId>cn.iocoder.boot</groupId>
      <artifactId>yudao-module-infra</artifactId>
    </dependency>
    <dependency>
      <groupId>cn.iocoder.boot</groupId>
      <artifactId>yudao-spring-boot-starter-protection</artifactId>
    </dependency>
    <dependency>
      <groupId>com.baomidou</groupId>
      <artifactId>mybatis-plus-spring-boot3-starter</artifactId>
    </dependency>
  </dependencies>
</project>
""",
        encoding="utf-8",
    )


def _write_vue3_project(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(
        """{
  "dependencies": {
    "element-plus": "^2.0.0",
    "pinia": "^2.0.0",
    "vue": "^3.4.0",
    "vue-router": "^4.0.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "vite": "^5.0.0"
  }
}
""",
        encoding="utf-8",
    )


def _write_vben_project(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(
        """{
  "scripts": {
    "dev": "turbo run dev"
  },
  "dependencies": {
    "@vben/common-ui": "workspace:*"
  },
  "devDependencies": {
    "@vben/types": "workspace:*"
  }
}
""",
        encoding="utf-8",
    )


def test_auto_init_workspace_config_scans_server_and_client_dirs(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    _write_backend_project(workspace_root / "server")
    _write_vue3_project(workspace_root / "client" / "admin")
    _write_vben_project(workspace_root / "client" / "vben")

    config_file = auto_init_workspace_config(workspace_root)
    raw_config = yaml.safe_load(config_file.content or "")

    assert config_file.exists is True
    assert raw_config["projects"]["backend"]["path"] == "server"
    assert raw_config["projects"]["backend"]["type"] == "ruoyi-vue-pro-jdk17"
    assert raw_config["projects"]["frontend"] == [
        {"type": "VUE3_ELEMENT_PLUS", "path": "client/admin"},
        {"type": "VUE3_VBEN5_ANTD_SCHEMA", "path": "client/vben"},
        {"type": "VUE3_VBEN5_EP_SCHEMA", "path": "client/vben"},
    ]
    assert load_workspace_config(workspace_root).projects.backend.path == "server"


def test_load_workspace_config_tool_auto_initializes_and_stops_for_review(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    _write_backend_project(workspace_root)

    result = load_workspace_config_tool(str(workspace_root))

    assert result["ok"] is False
    assert result["error_code"] == "config_initialized"
    assert "已经自动初始化" in result["message"]
    assert result["data"]["should_stop"] is True
    assert result["data"]["next_action_prompt"]
    assert (workspace_root / ".yudao-pilot" / "config.yaml").exists()


def test_missing_config_in_regular_tools_auto_initializes_once(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    _write_vue3_project(workspace_root)

    result = validate_workspace_projects_tool(str(workspace_root))

    assert result["ok"] is False
    assert result["error_code"] == "config_initialized"
    assert result["data"]["initialized"] is True
    assert result["data"]["detected_projects"]["frontend"][0]["path"] == "."
    assert (workspace_root / ".yudao-pilot" / "config.yaml").exists()
