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
请安装并配置 yudao-pilot-mcp。不要克隆源码仓库，除非用户明确要参与开发。

1. 确认 Python 版本不低于 3.11。
2. 优先执行 pipx install yudao-pilot-mcp，将 MCP Server 安装为隔离的命令行工具。
3. 如果没有 pipx 但有 uv，执行 uv tool install yudao-pilot-mcp。
4. 如果两者都没有，创建 Python 虚拟环境并执行 python -m pip install yudao-pilot-mcp。
5. 如果当前包镜像找不到该包，使用 --index-url https://pypi.org/simple/ 从官方 PyPI 安装。
6. 验证 yudao-pilot 命令存在。不要把 stdio MCP Server 持续运行在测试终端中。
7. 在用户的 MCP 客户端配置中注册 command=yudao-pilot、args=[]。
8. 如果 MCP 客户端读取不到 PATH，使用虚拟环境 Python 的绝对路径，并配置 args=["-m", "yudao_pilot.server"]。
9. 配置完成后提醒用户重启或重新加载 MCP 客户端。

安装后的业务操作方式以 yudao-pilot-mcp Skill 为准，不要在安装阶段自行执行代码生成或数据库写入。
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
Install and configure yudao-pilot-mcp. Do not clone the source repository unless the user explicitly wants a development checkout.

1. Confirm that Python 3.11 or newer is available.
2. Prefer pipx install yudao-pilot-mcp to install the MCP server as an isolated CLI application.
3. If pipx is unavailable but uv is installed, run uv tool install yudao-pilot-mcp.
4. If neither tool is available, create a Python virtual environment and run python -m pip install yudao-pilot-mcp.
5. If the configured package mirror cannot find the package, install from the official index with --index-url https://pypi.org/simple/.
6. Verify that the yudao-pilot command exists. Do not leave the stdio MCP server running in the verification terminal.
7. Register the server in the user's MCP client with command=yudao-pilot and args=[].
8. If the MCP client cannot see the command on PATH, use the absolute path to the virtual-environment Python and set args=["-m", "yudao_pilot.server"].
9. Ask the user to restart or reload the MCP client after saving the configuration.

After installation, follow the yudao-pilot-mcp Skill for business operations. Do not start code generation or database writes during installation.
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
