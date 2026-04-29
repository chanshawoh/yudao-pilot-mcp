from __future__ import annotations

from pathlib import Path

from yudao_pilot.inspector import (
    frontend_project_type_to_codegen_types,
    inspect_project_path,
)


def _write_backend_project(path: Path) -> Path:
    server = path / "yudao-server"
    server.mkdir(parents=True, exist_ok=True)
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
    <module>yudao-dependencies</module>
    <module>yudao-framework</module>
    <module>yudao-server</module>
    <module>yudao-module-system</module>
    <module>yudao-module-infra</module>
  </modules>
</project>
""",
        encoding="utf-8",
    )
    (server / "pom.xml").write_text(
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
    return path


def _write_vben_project(path: Path) -> Path:
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
    return path


def test_inspect_backend_project_by_fingerprint(tmp_path: Path) -> None:
    result = inspect_project_path(_write_backend_project(tmp_path / "ruoyi-vue-pro-jdk17"))
    assert result["exists"] is True
    assert result["best_match"]["detected_type"] == "ruoyi-vue-pro-jdk17"
    assert result["backend"]["supported"] is True


def test_inspect_frontend_vben_by_fingerprint(tmp_path: Path) -> None:
    result = inspect_project_path(_write_vben_project(tmp_path / "yudao-ui-admin-vben"))
    assert result["exists"] is True
    assert result["best_match"]["detected_type"] == "yudao-ui-admin-vben"
    assert result["frontend"]["supported"] is True


def test_vben_root_codegen_types_follow_existing_supported_apps(tmp_path: Path) -> None:
    root = _write_vben_project(tmp_path / "renamed-admin")
    (root / "apps" / "web-antd").mkdir(parents=True)
    (root / "apps" / "web-ele").mkdir(parents=True)
    (root / "apps" / "web-naive").mkdir(parents=True)
    (root / "apps" / "web-tdesign").mkdir(parents=True)

    assert frontend_project_type_to_codegen_types("yudao-ui-admin-vben", root) == [
        "VUE3_VBEN5_ANTD_SCHEMA",
        "VUE3_VBEN5_ANTD_GENERAL",
        "VUE3_VBEN5_EP_SCHEMA",
        "VUE3_VBEN5_EP_GENERAL",
    ]


def test_vben_child_app_codegen_types_are_app_local(tmp_path: Path) -> None:
    web_ele = _write_vben_project(tmp_path / "renamed-admin" / "apps" / "web-ele")

    assert frontend_project_type_to_codegen_types("yudao-ui-admin-vben", web_ele) == [
        "VUE3_VBEN5_EP_SCHEMA",
        "VUE3_VBEN5_EP_GENERAL",
    ]


def test_vben_unsupported_child_app_does_not_fallback_to_other_templates(
    tmp_path: Path,
) -> None:
    web_naive = _write_vben_project(tmp_path / "renamed-admin" / "apps" / "web-naive")

    assert frontend_project_type_to_codegen_types("yudao-ui-admin-vben", web_naive) == []


def test_inspect_backend_project_with_renamed_coordinates(tmp_path: Path) -> None:
    project = tmp_path / "safe-voyage"
    server = project / "safe-voyage-server"
    server.mkdir(parents=True)
    (project / "pom.xml").write_text(
        """<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.safe</groupId>
  <artifactId>safe-voyage-parent</artifactId>
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
    <module>yudao-dependencies</module>
    <module>yudao-framework</module>
    <module>safe-voyage-server</module>
    <module>yudao-module-system</module>
    <module>yudao-module-infra</module>
    <module>yudao-module-travel</module>
  </modules>
</project>
""",
        encoding="utf-8",
    )
    (server / "pom.xml").write_text(
        """<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.example.safe</groupId>
    <artifactId>safe-voyage-parent</artifactId>
  </parent>
  <artifactId>safe-voyage-server</artifactId>
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

    result = inspect_project_path(project)

    assert result["backend"]["supported"] is True
    assert result["backend"]["detected_type"] == "ruoyi-vue-pro-jdk17"
    assert not any(
        "根 pom 的 groupId/artifactId 为 cn.iocoder.boot:yudao" in item
        for item in result["backend"]["evidence"]
    )


def test_inspect_renamed_backend_server_module_from_child_path(tmp_path: Path) -> None:
    project = tmp_path / "safe-voyage"
    server = project / "safe-voyage-server"
    server.mkdir(parents=True)
    (project / "pom.xml").write_text(
        """<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.safe</groupId>
  <artifactId>safe-voyage-parent</artifactId>
  <packaging>pom</packaging>
  <properties>
    <java.version>17</java.version>
    <spring.boot.version>3.2.0</spring.boot.version>
  </properties>
  <modules>
    <module>yudao-framework</module>
    <module>safe-voyage-server</module>
    <module>yudao-module-system</module>
    <module>yudao-module-infra</module>
  </modules>
</project>
""",
        encoding="utf-8",
    )
    (server / "pom.xml").write_text(
        """<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.example.safe</groupId>
    <artifactId>safe-voyage-parent</artifactId>
  </parent>
  <artifactId>safe-voyage-server</artifactId>
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

    result = inspect_project_path(server)

    assert result["backend"]["supported"] is True
    assert result["backend"]["detected_type"] == "ruoyi-vue-pro-jdk17"
