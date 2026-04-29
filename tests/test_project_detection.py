from __future__ import annotations

from pathlib import Path

from yudao_pilot.inspector import inspect_project_path


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
