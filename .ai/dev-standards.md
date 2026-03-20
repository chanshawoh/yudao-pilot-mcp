# Yudao Pilot 开发规范

## 1. 通用原则

- 项目默认使用中文文档、中文说明、中文任务记录
- 不依赖目录名识别项目类型，必须基于 `pom.xml` / `package.json` / 依赖指纹
- 不凭对话上下文猜测项目状态，必须以 `work.json` 为准
- 第一版优先完成可追溯、可继续、可测试的能力

## 2. 配置规范

- 唯一工作区配置入口：`./.yudao-pilot/config.yaml`
- 同一工作区只能配置一个后端项目
- 前端项目 `type` 不允许重复
- `database` 配置优先级：
  - `config.yaml` 中已填写字段优先
  - 留空字段才回退到后端本地环境配置
- 测试夹具配置位于 `tests/fixtures/dev-workspace/.yudao-pilot/config.yaml`
  - 它只用于测试，不作为实际运行时配置

## 3. 项目识别规范

- 后端支持：
  - `ruoyi-vue-pro`
  - `ruoyi-vue-pro-jdk17`
  - `yudao-cloud`
- 前端支持：
  - `yudao-ui-admin-vue3`
  - `yudao-ui-admin-vben`
  - `yudao-ui-admin-uniapp`
- 禁止仅根据目录名、包名判断项目类型

## 4. 表结构解析规范

- 默认先读取参考项目 SQL dump
- 如果 SQL dump 中没有目标表，再回退到真实数据库读取 `information_schema`
- 真实数据库连接必须来自已解析的工作区数据库配置
- 若连接失败或找不到表，返回明确原因，不静默吞掉

## 5. 代码生成规范

- 生成依赖三元组：
  - 模块名 `module`
  - 业务名 `business`
  - 实体名 `entity`
- 手动路由规则优先级：
  - `table_rules.table` 精确匹配
  - `table_prefixes` 最长前缀匹配
  - fallback
- 生成文件计划必须和目标项目真实结构一致

## 6. 后端落盘规范

- 后端只能写入已有模块，例如 `yudao-module-member/`
- 禁止生成伪造子模块目录，例如：
  - `yudao-module-member-server`
  - `yudao-module-member-api`
- 正确目标应保持 yudao 现有平铺结构：
  - `yudao-module-xxx/src/main/java/...`
  - `yudao-module-xxx/src/main/resources/...`
- 如果模块不存在，则拒绝写入
- 如果文件已存在且 `overwrite=false`，则跳过该文件

## 7. 错误码规范

- 生成阶段允许先产出 `ErrorCodeConstants_手动操作.java` 作为中间结果
- 写入阶段必须自动合并到真实 `ErrorCodeConstants.java`
- 若模块没有错误码范围，则自动维护：
  - `yudao-framework/yudao-common/.../ServiceErrorCodeRange.java`
- 错误码标题与提示语应优先使用更贴近业务的名称
  - 不优先使用数据库味太重的表注释后缀，如“表”“关联表”
- 合并完成后，不保留 `_手动操作.java`

## 8. 文档规范

- `README.md` 面向使用者
- `docs/product.md` 面向产品介绍
- `docs/roadmap.md` 面向路线图
- 文档示例不得写入本机特定路径或临时数据库名，除非明确是开发配置

## 9. 测试规范

- 修改核心逻辑后必须补或改测试
- 默认执行：
  - `./.venv/bin/python -m pytest`
- 当前测试覆盖重点：
  - 项目识别
  - MCP 工具
  - 写入器
  - 开发工作区夹具
  - 错误码合并

## 10. 变更规范

- 优先使用 `apply_patch` 修改文件
- 不回退用户已有改动
- 若发现之前生成到错误目录的测试产物，应先纠正逻辑，再做清理
- 任何真实写入前，应尽量先用 `overwrite=false` 做安全验证
