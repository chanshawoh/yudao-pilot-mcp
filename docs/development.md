# Development and Testing / 开发与测试

[中文](#中文) | [English](#english)

## 中文

### 本地安装

```bash
uv venv
uv pip install -e '.[dev]'
```

或安装为 MCP 命令：

```bash
uv tool install .
```

安装后会提供：

```bash
yudao-pilot
```

### MCP 客户端配置

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "yudao-pilot",
      "args": []
    }
  }
}
```

### 测试

```bash
.venv/bin/pytest
```

重点测试覆盖：

- 项目类型识别
- 工作区配置初始化和校验
- 不可信工作区根目录保护
- 后端本地数据库配置解析
- MySQL 表结构解析
- 代码生成上下文构建
- 菜单 SQL、字典 SQL、H2 SQL 和菜单图标推断
- 后端和前端骨架代码生成
- 生成文件安全写入

### 本地联调约定

后端优先使用 Maven 打包后运行 jar：

```bash
cd yudao-projects/ruoyi-vue-pro-jdk17
mvn -pl yudao-server -am package
java -jar yudao-server/target/yudao-server.jar --spring.profiles.active=local
```

前端优先使用 `pnpm`：

```bash
cd yudao-projects/yudao-ui-admin-vue3
pnpm dev
```

### 目录结构

```text
yudao-pilot-mcp/
├── README.md
├── docs/
├── pyproject.toml
├── src/
│   └── yudao_pilot/
│       ├── server.py
│       ├── config.py
│       ├── inspector.py
│       ├── database.py
│       ├── codegen.py
│       └── writer.py
└── tests/
```

## English

### Local Install

```bash
uv venv
uv pip install -e '.[dev]'
```

Or install it as an MCP command:

```bash
uv tool install .
```

The installed command is:

```bash
yudao-pilot
```

### MCP Client Config

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "yudao-pilot",
      "args": []
    }
  }
}
```

### Tests

```bash
.venv/bin/pytest
```

Main coverage areas:

- Project type detection
- Workspace config initialization and validation
- Unsafe workspace root protection
- Backend local database config resolution
- MySQL table schema parsing
- Code-generation context building
- Menu SQL, dictionary SQL, H2 SQL, and menu icon inference
- Backend and frontend scaffold generation
- Safe generated file writing

### Local Integration Conventions

For backend integration, build with Maven and run the jar:

```bash
cd yudao-projects/ruoyi-vue-pro-jdk17
mvn -pl yudao-server -am package
java -jar yudao-server/target/yudao-server.jar --spring.profiles.active=local
```

For frontend integration, prefer `pnpm`:

```bash
cd yudao-projects/yudao-ui-admin-vue3
pnpm dev
```

### Project Layout

```text
yudao-pilot-mcp/
├── README.md
├── docs/
├── pyproject.toml
├── src/
│   └── yudao_pilot/
│       ├── server.py
│       ├── config.py
│       ├── inspector.py
│       ├── database.py
│       ├── codegen.py
│       └── writer.py
└── tests/
```
