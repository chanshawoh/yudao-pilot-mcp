# Yudao Pilot MCP

[中文](#中文) | [English](#english)

## 中文

Yudao Pilot MCP 是面向 yudao / ruoyi-vue-pro 生态的工作区感知型 MCP 服务。它帮助 AI 编码工具识别本地后端、前端、数据库和代码生成目标，让 AI 生成的代码准确落到正确项目结构里。

### 严肃声明

`yudao`、`ruoyi-vue-pro` 生态与 `ruoyi` / `RuoYi` / 若依原生生态不是同一个项目。当前 MCP 只支持 `yudao`、`ruoyi-vue-pro`、`ruoyi-vue-pro-jdk17`、`yudao-cloud` 相关项目，不支持若依原生生态项目。

### 核心价值

- 让 AI 不再猜 yudao 项目目录和生成位置
- 用 `.yudao-pilot/config.yaml` 固化后端、前端和数据库配置
- 基于项目指纹校验路径，避免代码写错仓库或模块
- 生成菜单、字典、H2 测试 SQL 和前后端骨架代码
- 当工作目录不明确时停止初始化，并要求 AI 先询问真实项目目录

### 安装

项目提供 `yudao-pilot` 命令入口，适合通过 pipx 或 uv 作为隔离的命令行工具安装。

推荐使用 pipx：

```bash
pipx install yudao-pilot-mcp
pipx ensurepath
```

也可以使用 uv：

```bash
uv tool install yudao-pilot-mcp
```

没有 pipx 或 uv 时，使用标准虚拟环境和 pip：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install yudao-pilot-mcp
```

Windows 使用 `.venv\Scripts\activate` 激活虚拟环境。如果当前 PyPI 镜像尚未同步新版本，显式使用官方索引：

```bash
python -m pip install --index-url https://pypi.org/simple/ yudao-pilot-mcp
```

从源码安装仅用于开发：

```bash
git clone https://github.com/chanshawoh/yudao-pilot-mcp.git
cd yudao-pilot-mcp
python -m pip install -e ".[dev]"
```

### 配置 MCP 客户端

通过 pipx、uv tool 或 PATH 中的 pip 环境安装后：

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

如果使用项目内虚拟环境，或 MCP 客户端读取不到 shell 的 PATH：

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "yudao_pilot.server"]
    }
  }
}
```

Windows 将 `command` 改为 `.venv\\Scripts\\python.exe` 的绝对路径。临时试用也可以让 pipx 自动创建缓存环境：

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "pipx",
      "args": ["run", "--spec", "yudao-pilot-mcp", "yudao-pilot"]
    }
  }
}
```

长期使用推荐先执行 `pipx install`，避免 MCP 首次启动时等待下载依赖。

### 使用

在你的 yudao 工作区中让 AI 先调用 `load_workspace_config`。首次使用会生成 `.yudao-pilot/config.yaml`，并要求确认识别到的后端和前端路径。

确认配置后，典型流程是：

```text
load_workspace_config
validate_workspace_projects
inspect_codegen_context
generate_codegen_scaffold(write_files=true)
```

如果用户明确要求“先预览”，则调用：

```text
generate_codegen_scaffold(write_files=false)
```

此时预览产物会写入 `.yudao-pilot/previews/` 下的临时目录，不会影响项目现有代码。

### 给 AI Agent 的说明

将下面的要求交给使用该 MCP 的 AI Agent：

```text
这是 yudao / ruoyi-vue-pro 项目，不是原生 RuoYi 项目。涉及根据数据库表生成代码时，必须使用 yudao-pilot MCP。

