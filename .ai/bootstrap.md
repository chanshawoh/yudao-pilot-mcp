# Yudao Pilot 项目初始化与编排规范

## 1. 项目目标

Yudao Pilot 是一个面向 yudao 生态的 MCP 智能开发助手。

第一版目标：

- 识别当前工作区中的 yudao 后端与后台前端项目
- 读取 `./.yudao-pilot/config.yaml` 与后端本地配置，解析数据库连接
- 基于表名、模块名、业务名、实体名生成后端与前端骨架
- 将生成结果安全写入正确项目位置
- 在写入阶段自动处理错误码合并，而不是留下 `ErrorCodeConstants_手动操作.java`

第一版明确不做：

- 数据库副本 / 沙箱
- DDL / DML 同步合并
- 自动部署流水线
- 报错后自动修复闭环

## 2. 当前技术栈

- Python 3.11+
- FastMCP
- Pydantic v2
- PyYAML
- PyMySQL
- pytest

## 3. 当前目录约定

- 项目源码：`src/yudao_pilot/`
- 文档：`README.md`、`docs/product.md`、`docs/roadmap.md`
- 测试：`tests/`
- 工作区配置：`./.yudao-pilot/config.yaml`
- AI 协议：`./.ai/`
- yudao 参考项目：`./yudao-projects/`

## 4. 当前核心模块

- `server.py`
  - MCP 服务入口与工具注册
- `config.py`
  - 工作区配置模板、加载与校验
- `inspector.py`
  - 后端 / 前端指纹识别与项目校验
- `database.py`
  - 数据库配置解析，支持配置优先、后端本地配置回退
- `schema.py`
  - 优先读参考 SQL，缺失时回退到真实数据库表结构
- `codegen.py`
  - 代码生成上下文、文件计划、迁移计划
- `scaffold.py`
  - 首版后端 / 前端代码骨架渲染
- `writer.py`
  - 生成文件安全写入
- `error_codes.py`
  - 错误码范围查找、错误码常量合并、`ServiceErrorCodeRange.java` 维护

## 5. 启动顺序

每次接手项目时，默认按下面顺序理解现场：

1. 读取 `.ai/agent.md`
2. 读取本文件 `.ai/bootstrap.md`
3. 读取 `.ai/dev-standards.md`
4. 读取根目录 `work.json`
5. 再根据 `current_task_id` 执行当前任务

## 6. 联调基线

当前仓库里已经完成并验证的能力：

- 中文 README / 产品文档 / 路线图
- 根目录开发配置 `./.yudao-pilot/config.yaml`
- 参考项目指纹识别
- 工作区项目配置校验
- 数据库配置解析与配置优先逻辑
- 真实数据库表结构回退解析
- `merchant` / `merchant_user` 真实生成与真实写入验证
- 后端按原有模块平铺结构写入，不再伪造子模块目录
- 错误码写入自动合并进 `ErrorCodeConstants.java`

联调启动约定：

- 后端联调默认使用 Maven 打包，再使用 `java -jar` 启动产物
- 默认命令形态为先执行 `mvn -pl yudao-server -am package`，再执行 `java -jar yudao-server/target/yudao-server.jar --spring.profiles.active=local`
- 前端联调默认优先使用 `pnpm` 启动，不使用 `npm` / `yarn` 作为默认方案

## 7. 后端写入规则

后端最终目标不是“生成一套独立子模块”，而是：

- 找到已有模块，例如 `yudao-module-member/`
- 仅向该模块已有结构中的 `src/main` / `src/test` 补文件
- 如果目标模块不存在，则拒绝写入
- 如果目标文件已存在且 `overwrite=false`，则跳过
- 错误码文件必须并入 `ErrorCodeConstants.java`

## 8. 前端写入规则

- 仅支持后台前端：
  - `yudao-ui-admin-vue3`
  - `yudao-ui-admin-vben`
  - `yudao-ui-admin-uniapp`
- 不支持：
  - `yudao-ui-admin-vue2`
  - `yudao-mall-uniapp`
- 同一个工作区中，前端 `type` 不允许重复

## 9. 迁移文件规则

所有新 SQL 结构文件统一写入：

- `sql/mysql/migrations/`

文件名采用 Laravel 风格时间戳命名。

## 10. 当前执行原则

- 以根目录 `work.json` 为唯一事实源推进任务
- 一轮只推进一个 Task
- 代码、文档、配置、测试都算正式产物，必须可追溯
