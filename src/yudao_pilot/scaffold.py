from __future__ import annotations

import re
from textwrap import dedent
from typing import Any

from .models import GeneratedFile


def generate_scaffold_files(
    context: dict[str, Any],
    *,
    overwrite: bool = True,
    include_backend: bool = True,
    include_frontend: bool = True,
) -> list[GeneratedFile]:
    files: list[GeneratedFile] = []
    backend_project = context["backend_project"]
    backend_plan = context["generated_file_plan"]["backend"]
    if include_backend:
        for relative_path in backend_plan:
            files.append(
                GeneratedFile(
                    target_kind="backend",
                    target_type=backend_project["type"],
                    relative_path=relative_path,
                    content=render_backend_file(relative_path, context),
                    overwrite=overwrite,
                )
            )

    if include_frontend:
        for frontend_plan in context["generated_file_plan"]["frontends"]:
            for relative_path in frontend_plan["relative_paths"]:
                files.append(
                    GeneratedFile(
                        target_kind="frontend",
                        target_type=frontend_plan["project_type"],
                        relative_path=relative_path,
                        content=render_frontend_file(relative_path, frontend_plan, context),
                        overwrite=overwrite,
                    )
                )
    return files


def render_backend_file(relative_path: str, context: dict[str, Any]) -> str:
    if relative_path.endswith("PageReqVO.java"):
        return render_page_req_vo(relative_path, context)
    if relative_path.endswith("RespVO.java"):
        return render_resp_vo(relative_path, context)
    if relative_path.endswith("SaveReqVO.java"):
        return render_save_req_vo(relative_path, context)
    if relative_path.endswith("Controller.java"):
        return render_controller(relative_path, context)
    if relative_path.endswith("DO.java"):
        return render_data_object(relative_path, context)
    if relative_path.endswith("Mapper.java"):
        return render_mapper(relative_path, context)
    if relative_path.endswith("Mapper.xml"):
        return render_mapper_xml(context)
    if relative_path.endswith("ServiceImpl.java"):
        return render_service_impl(relative_path, context)
    if relative_path.endswith("Service.java"):
        return render_service(relative_path, context)
    if relative_path.endswith("ServiceImplTest.java"):
        return render_service_test(relative_path, context)
    if relative_path.endswith("ErrorCodeConstants_手动操作.java"):
        return render_error_code_constants(relative_path, context)
    return render_plain_placeholder(relative_path, context)


def render_frontend_file(
    relative_path: str, frontend_plan: dict[str, Any], context: dict[str, Any]
) -> str:
    if relative_path.endswith("/index.ts"):
        return render_frontend_api(relative_path, frontend_plan, context)
    if relative_path.endswith("/index.vue"):
        return render_frontend_index(relative_path, frontend_plan, context)
    if relative_path.endswith("Form.vue"):
        return render_vue3_form(relative_path, context)
    if relative_path.endswith("/modules/form.vue"):
        return render_vben_form(relative_path, frontend_plan, context)
    if relative_path.endswith("/data.ts"):
        return render_vben_data(relative_path, frontend_plan, context)
    if relative_path.endswith("/components/search-form.vue"):
        return render_uniapp_search_form(relative_path, context)
    if relative_path.endswith("/form/index.vue"):
        return render_uniapp_form(relative_path, context)
    if relative_path.endswith("/detail/index.vue"):
        return render_uniapp_detail(relative_path, context)
    return render_plain_placeholder(relative_path, context)


