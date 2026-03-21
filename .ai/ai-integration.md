# Yudao Pilot AI 应用接入协议

## 1. 目标

这份协议面向接入 Yudao Pilot MCP 的 AI 应用。

目标是让 AI 在生成 yudao 代码时，按统一顺序调用工具，避免误判目录、误写代码和生成错误菜单。

## 2. 推荐调用顺序

AI 应用默认按下面顺序工作：

1. 调用 `load_workspace_config`
2. 如果返回 `config_missing`，调用 `init_workspace_config`
3. 调用 `validate_workspace_projects`
4. 调用 `resolve_database_config`
5. 调用 `inspect_codegen_context` 或 `inspect_table_schema`
6. 如果需要先落 SQL，再调用 `generate_codegen_sql`
7. 如果需要生成首版代码骨架，再调用 `generate_codegen_scaffold`
8. 如果 AI 自己生成了代码文件，再调用 `write_generated_files`

## 3. 配置不存在时

当 `./.yudao-pilot/config.yaml` 不存在时，MCP 会返回配置模板。

AI 应用应该：

- 告诉用户当前目录还没有初始化 Yudao Pilot 配置
- 展示模板并引导用户确认后端、前端和手动路由规则
- 完成后再继续后续流程

## 4. 生成代码前的必要信息

生成一个业务表的代码时，AI 至少要明确这些信息：

- `table_name`
- `module_name`
- `business_name`
- `entity_name`

如果配置里的 `manual_rules` 能命中，MCP 会自动推导这些值。

如果是菜单或 SQL 场景，建议 AI 额外提供：

- `menu_name`
- `module_menu_name`

这两个名称都应该优先使用中文。

## 5. SQL 生成工具

工具名：`generate_codegen_sql`

用途：

- 生成 MySQL 菜单 SQL
- 生成并合并 H2 测试 SQL
- 幂等写入真实数据库菜单数据

关键参数：

- `table_name`
  - 必填，目标表名
- `workspace_root`
  - 可选，工作区根目录
- `module_name`
  - 可选，模块名；不传时按配置推导
- `business_name`
  - 可选，业务名；不传时按配置推导
- `entity_name`
  - 可选，实体名；不传时按配置推导
- `menu_name`
  - 可选，业务菜单中文名称；建议 AI 显式传入
- `module_menu_name`
  - 可选，模块根菜单中文名称；建议 AI 显式传入
- `menu_icon`
  - 可选，业务菜单图标；格式为 Iconify 字符串，例如 `ep:shop`
- `module_menu_icon`
  - 可选，模块根菜单图标；格式为 Iconify 字符串，例如 `ep:bicycle`
- `write_files`
  - 可选，是否把 SQL 文件真实写入仓库
- `overwrite`
  - 可选，是否允许覆盖迁移文件
- `apply_menu_to_database`
  - 可选，是否把菜单 SQL 幂等执行到真实数据库

## 6. 菜单图标约定

Yudao Pilot 的菜单图标直接写入后端 `system_menu.icon` 字段。

前端 VBen 菜单管理页使用的是 `Iconify` 字符串，所以 AI 应用传图标时必须使用这种格式，例如：

- `ep:shop`
- `ep:avatar`
- `ep:menu`
- `lucide:user`
- `ant-design:message-filled`

图标策略如下：

- 如果 AI 应用显式传了 `menu_icon` / `module_menu_icon`，优先使用传入值
- 如果没有传，MCP 会按模块和业务关键词自动推断
- 如果推断不到，就回退到模块默认图标

建议：

- 业务语义明确时，由 AI 应用直接传图标，效果最稳定
- 业务语义不明确时，可先使用 MCP 的自动推断结果

## 7. SQL 文件落点

MySQL 菜单迁移文件落到：

- `sql/mysql/migrations/`

命名规则采用 Laravel 风格时间戳。

H2 测试 SQL 合并到对应后端模块：

- `src/test/resources/sql/create_tables.sql`
- `src/test/resources/sql/clean.sql`

当前 SQL 生成只支持 MySQL 菜单写入逻辑。

## 8. 数据库执行策略

当 `apply_menu_to_database=true` 时，MCP 不会盲目执行整段 SQL，而是按菜单粒度幂等处理：

- 先检查模块根菜单是否存在
- 再检查业务菜单是否存在
- 再检查按钮权限是否存在

返回结果会区分：

- `created`
- `skipped`

所以 AI 应用可以安全地重复调用。

## 9. 推荐的图标传参方式

如果 AI 能理解业务语义，建议按下面规则主动传参：

- 用户、会员、账号类：`ep:avatar`
- 商家、店铺类：`ep:shop`
- 配置类：`fa:connectdevelop`
- 字典类：`ep:collection`
- 代码生成类：`ep:document-copy`
- 订单、交易类：`ep:tickets` 或 `ep:sold-out`

例如：

```json
{
  "table_name": "merchant_user",
  "module_menu_name": "会员中心",
  "menu_name": "商家用户",
  "menu_icon": "ep:avatar",
  "module_menu_icon": "ep:bicycle",
  "write_files": true,
  "apply_menu_to_database": true
}
```

## 10. 失败时的处理建议

如果 `generate_codegen_sql` 返回失败，AI 应用应优先检查：

- 配置文件是否存在
- 项目路径和类型是否校验通过
- 数据库是否可连接
- 目标表是否存在
- `module_name` / `business_name` / `entity_name` 是否推导正确

如果是菜单中文名或图标不合适，不必要求用户手改数据库，可直接带上新的 `menu_name`、`module_menu_name`、`menu_icon`、`module_menu_icon` 重新调用。
