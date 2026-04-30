# 前端产物矩阵

本文档说明 Yudao Pilot 在一个工作区同时配置多个前端项目时，如何分别生成对应类型的前端产物。

## 目标

当 `./.yudao-pilot/config.yaml` 中配置了多个前端项目时：

- 不只生成一种前端代码
- 而是针对每一种已配置前端类型，分别生成一套对应的前端产物
- 所有前端产物都写入各自项目目录，不互相覆盖
- 同一个 `yudao-ui-admin-vben` 路径可以按不同枚举重复配置，分别生成 `web-antd` 与 `web-ele` 的产物

## 当前支持的前端类型

- `VUE3_ELEMENT_PLUS`
- `VUE3_VBEN5_ANTD_SCHEMA`
- `VUE3_VBEN5_ANTD_GENERAL`
- `VUE3_VBEN5_EP_SCHEMA`
- `VUE3_VBEN5_EP_GENERAL`
- `VUE3_ADMIN_UNIAPP_WOT`

## 生成规则

### Vue3 管理后台

目标类型：`VUE3_ELEMENT_PLUS`

生成产物：

- `src/views/{module}/{business}/index.vue`
- `src/views/{module}/{business}/{SimpleClassName}Form.vue`
- `src/api/{module}/{business}/index.ts`

### Vben 管理后台

目标类型：

- `VUE3_VBEN5_ANTD_SCHEMA`
- `VUE3_VBEN5_ANTD_GENERAL`
- `VUE3_VBEN5_EP_SCHEMA`
- `VUE3_VBEN5_EP_GENERAL`

路径映射：

- `VUE3_VBEN5_ANTD_SCHEMA`、`VUE3_VBEN5_ANTD_GENERAL` 对应 `apps/web-antd`
- `VUE3_VBEN5_EP_SCHEMA`、`VUE3_VBEN5_EP_GENERAL` 对应 `apps/web-ele`
- 当 MCP 只根据项目结构识别到这是一个 `yudao-ui-admin-vben` 项目，但还没有更细的模板信息时，内部默认按 `web-antd` 方向推导

生成产物：

- `apps/web-antd/src/views/{module}/{business}/data.ts`
- `apps/web-antd/src/views/{module}/{business}/index.vue`
- `apps/web-antd/src/views/{module}/{business}/modules/form.vue`
- `apps/web-antd/src/api/{module}/{business}/index.ts`
- `apps/web-ele/src/views/{module}/{business}/data.ts`
- `apps/web-ele/src/views/{module}/{business}/index.vue`
- `apps/web-ele/src/views/{module}/{business}/modules/form.vue`
- `apps/web-ele/src/api/{module}/{business}/index.ts`

### Uniapp 后台

目标类型：`VUE3_ADMIN_UNIAPP_WOT`

生成产物：

- `src/api/{module}/{business}/index.ts`
- `src/pages-{module}/{business}/index.vue`
- `src/pages-{module}/{business}/components/search-form.vue`
- `src/pages-{module}/{business}/form/index.vue`
- `src/pages-{module}/{business}/detail/index.vue`

## 当前联调结果

以 `merchant` 表为例，在测试夹具工作区中同时配置 3 个前端项目时，当前生成结果如下：

- `ruoyi-vue-pro-jdk17`：10 个后端文件
- `VUE3_ELEMENT_PLUS`：3 个前端文件
- `VUE3_VBEN5_ANTD_SCHEMA`：4 个前端文件
- `VUE3_ADMIN_UNIAPP_WOT`：5 个前端文件

说明：

- 配置多个前端类型，MCP 会多次产出不同前端类型的文件
- 不是“只选一个前端模板”
- 最终写入时，按每个 `frontend.type` 对应的项目路径分别落盘

## 落盘约束

- `projects.frontend` 中 `type` 不能重复
- 同一个 `path` 可以出现多次，但每次必须对应不同的前端枚举
- 只有配置中的前端项目才会参与生成
- 文件已存在且 `overwrite=false` 时，跳过该文件
- 生成计划与真实落盘都按前端项目类型分别执行

---

# Frontend Output Matrix

This document explains how Yudao Pilot generates frontend artifacts when multiple frontend projects are configured in one workspace.

## Goal

When `.yudao-pilot/config.yaml` contains multiple frontend targets:

- MCP generates artifacts for every configured frontend type
- It does not silently choose only one frontend template
- Each artifact is written to the project path configured for its frontend type
- A single `yudao-ui-admin-vben` path can be reused for different enum values, so `web-antd` and `web-ele` can both be generated

## Supported Frontend Types

- `VUE3_ELEMENT_PLUS`
- `VUE3_VBEN5_ANTD_SCHEMA`
- `VUE3_VBEN5_ANTD_GENERAL`
- `VUE3_VBEN5_EP_SCHEMA`
- `VUE3_VBEN5_EP_GENERAL`
- `VUE3_ADMIN_UNIAPP_WOT`

## Vue3 Admin

Target type: `VUE3_ELEMENT_PLUS`

Generated artifacts:

- `src/views/{module}/{business}/index.vue`
- `src/views/{module}/{business}/{SimpleClassName}Form.vue`
- `src/api/{module}/{business}/index.ts`

## Vben Admin

Target types:

- `VUE3_VBEN5_ANTD_SCHEMA`
- `VUE3_VBEN5_ANTD_GENERAL`
- `VUE3_VBEN5_EP_SCHEMA`
- `VUE3_VBEN5_EP_GENERAL`

Path mapping:

- `VUE3_VBEN5_ANTD_SCHEMA` and `VUE3_VBEN5_ANTD_GENERAL` map to `apps/web-antd`
- `VUE3_VBEN5_EP_SCHEMA` and `VUE3_VBEN5_EP_GENERAL` map to `apps/web-ele`

Generated artifacts:

- `apps/web-antd/src/views/{module}/{business}/data.ts`
- `apps/web-antd/src/views/{module}/{business}/index.vue`
- `apps/web-antd/src/views/{module}/{business}/modules/form.vue`
- `apps/web-antd/src/api/{module}/{business}/index.ts`
- `apps/web-ele/src/views/{module}/{business}/data.ts`
- `apps/web-ele/src/views/{module}/{business}/index.vue`
- `apps/web-ele/src/views/{module}/{business}/modules/form.vue`
- `apps/web-ele/src/api/{module}/{business}/index.ts`

## Uniapp Admin

Target type: `VUE3_ADMIN_UNIAPP_WOT`

Generated artifacts:

- `src/api/{module}/{business}/index.ts`
- `src/pages-{module}/{business}/index.vue`
- `src/pages-{module}/{business}/components/search-form.vue`
- `src/pages-{module}/{business}/form/index.vue`
- `src/pages-{module}/{business}/detail/index.vue`

## Write Constraints

- `projects.frontend[].type` must be unique
- The same `path` may appear more than once only when each entry uses a different frontend enum
- Only configured frontend projects participate in generation
- Existing files are skipped when `overwrite=false`
- Planning and writing are both executed per frontend type
