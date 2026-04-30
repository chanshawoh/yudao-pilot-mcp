# Yudao Pilot MCP

[中文](#中文) | [English](#english)

## 中文

Yudao Pilot MCP 是面向 yudao / ruoyi-vue-pro 生态的工作区感知型 MCP 服务。它帮助 AI 编码工具识别本地后端、前端、数据库和代码生成目标，让 AI 生成的代码准确落到正确项目结构里。

### 核心价值

- 让 AI 不再猜 yudao 项目目录和生成位置
- 用 `.yudao-pilot/config.yaml` 固化后端、前端和数据库配置
- 基于项目指纹校验路径，避免代码写错仓库或模块
- 生成菜单、字典、H2 测试 SQL 和前后端骨架代码
- 当工作目录不明确时停止初始化，并要求 AI 先询问真实项目目录

### 快速使用

1. 安装命令行入口。

```bash
git clone https://github.com/woodynew/yudao-pilot-mcp.git
cd yudao-pilot-mcp
uv tool install .
```

2. 在 MCP 客户端中注册服务。

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

3. 在你的 yudao 工作区中让 AI 先调用 `load_workspace_config`。首次使用会生成 `.yudao-pilot/config.yaml`，并要求确认识别到的后端和前端路径。

4. 确认配置后，典型流程是：

```text
load_workspace_config
validate_workspace_projects
inspect_codegen_context
generate_codegen_scaffold
generate_codegen_sql
```

### 文档

- [项目概览](docs/overview.md)
- [配置指南](docs/configuration.md)
- [MCP 工具与工作流](docs/tools.md)
- [SQL、菜单与字典生成](docs/sql-codegen.md)
- [开发与测试](docs/development.md)
- [前端产物矩阵](docs/frontend-output-matrix.md)
- [产品说明](docs/product.md)
- [路线图](docs/roadmap.md)

## English

Yudao Pilot MCP is a workspace-aware MCP server for the yudao / ruoyi-vue-pro ecosystem. It helps AI coding tools understand local backend projects, frontend targets, database configuration, and code-generation routes so generated code lands in the right place.

### Core Value

- Stop AI tools from guessing yudao project paths
- Use `.yudao-pilot/config.yaml` as the routing source of truth
- Validate backend and frontend paths with project fingerprints
- Generate menu SQL, dictionary SQL, H2 test SQL, and backend/frontend scaffolds
- Refuse unsafe initialization when the project workspace is unknown

### Quick Start

1. Install the command.

```bash
git clone https://github.com/woodynew/yudao-pilot-mcp.git
cd yudao-pilot-mcp
uv tool install .
```

2. Register the MCP server in your client.

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

3. Ask the AI client to call `load_workspace_config` from your yudao workspace. On first use, Yudao Pilot creates `.yudao-pilot/config.yaml` and asks the AI to confirm detected backend and frontend paths.

4. After configuration is confirmed, the common flow is:

```text
load_workspace_config
validate_workspace_projects
inspect_codegen_context
generate_codegen_scaffold
generate_codegen_sql
```

### Documentation

- [Overview](docs/overview.md)
- [Configuration](docs/configuration.md)
- [MCP Tools and Workflow](docs/tools.md)
- [SQL, Menu, and Dictionary Generation](docs/sql-codegen.md)
- [Development and Testing](docs/development.md)
- [Frontend Output Matrix](docs/frontend-output-matrix.md)
- [Product Notes](docs/product.md)
- [Roadmap](docs/roadmap.md)