def render_page_req_vo(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    query_fields = get_query_fields(context)
    imports = render_java_import_block(
        context["backend_codegen_defaults"]["base_package"] + ".framework.common.pojo.PageParam",
        *collect_java_type_imports(query_fields),
    )
    field_lines = "\n\n".join(render_page_query_field(field) for field in query_fields) or (
        '    @Schema(description = "关键字，建议后续由 AI 根据字段补齐")\n'
        '    private String keyword;'
    )
    return dedent(
        f"""\
package {package_name};

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;
{imports}

@Schema(description = "管理后台 - {class_name}分页 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class {class_name}PageReqVO extends PageParam {{

{field_lines}
}}
"""
    ).strip() + "\n"


def render_resp_vo(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    resp_fields = get_resp_fields(context)
    imports = render_java_import_block(*collect_java_type_imports(resp_fields))
    field_lines = "\n\n".join(render_java_field(field) for field in resp_fields)
    return dedent(
        f"""\
package {package_name};

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
{imports}

@Schema(description = "管理后台 - {class_name} Response VO")
@Data
public class {class_name}RespVO {{

{field_lines}
}}
"""
    ).strip() + "\n"


def render_save_req_vo(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    validation_package = resolve_validation_package(context["backend_project"]["type"])
    save_fields = get_save_fields(context)
    imports = render_java_import_block(
        f"{validation_package}.constraints.NotNull",
        *collect_save_vo_imports(save_fields, validation_package),
        *collect_java_type_imports(save_fields),
    )
    field_lines = "\n\n".join(render_save_vo_field(field) for field in save_fields) or (
        '    @Schema(description = "备注")\n'
        '    private String remark;'
    )
    return dedent(
        f"""\
package {package_name};

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
{imports}

@Schema(description = "管理后台 - {class_name}新增/修改 Request VO")
@Data
public class {class_name}SaveReqVO {{

    @Schema(description = "编号", example = "1")
    @NotNull(message = "编号不能为空", groups = Update.class)
    private Long id;

{field_lines}

    public interface Update {{}}
}}
"""
    ).strip() + "\n"


def render_controller(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    business_name = context["business_name"]
    module_name = context["module_name"]
    table_name = context["table_name"]
    url_path = table_name.replace("_", "-")
    resource_package = resolve_resource_package(context["backend_project"]["type"])
    validation_package = resolve_validation_package(context["backend_project"]["type"])
    base_package = context["backend_codegen_defaults"]["base_package"]
    return dedent(
        f"""\
        package {package_name};

        import {base_package}.framework.common.pojo.CommonResult;
        import {base_package}.framework.common.pojo.PageResult;
        import {base_package}.framework.common.util.object.BeanUtils;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}PageReqVO;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}RespVO;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}SaveReqVO;
        import {base_package}.module.{module_name}.dal.dataobject.{business_name}.{class_name}DO;
        import {base_package}.module.{module_name}.service.{business_name}.{class_name}Service;
        import {resource_package}.Resource;
        import {validation_package}.Valid;
        import org.springframework.validation.annotation.Validated;
        import org.springframework.web.bind.annotation.*;

        import static {base_package}.framework.common.pojo.CommonResult.success;

        @RestController
        @RequestMapping("/{module_name}/{url_path}")
        @Validated
        public class {class_name}Controller {{

            @Resource
            private {class_name}Service {lower_camel(class_name)}Service;

            @PostMapping("/create")
            public CommonResult<Long> create{class_name}(@Valid @RequestBody {class_name}SaveReqVO createReqVO) {{
                return success({lower_camel(class_name)}Service.create{class_name}(createReqVO));
            }}

            @PutMapping("/update")
            public CommonResult<Boolean> update{class_name}(@Valid @RequestBody {class_name}SaveReqVO updateReqVO) {{
                {lower_camel(class_name)}Service.update{class_name}(updateReqVO);
                return success(true);
            }}

            @DeleteMapping("/delete")
            public CommonResult<Boolean> delete{class_name}(@RequestParam("id") Long id) {{
                {lower_camel(class_name)}Service.delete{class_name}(id);
                return success(true);
            }}

            @GetMapping("/get")
            public CommonResult<{class_name}RespVO> get{class_name}(@RequestParam("id") Long id) {{
                {class_name}DO {lower_camel(class_name)} = {lower_camel(class_name)}Service.get{class_name}(id);
                return success(BeanUtils.toBean({lower_camel(class_name)}, {class_name}RespVO.class));
            }}

            @GetMapping("/page")
            public CommonResult<PageResult<{class_name}RespVO>> get{class_name}Page(@Valid {class_name}PageReqVO pageReqVO) {{
                PageResult<{class_name}DO> pageResult = {lower_camel(class_name)}Service.get{class_name}Page(pageReqVO);
                return success(BeanUtils.toBean(pageResult, {class_name}RespVO.class));
            }}
        }}
        """
    )


def render_data_object(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    table_name = context["table_name"]
    base_package = context["backend_codegen_defaults"]["base_package"]
    do_fields = get_do_fields(context)
    imports = render_java_import_block(
        *collect_java_type_imports(do_fields),
        f"{base_package}.framework.mybatis.core.dataobject.BaseDO",
    )
    field_lines = "\n\n".join(render_java_field(field) for field in do_fields)
    return dedent(
        f"""\
package {package_name};

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;
{imports}

@TableName("{table_name}")
@Data
@EqualsAndHashCode(callSuper = true)
public class {class_name}DO extends BaseDO {{

{field_lines}
}}
"""
    ).strip() + "\n"


def render_mapper(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    module_name = context["module_name"]
    business_name = context["business_name"]
    base_package = context["backend_codegen_defaults"]["base_package"]
    query_fields = get_query_fields(context)
    query_lines = render_mapper_query_lines(class_name, query_fields)
    return dedent(
        f"""\
        package {package_name};

        import {base_package}.framework.common.pojo.PageResult;
        import {base_package}.framework.mybatis.core.mapper.BaseMapperX;
        import {base_package}.framework.mybatis.core.query.LambdaQueryWrapperX;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}PageReqVO;
        import {base_package}.module.{module_name}.dal.dataobject.{business_name}.{class_name}DO;
        import org.apache.ibatis.annotations.Mapper;

        @Mapper
        public interface {class_name}Mapper extends BaseMapperX<{class_name}DO> {{

            default PageResult<{class_name}DO> selectPage({class_name}PageReqVO reqVO) {{
                return selectPage(reqVO, new LambdaQueryWrapperX<{class_name}DO>()
        {query_lines}
                        .orderByDesc({class_name}DO::getId));
            }}
        }}
        """
    )


def render_mapper_xml(context: dict[str, Any]) -> str:
    base_package = context["backend_codegen_defaults"]["base_package"]
    module_name = context["module_name"]
    business_name = context["business_name"]
    class_name = context["entity_name"]
    return dedent(
        f"""\
        <?xml version="1.0" encoding="UTF-8" ?>
        <!DOCTYPE mapper
                PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
                "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
        <mapper namespace="{base_package}.module.{module_name}.dal.mysql.{business_name}.{class_name}Mapper">

        </mapper>
        """
    )


def render_service(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    module_name = context["module_name"]
    business_name = context["business_name"]
    base_package = context["backend_codegen_defaults"]["base_package"]
    validation_package = resolve_validation_package(context["backend_project"]["type"])
    return dedent(
        f"""\
        package {package_name};

        import {base_package}.framework.common.pojo.PageResult;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}PageReqVO;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}SaveReqVO;
        import {base_package}.module.{module_name}.dal.dataobject.{business_name}.{class_name}DO;
        import {validation_package}.Valid;

        public interface {class_name}Service {{

            Long create{class_name}(@Valid {class_name}SaveReqVO createReqVO);

            void update{class_name}(@Valid {class_name}SaveReqVO updateReqVO);

            void delete{class_name}(Long id);

            {class_name}DO get{class_name}(Long id);

            PageResult<{class_name}DO> get{class_name}Page({class_name}PageReqVO pageReqVO);
        }}
        """
    )


def render_service_impl(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    module_name = context["module_name"]
    business_name = context["business_name"]
    base_package = context["backend_codegen_defaults"]["base_package"]
    resource_package = resolve_resource_package(context["backend_project"]["type"])
    error_const = upper_snake(class_name) + "_NOT_EXISTS"
    return dedent(
        f"""\
        package {package_name};

        import {base_package}.framework.common.pojo.PageResult;
        import {base_package}.framework.common.util.object.BeanUtils;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}PageReqVO;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}SaveReqVO;
        import {base_package}.module.{module_name}.dal.dataobject.{business_name}.{class_name}DO;
        import {base_package}.module.{module_name}.dal.mysql.{business_name}.{class_name}Mapper;
        import {resource_package}.Resource;
        import org.springframework.stereotype.Service;
        import org.springframework.validation.annotation.Validated;

        import static {base_package}.framework.common.exception.util.ServiceExceptionUtil.exception;
        import static {base_package}.module.{module_name}.enums.ErrorCodeConstants.{error_const};

        @Service
        @Validated
        public class {class_name}ServiceImpl implements {class_name}Service {{

            @Resource
            private {class_name}Mapper {lower_camel(class_name)}Mapper;

            @Override
            public Long create{class_name}({class_name}SaveReqVO createReqVO) {{
                {class_name}DO {lower_camel(class_name)} = BeanUtils.toBean(createReqVO, {class_name}DO.class);
                {lower_camel(class_name)}Mapper.insert({lower_camel(class_name)});
                return {lower_camel(class_name)}.getId();
            }}

            @Override
            public void update{class_name}({class_name}SaveReqVO updateReqVO) {{
                validate{class_name}Exists(updateReqVO.getId());
                {class_name}DO updateObj = BeanUtils.toBean(updateReqVO, {class_name}DO.class);
                {lower_camel(class_name)}Mapper.updateById(updateObj);
            }}

            @Override
            public void delete{class_name}(Long id) {{
                validate{class_name}Exists(id);
                {lower_camel(class_name)}Mapper.deleteById(id);
            }}

            private void validate{class_name}Exists(Long id) {{
                if ({lower_camel(class_name)}Mapper.selectById(id) == null) {{
                    throw exception({error_const});
                }}
            }}

            @Override
            public {class_name}DO get{class_name}(Long id) {{
                return {lower_camel(class_name)}Mapper.selectById(id);
            }}

            @Override
            public PageResult<{class_name}DO> get{class_name}Page({class_name}PageReqVO pageReqVO) {{
                return {lower_camel(class_name)}Mapper.selectPage(pageReqVO);
            }}
        }}
        """
    )


def render_service_test(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    return dedent(
        f"""\
        package {package_name};

        import org.junit.jupiter.api.Disabled;
        import org.junit.jupiter.api.Test;

        @Disabled("TODO Yudao Pilot: 字段级生成完成后补齐 Service 单测")
        class {class_name}ServiceImplTest {{

            @Test
            void placeholder() {{
            }}
        }}
        """
    )


def render_error_code_constants(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    base_package = context["backend_codegen_defaults"]["base_package"]
    entity_name = upper_snake(context["entity_name"])
    section_title = resolve_error_code_section_title(context)
    return dedent(
        f"""\
        package {package_name};

        import {base_package}.framework.common.exception.ErrorCode;

        // Yudao Pilot Section: {section_title}
        public interface ErrorCodeConstants_手动操作 {{

            ErrorCode {entity_name}_NOT_EXISTS = new ErrorCode(0, "{section_title}不存在");
        }}
        """
    )


def render_frontend_api(
    relative_path: str, frontend_plan: dict[str, Any], context: dict[str, Any]
) -> str:
    project_type = frontend_plan["project_type"]
    module_name = context["module_name"]
    entity_name = context["entity_name"]
    lower_name = lower_camel(entity_name)
    table_name = context["table_name"]
    url_path = table_name.replace("_", "-")
    frontend_business_path = (
        frontend_plan.get("frontend_business_path")
        or context.get("generated_file_plan", {}).get("frontend_business_path")
        or context["business_name"]
    )
    ts_interface = render_ts_interface(entity_name + "VO", get_resp_fields(context))
    if is_vben_codegen_type(project_type):
        return render_vben_api_file(
            module_name=module_name,
            frontend_business_path=frontend_business_path,
            entity_name=entity_name,
            entity_label=resolve_frontend_entity_label(context),
            fields=get_resp_fields(context),
            url_path=url_path,
        )
    if is_uniapp_codegen_type(project_type):
        return dedent(
            f"""\
            import request from '@/config/axios'

            {ts_interface}

            export const get{entity_name}Page = (params: any) => {{
              return request.get({{
                url: '/admin-api/{module_name}/{url_path}/page',
                params,
              }})
            }}

            export const get{entity_name} = (id: number) => {{
              return request.get({{
                url: '/admin-api/{module_name}/{url_path}/get?id=' + id,
              }})
            }}

            export const save{entity_name} = (data: {entity_name}VO) => {{
              return request.request({{
                url: '/admin-api/{module_name}/{url_path}/' + (data.id ? 'update' : 'create'),
                method: data.id ? 'PUT' : 'POST',
                data,
              }})
            }}

            export const delete{entity_name} = (id: number) => {{
              return request.delete({{
                url: '/admin-api/{module_name}/{url_path}/delete?id=' + id,
              }})
            }}
            """
        )
    return dedent(
        f"""\
        import request from '@/config/axios'

        {ts_interface}

        export const get{entity_name}Page = async (params: any) => {{
          return await request.get({{ url: '/admin-api/{module_name}/{url_path}/page', params }})
        }}

        export const get{entity_name} = async (id: number) => {{
          return await request.get({{ url: '/admin-api/{module_name}/{url_path}/get', params: {{ id }} }})
        }}

        export const create{entity_name} = async (data: {entity_name}VO) => {{
          return await request.post({{ url: '/admin-api/{module_name}/{url_path}/create', data }})
        }}

        export const update{entity_name} = async (data: {entity_name}VO) => {{
          return await request.put({{ url: '/admin-api/{module_name}/{url_path}/update', data }})
        }}

        export const delete{entity_name} = async (id: number) => {{
          return await request.delete({{ url: '/admin-api/{module_name}/{url_path}/delete', params: {{ id }} }})
        }}

        export const {lower_name}Permission = '{context["permission_prefix"]}'
        """
    )


def render_vben_api_file(
    *,
    module_name: str,
    frontend_business_path: str,
    entity_name: str,
    entity_label: str,
    fields: list[dict[str, Any]],
    url_path: str = "",
) -> str:
    namespace = build_vben_api_namespace(entity_name)
    model_name = entity_name
    base_url = f"/{module_name}/{url_path}" if url_path else f"/{module_name}/{frontend_business_path.replace('/', '_')}"
    interface_body = render_vben_api_interface_body(fields)
    return (
        "\n".join(
            [
                "import type { PageParam, PageResult } from '@vben/request';",
                "",
                "import { requestClient } from '#/api/request';",
                "",
                f"export namespace {namespace} {{",
                f"  /** {entity_label}信息 */",
                f"  export interface {model_name} {{",
                indent_block(interface_body, "    "),
                "  }",
                "}",
                "",
                f"/** 查询{entity_label}列表 */",
                f"export function get{entity_name}Page(params: PageParam) {{",
                f"  return requestClient.get<PageResult<{namespace}.{model_name}>>('{base_url}/page', {{",
                "    params,",
                "  });",
                "}",
                "",
                f"/** 查询{entity_label}详情 */",
                f"export function get{entity_name}(id: number) {{",
                f"  return requestClient.get<{namespace}.{model_name}>(`{base_url}/get?id=${{id}}`);",
                "}",
                "",
                f"/** 新增{entity_label} */",
                f"export function create{entity_name}(data: {namespace}.{model_name}) {{",
                f"  return requestClient.post('{base_url}/create', data);",
                "}",
                "",
                f"/** 修改{entity_label} */",
                f"export function update{entity_name}(data: {namespace}.{model_name}) {{",
                f"  return requestClient.put('{base_url}/update', data);",
                "}",
                "",
                f"/** 删除{entity_label} */",
                f"export function delete{entity_name}(id: number) {{",
                f"  return requestClient.delete(`{base_url}/delete?id=${{id}}`);",
                "}",
            ]
        ).strip()
        + "\n"
    )


def render_frontend_index(
    relative_path: str, frontend_plan: dict[str, Any], context: dict[str, Any]
) -> str:
    if is_uniapp_codegen_type(frontend_plan["project_type"]):
        return render_uniapp_index(relative_path, context)
    if is_vben_codegen_type(frontend_plan["project_type"]):
        return render_vben_index(relative_path, frontend_plan, context)
    return render_vue3_index(relative_path, context)


def render_vue3_index(relative_path: str, context: dict[str, Any]) -> str:
    entity_name = context["entity_name"]
    simple_class_name = context["generated_file_plan"]["simple_class_name"]
    list_fields = get_frontend_list_fields(context)
    column_lines = "\n".join(render_vue3_table_column(field) for field in list_fields)
    ts_interface = render_ts_interface(entity_name + "VO", get_resp_fields(context))
    return dedent(
        f"""\
<template>
  <ContentWrap>
    <div class="mb-16px text-14px text-[var(--el-text-color-secondary)]">
      Yudao Pilot 已根据 `{context["table_name"]}` 解析字段并生成首版页面骨架。
    </div>
    <el-button type="primary">新增{entity_name}</el-button>
    <el-table :data="list" class="mt-16px">
{indent_block(column_lines, "      ")}
      <el-table-column label="操作" width="160">
        <template #default>
          <el-button link type="primary">编辑</el-button>
          <el-button link type="danger">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <{simple_class_name}Form ref="formRef" />
  </ContentWrap>
</template>

<script setup lang="ts">
import {{ ref }} from 'vue'
import {entity_name}Form from './{simple_class_name}Form.vue'

{ts_interface}

const list = ref<{entity_name}VO[]>([])

// TODO Yudao Pilot: 继续接入查询条件、权限点和真实接口调用
</script>
"""
    ).strip() + "\n"


def render_vue3_form(relative_path: str, context: dict[str, Any]) -> str:
    entity_name = context["entity_name"]
    save_fields = get_frontend_save_fields(context)
    form_items = "\n".join(render_vue3_form_item(field) for field in save_fields)
    form_state = ",\n".join(render_ts_form_state_line(field) for field in save_fields)
    return dedent(
        f"""\
<template>
  <el-dialog v-model="visible" title="{entity_name}表单" width="640px">
    <el-form :model="formData" label-width="100px">
{indent_block(form_items, "      ")}
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import {{ reactive, ref }} from 'vue'

const visible = ref(false)
const formData = reactive({{
  id: undefined as number | undefined,
{indent_block(form_state, "  ")}
}})

const open = (data?: Partial<typeof formData>) => {{
  Object.assign(formData, {{
    id: undefined as number | undefined,
{indent_block(form_state, "    ")}
  }}, data)
  visible.value = true
}}

const handleSubmit = () => {{
  // TODO Yudao Pilot: 接入 save API，并结合字段规则补齐校验
  visible.value = false
}}

defineExpose({{ open }})
</script>
"""
    ).strip() + "\n"


def render_vben_index(
    relative_path: str, frontend_plan: dict[str, Any], context: dict[str, Any]
) -> str:
    entity_name = context["entity_name"]
    entity_label = resolve_frontend_entity_label(context)
    api_import_path = build_frontend_api_import_path(frontend_plan, context)
    api_namespace = build_vben_api_namespace(entity_name)
    uses_element_plus = is_vben_ele_codegen_type(frontend_plan["project_type"])
    grid_columns_expr = "useGridColumns()"
    grid_form_expr = "useGridFormSchema()"
    schema_import = "import { useGridColumns, useGridFormSchema } from './data';"
    feedback_import = (
        "import { ElLoading, ElMessage } from 'element-plus';"
        if uses_element_plus
        else "import { message } from 'ant-design-vue';"
    )
    delete_handler = (
        dedent(
            f"""\
            async function handleDelete(row: {api_namespace}.{entity_name}) {{
              const loadingInstance = ElLoading.service({{
                text: $t('ui.actionMessage.deleting', [row.id]),
              }});
              try {{
                await delete{entity_name}(row.id!);
                ElMessage.success($t('ui.actionMessage.deleteSuccess', [row.id]));
                handleRefresh();
              }} finally {{
                loadingInstance.close();
              }}
            }}
            """
        ).strip()
        if uses_element_plus
        else dedent(
            f"""\
            async function handleDelete(row: {api_namespace}.{entity_name}) {{
              const hideLoading = message.loading({{
                content: $t('ui.actionMessage.deleting', [row.id]),
                duration: 0,
              }});
              try {{
                await delete{entity_name}(row.id!);
                message.success($t('ui.actionMessage.deleteSuccess', [row.id]));
                handleRefresh();
              }} finally {{
                hideLoading();
              }}
            }}
            """
        ).strip()
    )
    edit_action_lines = [
        "{",
        "  label: $t('common.edit'),",
        "  type: 'primary'," if uses_element_plus else "  type: 'link',",
        "  link: true," if uses_element_plus else None,
        "  icon: ACTION_ICON.EDIT,",
        f"  auth: ['{context['permission_prefix']}:update'],",
        "  onClick: handleEdit.bind(null, row),",
        "},",
    ]
    delete_action_lines = [
        "{",
        "  label: $t('common.delete'),",
        "  type: 'danger'," if uses_element_plus else "  type: 'link',",
        "  link: true," if uses_element_plus else "  danger: true,",
        "  icon: ACTION_ICON.DELETE,",
        f"  auth: ['{context['permission_prefix']}:delete'],",
        "  popConfirm: {",
        "    title: $t('ui.actionMessage.deleteConfirm', [row.id]),",
        "    confirm: handleDelete.bind(null, row),",
        "  },",
        "}",
    ]
    lines = [
        '<script lang="ts" setup>',
        "import type { VxeTableGridOptions } from '#/adapter/vxe-table';",
        f"import type {{ {api_namespace} }} from '{api_import_path}';",
        "",
        "import { Page, useVbenModal } from '@vben/common-ui';",
        feedback_import,
        "",
        "import { ACTION_ICON, TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';",
        f"import {{ delete{entity_name}, get{entity_name}Page }} from '{api_import_path}';",
        "import { $t } from '#/locales';",
        "",
    ]
    lines.append(schema_import)
    lines.extend(
        [
            "import Form from './modules/form.vue';",
            "",
        ]
    )
    lines.extend(
        [
            "const [FormModal, formModalApi] = useVbenModal({",
            "  connectedComponent: Form,",
            "  destroyOnClose: true,",
            "});",
            "",
            "function handleRefresh() {",
            "  gridApi.query();",
            "}",
            "",
            "function handleCreate() {",
            "  formModalApi.setData(null).open();",
            "}",
            "",
            f"function handleEdit(row: {api_namespace}.{entity_name}) {{",
            "  formModalApi.setData(row).open();",
            "}",
            "",
        ]
    )
    lines.extend(delete_handler.splitlines())
    lines.extend(
        [
            "",
            "const [Grid, gridApi] = useVbenVxeGrid({",
            "  formOptions: {",
            f"    schema: {grid_form_expr},",
            "  },",
            "  gridOptions: {",
            f"    columns: {grid_columns_expr},",
            "    height: 'auto',",
            "    keepSource: true,",
            "    proxyConfig: {",
            "      ajax: {",
            "        query: async ({ page }, formValues) => {",
            f"          return await get{entity_name}Page({{",
            "            pageNo: page.currentPage,",
            "            pageSize: page.pageSize,",
            "            ...formValues,",
            "          });",
            "        },",
            "      },",
            "    },",
            "    rowConfig: {",
            "      keyField: 'id',",
            "      isHover: true,",
            "    },",
            "    toolbarConfig: {",
            "      refresh: true,",
            "      search: true,",
            "    },",
            f"  }} as VxeTableGridOptions<{api_namespace}.{entity_name}>,",
            "});",
            "</script>",
            "",
            "<template>",
            "  <Page auto-content-height>",
            "    <FormModal @success=\"handleRefresh\" />",
            f"    <Grid table-title=\"{entity_label}列表\">",
            "      <template #toolbar-tools>",
            "        <TableAction",
            "          :actions=\"[",
            f"            {{ label: $t('ui.actionTitle.create', ['{entity_label}']), type: 'primary', icon: ACTION_ICON.ADD, auth: ['{context['permission_prefix']}:create'], onClick: handleCreate }},",
            "          ]\"",
            "        />",
            "      </template>",
            "      <template #actions=\"{ row }\">",
            "        <TableAction",
            "          :actions=\"[",
            indent_block("\n".join([line for line in edit_action_lines if line]), "            "),
            indent_block("\n".join([line for line in delete_action_lines if line]), "            "),
            "          ]\"",
            "        />",
            "      </template>",
            "    </Grid>",
            "  </Page>",
            "</template>",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def render_vben_form(
    relative_path: str, frontend_plan: dict[str, Any], context: dict[str, Any]
) -> str:
    entity_name = context["entity_name"]
    entity_label = resolve_frontend_entity_label(context)
    api_import_path = build_frontend_api_import_path(frontend_plan, context)
    api_namespace = build_vben_api_namespace(entity_name)
    uses_element_plus = is_vben_ele_codegen_type(frontend_plan["project_type"])
    schema_import = "import { useFormSchema } from '../data';"
    schema_expr = "useFormSchema()"
    feedback_import = (
        "import { ElMessage } from 'element-plus';"
        if uses_element_plus
        else "import { message } from 'ant-design-vue';"
    )
    success_feedback = (
        "ElMessage.success($t('ui.actionMessage.operationSuccess'));"
        if uses_element_plus
        else "message.success($t('ui.actionMessage.operationSuccess'));"
    )
    lines = [
        '<script lang="ts" setup>',
        f"import type {{ {api_namespace} }} from '{api_import_path}';",
        "",
        "import { computed, ref } from 'vue';",
        "",
        "import { useVbenModal } from '@vben/common-ui';",
        feedback_import,
        "",
        "import { useVbenForm } from '#/adapter/form';",
        f"import {{ create{entity_name}, get{entity_name}, update{entity_name} }} from '{api_import_path}';",
        "import { $t } from '#/locales';",
        "",
    ]
    lines.append(schema_import)
    lines.append("")
    lines.extend(
        [
            "const emit = defineEmits(['success']);",
            f"const formData = ref<{api_namespace}.{entity_name}>();",
            "const getTitle = computed(() => {",
            "  return formData.value?.id",
            f"    ? $t('ui.actionTitle.edit', ['{entity_label}'])",
            f"    : $t('ui.actionTitle.create', ['{entity_label}']);",
            "});",
            "",
            "const [Form, formApi] = useVbenForm({",
            "  commonConfig: {",
            "    componentProps: {",
            "      class: 'w-full',",
            "    },",
            "    formItemClass: 'col-span-2',",
            "    labelWidth: 100,",
            "  },",
            "  layout: 'horizontal',",
            f"  schema: {schema_expr},",
            "  showDefaultActions: false,",
            "});",
            "",
            "const [Modal, modalApi] = useVbenModal({",
            "  async onConfirm() {",
            "    const { valid } = await formApi.validate();",
            "    if (!valid) {",
            "      return;",
            "    }",
            "    modalApi.lock();",
            f"    const data = (await formApi.getValues()) as {api_namespace}.{entity_name};",
            "    try {",
            f"      await (formData.value?.id ? update{entity_name}(data) : create{entity_name}(data));",
            "      await modalApi.close();",
            "      emit('success');",
            f"      {success_feedback}",
            "    } finally {",
            "      modalApi.unlock();",
            "    }",
            "  },",
            "  async onOpenChange(isOpen: boolean) {",
            "    if (!isOpen) {",
            "      formData.value = undefined;",
            "      return;",
            "    }",
            f"    const data = modalApi.getData<{api_namespace}.{entity_name}>();",
            "    if (!data || !data.id) {",
            "      return;",
            "    }",
            "    modalApi.lock();",
            "    try {",
            f"      formData.value = await get{entity_name}(data.id);",
            "      await formApi.setValues(formData.value);",
            "    } finally {",
            "      modalApi.unlock();",
            "    }",
            "  },",
            "});",
            "</script>",
            "",
            "<template>",
            '  <Modal :title="getTitle" class="w-1/2">',
            '    <Form class="mx-4" />',
            "  </Modal>",
            "</template>",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def render_vben_data(
    relative_path: str, frontend_plan: dict[str, Any], context: dict[str, Any]
) -> str:
    entity_name = context["entity_name"]
    api_import_path = build_frontend_api_import_path(frontend_plan, context)
    api_namespace = build_vben_api_namespace(entity_name)
    form_fields = get_frontend_save_fields(context)
    query_fields = get_frontend_query_fields(context)
    list_fields = get_frontend_list_fields(context)
    dict_types = collect_vben_dict_types(form_fields + query_fields + list_fields)
    needs_common_status_enum = any(
        should_use_vben_common_status_default(field) for field in form_fields
    )
    needs_dict_options = bool(dict_types)
    needs_range_picker_default_props = any(
        is_vben_range_picker_field(field) for field in query_fields
    )
    import_lines = [
        "import type { VbenFormSchema } from '#/adapter/form';",
        "import type { VxeTableGridOptions } from '#/adapter/vxe-table';",
        f"import type {{ {api_namespace} }} from '{api_import_path}';",
    ]
    constant_names: list[str] = []
    if needs_common_status_enum:
        constant_names.append("CommonStatusEnum")
    if needs_dict_options:
        constant_names.append("DICT_TYPE")
    if constant_names:
        import_lines.append("")
        import_lines.append(f"import {{ {', '.join(constant_names)} }} from '@vben/constants';")
    if needs_dict_options:
        import_lines.append("import { getDictOptions } from '@vben/hooks';")
    extra_imports: list[str] = []
    if needs_common_status_enum:
        extra_imports.append("import { z } from '#/adapter/form';")
    if needs_range_picker_default_props:
        extra_imports.append("import { getRangePickerDefaultProps } from '#/utils';")
    if extra_imports:
        import_lines.append("")
        import_lines.extend(extra_imports)
    return (
        "\n".join(
            import_lines
            + [
                "",
                "/** 新增/修改的表单 */",
                "export function useFormSchema(): VbenFormSchema[] {",
                "  return [",
                indent_block(render_vben_form_schema_fields(form_fields, frontend_plan), "    "),
                "  ];",
                "}",
                "",
                "/** 列表的搜索表单 */",
                "export function useGridFormSchema(): VbenFormSchema[] {",
                "  return [",
                indent_block(render_vben_grid_form_schema_fields(query_fields, frontend_plan), "    "),
                "  ];",
                "}",
                "",
                "/** 列表的字段 */",
                f"export function useGridColumns(): VxeTableGridOptions<{api_namespace}.{entity_name}>['columns'] {{",
                "  return [",
                indent_block(render_vben_grid_columns(list_fields), "    "),
                "  ];",
                "}",
            ]
        ).strip()
        + "\n"
    )


def render_uniapp_index(relative_path: str, context: dict[str, Any]) -> str:
    entity_name = context["entity_name"]
    preview_field = next(
        (field for field in get_frontend_list_fields(context) if field["java_field"] != "id"),
        None,
    )
    preview_expr = f"item.{preview_field['java_field']}" if preview_field else "item.id"
    ts_interface = render_ts_interface(entity_name + "VO", get_resp_fields(context))
    return dedent(
        f"""\
        <template>
          <view class="page">
            <view class="page__header">
              <text class="page__title">{entity_name}列表</text>
            </view>
            <search-form />
            <view class="card" v-for="item in list" :key="item.id">
              <text class="card__title">#{{{{ item.id }}}}</text>
              <text class="card__desc">{{{{ {preview_expr} || '待补齐字段' }}}}</text>
            </view>
          </view>
        </template>

        <script setup lang="ts">
        import {{ ref }} from 'vue'
        import SearchForm from './components/search-form.vue'

        {ts_interface}

        const list = ref<{entity_name}VO[]>([])
        </script>

        <style scoped>
        .page {{ padding: 24rpx; }}
        .page__header {{ margin-bottom: 24rpx; }}
        .page__title {{ font-size: 34rpx; font-weight: 600; }}
        .card {{ margin-top: 20rpx; padding: 24rpx; border-radius: 20rpx; background: #ffffff; }}
        .card__title {{ display: block; font-weight: 600; }}
        .card__desc {{ display: block; margin-top: 12rpx; color: #666666; }}
        </style>
        """
    )


def render_uniapp_search_form(relative_path: str, context: dict[str, Any]) -> str:
    query_fields = get_frontend_query_fields(context)
    input_fields = "\n".join(render_uniapp_search_item(field) for field in query_fields[:3]) or '    <input class="search-input" placeholder="请输入关键字" />'
    return dedent(
        f"""\
        <template>
          <view class="search-box">
        {input_fields}
          </view>
        </template>

        <style scoped>
        .search-box {{ margin-bottom: 24rpx; }}
        .search-input {{ height: 72rpx; padding: 0 24rpx; border-radius: 16rpx; background: #f5f7fa; }}
        </style>
        """
    )


def render_uniapp_form(relative_path: str, context: dict[str, Any]) -> str:
    entity_name = context["entity_name"]
    save_fields = get_frontend_save_fields(context)
    form_items = "\n".join(render_uniapp_form_item(field) for field in save_fields[:6]) or '    <textarea class="textarea" placeholder="请输入备注" />'
    return dedent(
        f"""\
        <template>
          <view class="page">
            <text class="title">{entity_name}表单</text>
        {form_items}
          </view>
        </template>

        <style scoped>
        .page {{ padding: 24rpx; }}
        .title {{ display: block; margin-bottom: 24rpx; font-size: 34rpx; font-weight: 600; }}
        .input {{ height: 72rpx; margin-bottom: 20rpx; padding: 0 24rpx; border-radius: 16rpx; background: #f5f7fa; }}
        .textarea {{ width: 100%; min-height: 240rpx; padding: 24rpx; border-radius: 16rpx; background: #f5f7fa; }}
        </style>
        """
    )


def render_uniapp_detail(relative_path: str, context: dict[str, Any]) -> str:
    entity_name = context["entity_name"]
    rows = "\n".join(render_uniapp_detail_row(field) for field in get_resp_fields(context)[:8])
    ts_interface = render_ts_interface(entity_name + "VO", get_resp_fields(context))
    return dedent(
        f"""\
        <template>
          <view class="page">
            <text class="title">{entity_name}详情</text>
        {rows}
          </view>
        </template>

        <script setup lang="ts">
        import {{ ref }} from 'vue'

        {ts_interface}

        const detail = ref<{entity_name}VO | null>(null)
        </script>

        <style scoped>
        .page {{ padding: 24rpx; }}
        .title {{ display: block; margin-bottom: 24rpx; font-size: 34rpx; font-weight: 600; }}
        .row {{ display: flex; justify-content: space-between; margin-bottom: 16rpx; color: #666666; }}
        </style>
        """
    )


def render_mapper_query_lines(class_name: str, query_fields: list[dict[str, Any]]) -> str:
    if not query_fields:
        return ""
    lines: list[str] = []
    for field in query_fields:
        java_field = field["java_field"]
        getter = f"{class_name}DO::get{java_field[0].upper()}{java_field[1:]}"
        java_type = normalize_java_field_type(field)
        if java_type in {"LocalDateTime", "LocalDate"}:
            lines.append(
                f"                .betweenIfPresent({getter}, reqVO.get{java_field[0].upper()}{java_field[1:]}())"
            )
        elif java_type == "String":
            lines.append(
                f"                .likeIfPresent({getter}, reqVO.get{java_field[0].upper()}{java_field[1:]}())"
            )
        else:
            lines.append(
                f"                .eqIfPresent({getter}, reqVO.get{java_field[0].upper()}{java_field[1:]}())"
            )
    return "\n".join(lines)


def render_plain_placeholder(relative_path: str, context: dict[str, Any]) -> str:
    return f"// TODO Yudao Pilot: 请继续根据 {context['table_name']} 的字段定义补齐 {relative_path}\n"


def java_package_from_path(relative_path: str) -> str:
    marker = "/java/"
    if marker not in relative_path:
        return ""
    package_path = relative_path.split(marker, 1)[1].rsplit("/", 1)[0]
    return package_path.replace("/", ".")


def resolve_validation_package(backend_type: str) -> str:
    return "javax.validation" if backend_type == "ruoyi-vue-pro" else "jakarta.validation"


def resolve_resource_package(backend_type: str) -> str:
    return "javax.annotation" if backend_type == "ruoyi-vue-pro" else "jakarta.annotation"


def lower_camel(value: str) -> str:
    return value[:1].lower() + value[1:] if value else value


def is_vben_codegen_type(project_type: str) -> bool:
    return project_type in {
        "VUE3_VBEN5_ANTD_SCHEMA",
        "VUE3_VBEN5_ANTD_GENERAL",
        "VUE3_VBEN5_EP_SCHEMA",
        "VUE3_VBEN5_EP_GENERAL",
    }


def is_vben_ele_codegen_type(project_type: str) -> bool:
    return project_type in {
        "VUE3_VBEN5_EP_SCHEMA",
        "VUE3_VBEN5_EP_GENERAL",
    }


def is_uniapp_codegen_type(project_type: str) -> bool:
    return project_type == "VUE3_ADMIN_UNIAPP_WOT"


def resolve_error_code_section_title(context: dict[str, Any]) -> str:
    menu_name = context.get("menu_name")
    if is_human_label(menu_name):
        return str(menu_name).strip()

    table_schema = context.get("table_schema") or {}
    table_comment = table_schema.get("table_comment")
    business_name = str(context.get("business_name") or "")
    if isinstance(table_comment, str) and table_comment.strip():
        return normalize_business_label(table_comment.strip(), business_name)
    if business_name:
        return business_name.replace("_", " ").strip()
    return context["entity_name"]


def normalize_business_label(label: str, business_name: str) -> str:
    normalized = label.strip()
    for suffix in ("信息表", "关联表", "记录表", "日志表", "详情表", "明细表", "表"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
            break
    if business_name.endswith("_user"):
        if normalized.endswith("员工"):
            normalized = normalized[:-2] + "用户"
        elif not normalized.endswith(("用户", "会员", "账号", "人员")):
            normalized = normalized + "用户"
    return normalized or label


def is_human_label(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    if text == text.replace("_", "") and any("\u4e00" <= char <= "\u9fff" for char in text):
        return True
    return False


def upper_snake(value: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.upper())
    return "".join(chars)


def get_table_columns(context: dict[str, Any]) -> list[dict[str, Any]]:
    return list(context.get("table_schema", {}).get("columns", []))


def get_save_fields(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [field for field in get_table_columns(context) if field.get("in_save")]


def get_resp_fields(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [field for field in get_table_columns(context) if field.get("in_resp")]


def get_do_fields(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [field for field in get_table_columns(context) if field.get("in_do")]


def get_list_fields(context: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [field for field in get_table_columns(context) if field.get("in_list")]
    return fields[:6] if fields else []


def get_query_fields(context: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [field for field in get_table_columns(context) if field.get("in_query")]
    return fields[:6] if fields else []


def get_frontend_save_fields(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [field for field in get_save_fields(context) if should_render_frontend_save_field(field)]


def get_frontend_list_fields(context: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [field for field in get_list_fields(context) if should_render_frontend_list_field(field)]
    return fields[:6] if fields else []


def get_frontend_query_fields(context: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [field for field in get_query_fields(context) if should_render_frontend_query_field(field)]
    return fields[:6] if fields else []


def collect_java_type_imports(fields: list[dict[str, Any]]) -> list[str]:
    imports: list[str] = []
    java_type_to_import = {
        "BigDecimal": "java.math.BigDecimal",
        "LocalDate": "java.time.LocalDate",
        "LocalDateTime": "java.time.LocalDateTime",
        "LocalTime": "java.time.LocalTime",
    }
    for field in fields:
        java_type = normalize_java_field_type(field)
        import_path = java_type_to_import.get(java_type)
        if import_path and import_path not in imports:
            imports.append(import_path)
    return imports


def render_java_import_block(*imports: str) -> str:
    normalized = [item for item in imports if item]
    if not normalized:
        return ""
    unique: list[str] = []
    for item in normalized:
        if item not in unique:
            unique.append(item)
    return "\n".join(f"import {item};" for item in unique)


def render_java_field(field: dict[str, Any]) -> str:
    java_type = normalize_java_field_type(field)
    desc = escape_java_string(field["column_comment"])
    return (
        f'    @Schema(description = "{desc}")\n'
        f'    private {java_type} {field["java_field"]};'
    )


def render_save_vo_field(field: dict[str, Any]) -> str:
    """Render a SaveReqVO field with validation annotations."""
    java_type = normalize_java_field_type(field)
    desc = escape_java_string(field["column_comment"])
    label = sanitize_column_comment(field["column_comment"])
    lines = [f'    @Schema(description = "{desc}")']

    if not field.get("nullable"):
        if java_type == "String":
            lines.append(f'    @NotEmpty(message = "{label}不能为空")')
        else:
            lines.append(f'    @NotNull(message = "{label}不能为空")')

    if java_type == "BigDecimal":
        integer_digits = field.get("integer_digits")
        scale = field.get("scale")
        if integer_digits is not None and scale is not None:
            lines.append(
                f'    @Digits(integer = {integer_digits}, fraction = {scale}, message = "{label}数值超出范围")'
            )

    if java_type == "String":
        max_length = field.get("max_length")
        if max_length and max_length < 10000:
            lines.append(f'    @Size(max = {max_length}, message = "{label}长度不能超过{max_length}个字符")')

    lines.append(f'    private {java_type} {field["java_field"]};')
    return "\n".join(lines)


def collect_save_vo_imports(
    fields: list[dict[str, Any]], validation_package: str
) -> list[str]:
    """Collect validation annotation imports needed for SaveReqVO fields."""
    imports: list[str] = []
    has_not_null = False
    has_not_empty = False
    has_digits = False
    has_size = False

    for field in fields:
        java_type = normalize_java_field_type(field)
        if not field.get("nullable"):
            if java_type == "String":
                has_not_empty = True
            else:
                has_not_null = True
        if java_type == "BigDecimal" and field.get("integer_digits") is not None:
            has_digits = True
        if java_type == "String" and field.get("max_length"):
            has_size = True

    if has_not_null:
        imports.append(f"{validation_package}.constraints.NotNull")
    if has_not_empty:
        imports.append(f"{validation_package}.constraints.NotEmpty")
    if has_digits:
        imports.append(f"{validation_package}.constraints.Digits")
    if has_size:
        imports.append(f"{validation_package}.constraints.Size")
    return imports


def render_page_query_field(field: dict[str, Any]) -> str:
    java_type = normalize_java_field_type(field)
    desc = escape_java_string(field["column_comment"])
    if java_type in {"LocalDateTime", "LocalDate"}:
        return (
            f'    @Schema(description = "{desc}范围")\n'
            f'    private {java_type}[] {field["java_field"]};'
        )
    return render_java_field(field)


def normalize_java_field_type(field: dict[str, Any]) -> str:
    return "Long" if field["java_field"] == "id" else field["java_type"]


def render_ts_interface(name: str, fields: list[dict[str, Any]]) -> str:
    body = "\n".join(
        f"  {field['java_field']}?: {field['ts_type']};" for field in fields
    ) or "  id?: number;"
    return f"export interface {name} {{\n{body}\n}}"


def render_vue3_table_column(field: dict[str, Any]) -> str:
    label = sanitize_column_comment(field["column_comment"])
    width = "120" if field["ts_type"] == "number" or field["java_field"] == "id" else "180"
    return f'              <el-table-column label="{label}" prop="{field["java_field"]}" width="{width}" />'


def render_vue3_form_item(field: dict[str, Any]) -> str:
    label = sanitize_column_comment(field["column_comment"])
    model = f'formData.{field["java_field"]}'
    placeholder = escape_html_attr(f"请输入{label}")
    html_type = field["html_type"]
    if html_type in {"textarea"}:
        control = f'<el-input v-model="{model}" type="textarea" placeholder="{placeholder}" />'
    elif html_type in {"datetime", "date"}:
        value_type = ' value-format="YYYY-MM-DD HH:mm:ss"' if html_type == "datetime" else ' value-format="YYYY-MM-DD"'
        picker_type = "datetime" if html_type == "datetime" else "date"
        control = f'<el-date-picker v-model="{model}" type="{picker_type}" placeholder="{placeholder}"{value_type} />'
    else:
        control = f'<el-input v-model="{model}" placeholder="{placeholder}" />'
    return f'              <el-form-item label="{label}">\n                {control}\n              </el-form-item>'


def render_ts_form_state_line(field: dict[str, Any]) -> str:
    value = default_ts_value(field)
    return f'          {field["java_field"]}: {value}'


def default_ts_value(field: dict[str, Any]) -> str:
    if field["ts_type"] == "number":
        return "undefined as number | undefined"
    if field["ts_type"] == "boolean":
        return "false"
    return "''"


def render_vben_column(field: dict[str, Any]) -> str:
    lines = [
        "{",
        f"  field: '{field['java_field']}',",
        f"  title: '{sanitize_column_comment(field['column_comment'])}',",
        f"  minWidth: {resolve_vben_column_width(field)},",
    ]
    if field["java_type"] == "LocalDateTime":
        lines.append("  formatter: 'formatDateTime',")
    else:
        dict_type = infer_vben_dict_type(field)
        if dict_type:
            lines.extend(
                [
                    "  cellRender: {",
                    "    name: 'CellDict',",
                    f"    props: {{ type: DICT_TYPE.{dict_type} }},",
                    "  },",
                ]
            )
        else:
            lines.extend(build_vben_enum_formatter_lines(field))
    if should_use_vben_tooltip(field):
        lines.append("  showOverflow: 'tooltip',")
    lines.append("}")
    return "\n".join(lines)


def render_vben_search_field(field: dict[str, Any], frontend_plan: dict[str, Any]) -> str:
    clear_prop = resolve_vben_clear_prop_name(frontend_plan)
    component = "RangePicker" if is_vben_range_picker_field(field) else "Input"
    dict_type = infer_vben_dict_type(field)
    enum_options = build_vben_inline_options(field)
    if field["html_type"] in {"select", "radio", "checkbox"} or dict_type or enum_options:
        component = "Select"
    component_props: list[str] = []
    if component == "RangePicker":
        component_props.append("...getRangePickerDefaultProps()")
        component_props.append(f"{clear_prop}: true")
    elif component == "Select":
        if dict_type:
            component_props.append(
                f"options: getDictOptions(DICT_TYPE.{dict_type}, '{resolve_vben_dict_value_type(field)}')"
            )
        elif enum_options:
            component_props.append(f"options: {render_vben_options_literal(enum_options)}")
        else:
            component_props.append("options: []")
        component_props.append(
            f"placeholder: '请选择{sanitize_column_comment(field['column_comment'])}'"
        )
        component_props.append(f"{clear_prop}: true")
    else:
        component_props.append(
            f"placeholder: '请输入{sanitize_column_comment(field['column_comment'])}'"
        )
        component_props.append(f"{clear_prop}: true")
    component_props_block = "\n".join(f"    {item}," for item in component_props)
    return (
        "{\n"
        f"  fieldName: '{field['java_field']}',\n"
        f"  label: '{sanitize_column_comment(field['column_comment'])}',\n"
        f"  component: '{component}',\n"
        "  componentProps: {\n"
        f"{component_props_block}\n"
        "  },\n"
        "}"
    )


def render_vben_form_field(field: dict[str, Any], frontend_plan: dict[str, Any]) -> str:
    html_type = field["html_type"]
    component = "Input"
    dict_type = infer_vben_dict_type(field)
    enum_options = build_vben_inline_options(field)
    component_props = [f"placeholder: '请输入{sanitize_column_comment(field['column_comment'])}'"]
    if html_type == "textarea":
        component = "Textarea"
    elif html_type == "editor":
        component = "RichTextarea"
        component_props = []
    elif html_type in {"datetime", "date"}:
        component = "DatePicker"
        component_props = [
            "showTime: true" if html_type == "datetime" else None,
            "format: 'YYYY-MM-DD HH:mm:ss'" if html_type == "datetime" else "format: 'YYYY-MM-DD'",
            "valueFormat: 'x'" if html_type == "datetime" else "valueFormat: 'YYYY-MM-DD'",
            "!w-full",
            f"placeholder: '请选择{sanitize_column_comment(field['column_comment'])}'",
        ]
    elif html_type == "inputNumber":
        component = "InputNumber"
        component_props = [
            f"placeholder: '请输入{sanitize_column_comment(field['column_comment'])}'",
            "min: 0",
            "class: '!w-full'" if resolve_vben_clear_prop_name(frontend_plan) == "clearable" else None,
            "controlsPosition: 'right'" if resolve_vben_clear_prop_name(frontend_plan) == "clearable" else None,
        ]
    elif html_type in {"select", "radio"} and dict_type:
        component = "RadioGroup" if html_type == "radio" else "Select"
        component_props = [
            f"options: getDictOptions(DICT_TYPE.{dict_type}, '{resolve_vben_dict_value_type(field)}')",
            f"placeholder: '请选择{sanitize_column_comment(field['column_comment'])}'" if component == "Select" else None,
            "buttonStyle: 'solid'" if component == "RadioGroup" and resolve_vben_clear_prop_name(frontend_plan) == "allowClear" else None,
            "optionType: 'button'" if component == "RadioGroup" and resolve_vben_clear_prop_name(frontend_plan) == "allowClear" else None,
        ]
    elif html_type in {"select", "radio"} and enum_options:
        component = "RadioGroup" if len(enum_options) <= 3 else "Select"
        component_props = [
            f"options: {render_vben_options_literal(enum_options)}",
            f"placeholder: '请选择{sanitize_column_comment(field['column_comment'])}'" if component == "Select" else None,
            "buttonStyle: 'solid'" if component == "RadioGroup" and resolve_vben_clear_prop_name(frontend_plan) == "allowClear" else None,
            "optionType: 'button'" if component == "RadioGroup" and resolve_vben_clear_prop_name(frontend_plan) == "allowClear" else None,
        ]
    elif html_type == "select":
        component = "Select"
        component_props = [
            f"placeholder: '请选择{sanitize_column_comment(field['column_comment'])}'",
            "options: []",
        ]
    elif html_type == "radio":
        component = "RadioGroup"
        component_props = [
            "options: []",
            "buttonStyle: 'solid'" if resolve_vben_clear_prop_name(frontend_plan) == "allowClear" else None,
            "optionType: 'button'" if resolve_vben_clear_prop_name(frontend_plan) == "allowClear" else None,
        ]
    elif html_type == "checkbox":
        component = "Checkbox"
        component_props = ["options: []"]
    elif html_type in {"imageUpload", "image-upload"}:
        component = "ImageUpload"
        component_props = []
    elif html_type in {"fileUpload", "file-upload"}:
        component = "FileUpload"
        component_props = []
    component_props = [item for item in component_props if item]
    component_props = [
        "class: '!w-full'" if item == "!w-full" else item for item in component_props
    ]
    rules_value = render_vben_form_rules(field)
    rules_line = f"  rules: {rules_value},\n" if rules_value else ""
    component_props_block = "\n".join(f"    {item}," for item in component_props)
    component_block = ""
    if component_props:
        component_block = "  componentProps: {\n" + component_props_block + "\n  },\n"
    return (
        "{\n"
        f"  fieldName: '{field['java_field']}',\n"
        f"  label: '{sanitize_column_comment(field['column_comment'])}',\n"
        f"  component: '{component}',\n"
        f"{rules_line}"
        f"{component_block}"
        "}"
    )


def render_vben_form_schema_fields(
    fields: list[dict[str, Any]], frontend_plan: dict[str, Any]
) -> str:
    items = [
        dedent(
            """\
            {
              fieldName: 'id',
              component: 'Input',
              dependencies: {
                triggerFields: [''],
                show: () => false,
              },
            }"""
        )
    ]
    effective_fields = fields or [
        {
            "java_field": "remark",
            "column_comment": "备注",
            "html_type": "textarea",
            "nullable": True,
        }
    ]
    items.extend(render_vben_form_field(field, frontend_plan) for field in effective_fields)
    return ",\n".join(items)


def render_vben_grid_form_schema_fields(
    fields: list[dict[str, Any]], frontend_plan: dict[str, Any]
) -> str:
    if not fields:
        fields = [
            {
                "java_field": "keyword",
                "column_comment": "关键字",
                "html_type": "input",
            }
        ]
    return ",\n".join(render_vben_search_field(field, frontend_plan) for field in fields)


def render_vben_grid_columns(fields: list[dict[str, Any]]) -> str:
    items = [render_vben_column(field) for field in fields] or [
        "{\n  field: 'id',\n  title: '编号',\n  minWidth: 100,\n}",
        "{\n  field: 'remark',\n  title: '备注',\n  minWidth: 180,\n  showOverflow: 'tooltip',\n}",
    ]
    items.append(
        dedent(
            """\
            {
              title: '操作',
              width: 160,
              fixed: 'right',
              slots: { default: 'actions' },
            }"""
        )
    )
    return ",\n".join(items)


def build_frontend_api_import_path(frontend_plan: dict[str, Any], context: dict[str, Any]) -> str:
    frontend_business_path = (
        frontend_plan.get("frontend_business_path")
        or context.get("generated_file_plan", {}).get("frontend_business_path")
        or context["business_name"]
    )
    return f"#/api/{context['module_name']}/{frontend_business_path}"


def resolve_frontend_entity_label(context: dict[str, Any]) -> str:
    table_schema = context.get("table_schema") or {}
    table_comment = table_schema.get("table_comment")
    if isinstance(table_comment, str) and table_comment.strip():
        return normalize_business_label(
            table_comment.strip(),
            str(context.get("business_name") or ""),
        )
    menu_name = context.get("menu_name")
    if is_human_label(menu_name):
        return str(menu_name).strip()
    return context["entity_name"]


def render_vben_api_interface_body(fields: list[dict[str, Any]]) -> str:
    effective_fields = fields or [
        {
            "java_field": "id",
            "column_comment": "编号",
            "ts_type": "number",
        },
        {
            "java_field": "remark",
            "column_comment": "备注",
            "ts_type": "string",
        },
    ]
    return "\n".join(
        f"/** {sanitize_column_comment(field['column_comment'])} */\n{field['java_field']}?: {field['ts_type']};"
        for field in effective_fields
    )


def build_vben_api_namespace(entity_name: str) -> str:
    return f"{entity_name}Api"


def should_render_frontend_save_field(field: dict[str, Any]) -> bool:
    return field["java_field"] not in {
        "deleteToken",
        "deleted",
        "tenantId",
        "creator",
        "updater",
        "createTime",
        "updateTime",
    }


def should_render_frontend_list_field(field: dict[str, Any]) -> bool:
    return field["java_field"] not in {
        "deleteToken",
        "deleted",
        "tenantId",
    }


def should_render_frontend_query_field(field: dict[str, Any]) -> bool:
    if field["java_field"] == "createTime":
        return True
    if field.get("is_base_column"):
        return False
    return field["java_field"] not in {
        "deleteToken",
        "deleted",
        "updateTime",
        "tenantId",
    }


def infer_vben_dict_type(field: dict[str, Any]) -> str | None:
    java_field = field["java_field"]
    if java_field == "status":
        return "COMMON_STATUS"
    if java_field in {"sex", "userSex"} or java_field.endswith("Sex"):
        return "SYSTEM_USER_SEX"
    return None


def collect_vben_dict_types(fields: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for field in fields:
        dict_type = infer_vben_dict_type(field)
        if dict_type and dict_type not in result:
            result.append(dict_type)
    return result


def resolve_vben_dict_value_type(field: dict[str, Any]) -> str:
    if field["ts_type"] == "number":
        return "number"
    if field["ts_type"] == "boolean":
        return "boolean"
    return "string"


def sanitize_column_comment(comment: str) -> str:
    cleaned = re.sub(r"[\r\n]+", " ", comment).strip()
    return re.split(r"[:：(（]", cleaned, maxsplit=1)[0].strip() or cleaned


def build_vben_inline_options(field: dict[str, Any]) -> list[dict[str, Any]]:
    if infer_vben_dict_type(field):
        return []
    comment = re.sub(r"[\r\n]+", " ", str(field.get("column_comment") or "")).strip()
    if not comment or (":" not in comment and "：" not in comment):
        return []
    option_text = re.split(r"[:：]", comment, maxsplit=1)[-1].strip()
    if not re.search(r"\d+\s*[-=]\s*\S", option_text):
        return []
    options: list[dict[str, Any]] = []
    for segment in re.split(r"[，,；;]", option_text):
        item = segment.strip()
        if not item:
            continue
        match = re.match(r"(?P<value>[^-=:：\s]+)\s*[-=:：]\s*(?P<label>.+)", item)
        if not match:
            return []
        raw_value = match.group("value").strip()
        label = match.group("label").strip()
        options.append(
            {
                "label": label,
                "value": normalize_vben_option_value(raw_value, field["ts_type"]),
            }
        )
    return options


def normalize_vben_option_value(raw_value: str, ts_type: str) -> str | int | bool:
    lowered = raw_value.lower()
    if ts_type == "boolean" or lowered in {"true", "false"}:
        return lowered == "true"
    if ts_type == "number":
        try:
            return int(raw_value)
        except ValueError:
            pass
    return raw_value


def render_vben_options_literal(options: list[dict[str, Any]]) -> str:
    rendered = ", ".join(
        f"{{ label: '{escape_js_string(str(option['label']))}', value: {render_vben_option_value(option['value'])} }}"
        for option in options
    )
    return f"[{rendered}]"


def render_vben_option_value(value: str | int | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return f"'{escape_js_string(value)}'"


def build_vben_enum_formatter_lines(field: dict[str, Any]) -> list[str]:
    options = build_vben_inline_options(field)
    if not options:
        return []
    mappings = ", ".join(
        f"{render_vben_option_key(option['value'])}: '{escape_js_string(str(option['label']))}'"
        for option in options
    )
    return [
        "  formatter: ({ cellValue }) => {",
        f"    const labels: Record<string, string> = {{ {mappings} }};",
        "    return labels[String(cellValue)] ?? cellValue ?? '-';",
        "  },",
    ]


def render_vben_option_key(value: str | int | bool) -> str:
    if isinstance(value, bool):
        return "'true'" if value else "'false'"
    return f"'{value}'"


def resolve_vben_column_width(field: dict[str, Any]) -> int:
    if field["java_type"] == "LocalDateTime":
        return 180
    if field["html_type"] in {"textarea", "editor"} or should_use_vben_tooltip(field):
        return 200
    if field["html_type"] in {"imageUpload", "image-upload"}:
        return 140
    return 120


def should_use_vben_tooltip(field: dict[str, Any]) -> bool:
    return field["html_type"] in {"textarea", "editor"} or len(sanitize_column_comment(field["column_comment"])) >= 18


def resolve_vben_clear_prop_name(frontend_plan: dict[str, Any]) -> str:
    return "clearable" if frontend_plan.get("project_type", "").startswith("VUE3_VBEN5_EP") else "allowClear"


def is_vben_range_picker_field(field: dict[str, Any]) -> bool:
    return field["html_type"] in {"datetime", "date"}


def should_use_vben_common_status_default(field: dict[str, Any]) -> bool:
    return (
        field["java_field"] == "status"
        and field["html_type"] == "radio"
        and not field.get("nullable")
        and infer_vben_dict_type(field) == "COMMON_STATUS"
    )


def render_vben_form_rules(field: dict[str, Any]) -> str | None:
    if should_use_vben_common_status_default(field):
        return "z.number().default(CommonStatusEnum.ENABLE)"
    if not field.get("nullable"):
        return "'required'"
    return None


def escape_js_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def render_uniapp_search_item(field: dict[str, Any]) -> str:
    label = sanitize_column_comment(field['column_comment'])
    placeholder = escape_html_attr(f"请输入{label}")
    return f'    <input class="search-input" placeholder="{placeholder}" />'


def render_uniapp_form_item(field: dict[str, Any]) -> str:
    label = sanitize_column_comment(field['column_comment'])
    placeholder = escape_html_attr(f"请输入{label}")
    if field["html_type"] == "textarea":
        return f'    <textarea class="textarea" placeholder="{placeholder}" />'
    return f'    <input class="input" placeholder="{placeholder}" />'


def render_uniapp_detail_row(field: dict[str, Any]) -> str:
    label = sanitize_column_comment(field["column_comment"])
    return (
        f'    <view class="row"><text>{label}</text>'
        f'<text>{{{{ detail?.{field["java_field"]} ?? "-" }}}}</text></view>'
    )


def escape_java_string(value: str) -> str:
    s = value.replace("\\", "\\\\").replace('"', '\\"')
    return re.sub(r"[\r\n]+", " ", s).strip()


def escape_html_attr(value: str) -> str:
    return value.replace('"', "&quot;")


def indent_block(value: str, prefix: str) -> str:
    lines = value.splitlines()
    return "\n".join(f"{prefix}{line}" if line else "" for line in lines)