1. 先调用 load_workspace_config，再调用 validate_workspace_projects。
2. 如果返回 config_initialized，暂停生成，让用户确认 .yudao-pilot/config.yaml 中识别到的项目路径。
3. 生成前调用 resolve_database_config 和 inspect_codegen_context(table_name)，并确认真实数据库中存在目标表。
4. 用户未明确要求预览时，调用 generate_codegen_scaffold(table_name, write_files=true)；只有用户明确说“先预览”时才使用 write_files=false。
5. 不要擅自修改 apply_to_database、SQL mode、routing 或 manual_rules。
6. 普通目标文件已存在时不要覆盖；把 MCP 返回的 next_action_prompt 交给用户确认。
7. 后端和前端写入路径只使用 MCP 返回的 codegen_target、frontend_targets 和 generated_file_plan，不根据目录名猜测。
```

### 开源协议

本项目采用 [MIT License](LICENSE)。你可以自由使用、复制、修改、合并、发布和分发本项目，但必须保留原始版权和许可声明。软件按“原样”提供，不附带任何明示或默示担保。

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

### Important Notice

The `yudao` / `ruoyi-vue-pro` ecosystem is not the same project as the original `ruoyi` / `RuoYi` ecosystem. This MCP currently supports `yudao`, `ruoyi-vue-pro`, `ruoyi-vue-pro-jdk17`, and `yudao-cloud` projects only. It does not support original RuoYi projects.

### Core Value

- Stop AI tools from guessing yudao project paths
- Use `.yudao-pilot/config.yaml` as the routing source of truth
- Validate backend and frontend paths with project fingerprints
- Generate menu SQL, dictionary SQL, H2 test SQL, and backend/frontend scaffolds
- Refuse unsafe initialization when the project workspace is unknown

### Installation

The package exposes a `yudao-pilot` command and is well suited to isolated CLI installation with pipx or uv.

Recommended with pipx:

```bash
pipx install yudao-pilot-mcp
pipx ensurepath
```

With uv:

```bash
uv tool install yudao-pilot-mcp
```

Without pipx or uv, use a standard virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install yudao-pilot-mcp
```

On Windows, activate with `.venv\Scripts\activate`. If your configured package mirror has not synchronized the release yet, use the official PyPI index:

```bash
python -m pip install --index-url https://pypi.org/simple/ yudao-pilot-mcp
```

Install from source only for development:

```bash
git clone https://github.com/chanshawoh/yudao-pilot-mcp.git
cd yudao-pilot-mcp
python -m pip install -e ".[dev]"
```

### MCP Client Configuration

After installing with pipx, uv tool, or a pip environment available on PATH:

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

When using a project virtual environment, or when the MCP client cannot see your shell PATH:

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "yudao_pilot.server"]
    }
  }
}
```

On Windows, set `command` to the absolute path of `.venv\\Scripts\\python.exe`. For temporary use, pipx can create a cached environment automatically:

```json
{
  "mcpServers": {
    "yudao-pilot": {
      "command": "pipx",
      "args": ["run", "--spec", "yudao-pilot-mcp", "yudao-pilot"]
    }
  }
}
```

For regular use, run `pipx install` first to avoid dependency downloads during the first MCP startup.

### Usage

Ask the AI client to call `load_workspace_config` from your yudao workspace. On first use, Yudao Pilot creates `.yudao-pilot/config.yaml` and asks the AI to confirm detected backend and frontend paths.

After configuration is confirmed, the common flow is:

```text
load_workspace_config
validate_workspace_projects
inspect_codegen_context
generate_codegen_scaffold(write_files=true)
```

If the user explicitly asks to preview first, call:

```text
generate_codegen_scaffold(write_files=false)
```

Preview artifacts are written under `.yudao-pilot/previews/` and do not touch the existing project code.

### Instructions for AI Agents

Give the following requirements to the AI Agent using this MCP server:

```text
This is a yudao / ruoyi-vue-pro project, not an original RuoYi project. For database-table-based code generation, use the yudao-pilot MCP server.

1. Call load_workspace_config first, then validate_workspace_projects.
2. If config_initialized is returned, stop generation and ask the user to confirm the detected paths in .yudao-pilot/config.yaml.
3. Before generation, call resolve_database_config and inspect_codegen_context(table_name), and require the target table to exist in the real database.
4. Unless the user explicitly asks for a preview, call generate_codegen_scaffold(table_name, write_files=true). Use write_files=false only for an explicit preview request.
5. Do not silently change apply_to_database, SQL modes, routing, or manual_rules.
6. Do not overwrite normal generated files when they already exist. Present the MCP next_action_prompt to the user.
7. Use only the codegen_target, frontend_targets, and generated_file_plan returned by the MCP server; do not guess output paths from directory names.
```

### License

This project is released under the [MIT License](LICENSE). You may use, copy, modify, merge, publish, and distribute it provided that the original copyright and permission notice are retained. The software is provided “as is”, without warranty of any kind.

### Documentation

- [Overview](docs/overview.md)
- [Configuration](docs/configuration.md)
- [MCP Tools and Workflow](docs/tools.md)
- [SQL, Menu, and Dictionary Generation](docs/sql-codegen.md)
- [Development and Testing](docs/development.md)
- [Frontend Output Matrix](docs/frontend-output-matrix.md)
- [Product Notes](docs/product.md)
- [Roadmap](docs/roadmap.md)
