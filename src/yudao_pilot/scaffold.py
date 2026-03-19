from __future__ import annotations

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
        *collect_java_type_imports(save_fields),
    )
    field_lines = "\n\n".join(render_java_field(field) for field in save_fields) or (
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
    permission = context["permission_prefix"]
    resource_package = resolve_resource_package(context["backend_project"]["type"])
    validation_package = resolve_validation_package(context["backend_project"]["type"])
    base_package = context["backend_codegen_defaults"]["base_package"]
    return dedent(
        f"""\
        package {package_name};

        import {resource_package}.Resource;
        import {validation_package}.Valid;
        import org.springframework.validation.annotation.Validated;
        import org.springframework.web.bind.annotation.DeleteMapping;
        import org.springframework.web.bind.annotation.GetMapping;
        import org.springframework.web.bind.annotation.PostMapping;
        import org.springframework.web.bind.annotation.PutMapping;
        import org.springframework.web.bind.annotation.RequestBody;
        import org.springframework.web.bind.annotation.RequestMapping;
        import org.springframework.web.bind.annotation.RequestParam;
        import org.springframework.web.bind.annotation.RestController;

        import {base_package}.framework.common.pojo.CommonResult;
        import {base_package}.framework.common.pojo.PageResult;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}PageReqVO;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}RespVO;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}SaveReqVO;
        import {base_package}.module.{module_name}.service.{business_name}.{class_name}Service;

        @RestController
        @RequestMapping("/{module_name}/{business_name}")
        @Validated
        public class {class_name}Controller {{

            /**
             * 建议权限前缀：{permission}
             * 父菜单解析结果：{context["menu_context"]["message"]}
             */
            @Resource
            private {class_name}Service {lower_camel(class_name)}Service;

            @PostMapping("/create")
            public CommonResult<Long> create{class_name}(@Valid @RequestBody {class_name}SaveReqVO createReqVO) {{
                return CommonResult.success({lower_camel(class_name)}Service.create{class_name}(createReqVO));
            }}

            @PutMapping("/update")
            public CommonResult<Boolean> update{class_name}(@Valid @RequestBody {class_name}SaveReqVO updateReqVO) {{
                {lower_camel(class_name)}Service.update{class_name}(updateReqVO);
                return CommonResult.success(true);
            }}

            @DeleteMapping("/delete")
            public CommonResult<Boolean> delete{class_name}(@RequestParam("id") Long id) {{
                {lower_camel(class_name)}Service.delete{class_name}(id);
                return CommonResult.success(true);
            }}

            @GetMapping("/get")
            public CommonResult<{class_name}RespVO> get{class_name}(@RequestParam("id") Long id) {{
                return CommonResult.success({lower_camel(class_name)}Service.get{class_name}(id));
            }}

            @GetMapping("/page")
            public CommonResult<PageResult<{class_name}RespVO>> get{class_name}Page({class_name}PageReqVO pageReqVO) {{
                return CommonResult.success({lower_camel(class_name)}Service.get{class_name}Page(pageReqVO));
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
    return dedent(
        f"""\
        package {package_name};

        import org.apache.ibatis.annotations.Mapper;

        import {base_package}.framework.mybatis.core.mapper.BaseMapperX;
        import {base_package}.module.{module_name}.dal.dataobject.{business_name}.{class_name}DO;

        @Mapper
        public interface {class_name}Mapper extends BaseMapperX<{class_name}DO> {{
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

            <!-- TODO Yudao Pilot: 根据字段定义补充 ResultMap、自定义 SQL 与复杂查询 -->

        </mapper>
        """
    )


def render_service(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    module_name = context["module_name"]
    business_name = context["business_name"]
    base_package = context["backend_codegen_defaults"]["base_package"]
    return dedent(
        f"""\
        package {package_name};

        import {base_package}.framework.common.pojo.PageResult;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}PageReqVO;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}RespVO;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}SaveReqVO;

        public interface {class_name}Service {{

            Long create{class_name}({class_name}SaveReqVO createReqVO);

            void update{class_name}({class_name}SaveReqVO updateReqVO);

            void delete{class_name}(Long id);

            {class_name}RespVO get{class_name}(Long id);

            PageResult<{class_name}RespVO> get{class_name}Page({class_name}PageReqVO pageReqVO);
        }}
        """
    )


def render_service_impl(relative_path: str, context: dict[str, Any]) -> str:
    package_name = java_package_from_path(relative_path)
    class_name = context["entity_name"]
    module_name = context["module_name"]
    business_name = context["business_name"]
    base_package = context["backend_codegen_defaults"]["base_package"]
    return dedent(
        f"""\
        package {package_name};

        import org.springframework.stereotype.Service;

        import {base_package}.framework.common.pojo.PageResult;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}PageReqVO;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}RespVO;
        import {base_package}.module.{module_name}.controller.admin.{business_name}.vo.{class_name}SaveReqVO;
        import {base_package}.module.{module_name}.service.{business_name}.{class_name}Service;

        @Service
        public class {class_name}ServiceImpl implements {class_name}Service {{

            @Override
            public Long create{class_name}({class_name}SaveReqVO createReqVO) {{
                throw new UnsupportedOperationException("TODO Yudao Pilot: 根据表字段和业务规则补齐 create 逻辑");
            }}

            @Override
            public void update{class_name}({class_name}SaveReqVO updateReqVO) {{
                throw new UnsupportedOperationException("TODO Yudao Pilot: 根据表字段和业务规则补齐 update 逻辑");
            }}

            @Override
            public void delete{class_name}(Long id) {{
                throw new UnsupportedOperationException("TODO Yudao Pilot: 根据业务规则补齐 delete 逻辑");
            }}

            @Override
            public {class_name}RespVO get{class_name}(Long id) {{
                throw new UnsupportedOperationException("TODO Yudao Pilot: 根据表字段和业务规则补齐 get 逻辑");
            }}

            @Override
            public PageResult<{class_name}RespVO> get{class_name}Page({class_name}PageReqVO pageReqVO) {{
                throw new UnsupportedOperationException("TODO Yudao Pilot: 根据表字段和业务规则补齐 page 逻辑");
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
    business_name = context["business_name"]
    entity_name = context["entity_name"]
    lower_name = lower_camel(entity_name)
    ts_interface = render_ts_interface(entity_name + "VO", get_resp_fields(context))
    if project_type == "yudao-ui-admin-uniapp":
        return dedent(
            f"""\
            import request from '@/config/axios'

            {ts_interface}

            export const get{entity_name}Page = (params: any) => {{
              return request.get({{
                url: '/admin-api/{module_name}/{business_name}/page',
                params,
              }})
            }}

            export const get{entity_name} = (id: number) => {{
              return request.get({{
                url: '/admin-api/{module_name}/{business_name}/get?id=' + id,
              }})
            }}

            export const save{entity_name} = (data: {entity_name}VO) => {{
              return request.request({{
                url: '/admin-api/{module_name}/{business_name}/' + (data.id ? 'update' : 'create'),
                method: data.id ? 'PUT' : 'POST',
                data,
              }})
            }}

            export const delete{entity_name} = (id: number) => {{
              return request.delete({{
                url: '/admin-api/{module_name}/{business_name}/delete?id=' + id,
              }})
            }}
            """
        )
    return dedent(
        f"""\
        import request from '@/config/axios'

        {ts_interface}

        export const get{entity_name}Page = async (params: any) => {{
          return await request.get({{ url: '/admin-api/{module_name}/{business_name}/page', params }})
        }}

        export const get{entity_name} = async (id: number) => {{
          return await request.get({{ url: '/admin-api/{module_name}/{business_name}/get', params: {{ id }} }})
        }}

        export const create{entity_name} = async (data: {entity_name}VO) => {{
          return await request.post({{ url: '/admin-api/{module_name}/{business_name}/create', data }})
        }}

        export const update{entity_name} = async (data: {entity_name}VO) => {{
          return await request.put({{ url: '/admin-api/{module_name}/{business_name}/update', data }})
        }}

        export const delete{entity_name} = async (id: number) => {{
          return await request.delete({{ url: '/admin-api/{module_name}/{business_name}/delete', params: {{ id }} }})
        }}

        export const {lower_name}Permission = '{context["permission_prefix"]}'
        """
    )


def render_frontend_index(
    relative_path: str, frontend_plan: dict[str, Any], context: dict[str, Any]
) -> str:
    if frontend_plan["project_type"] == "yudao-ui-admin-uniapp":
        return render_uniapp_index(relative_path, context)
    if frontend_plan["project_type"] == "yudao-ui-admin-vben":
        return render_vben_index(relative_path, frontend_plan, context)
    return render_vue3_index(relative_path, context)


def render_vue3_index(relative_path: str, context: dict[str, Any]) -> str:
    entity_name = context["entity_name"]
    simple_class_name = context["generated_file_plan"]["simple_class_name"]
    list_fields = get_list_fields(context)
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
    save_fields = get_save_fields(context)
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
    uses_schema = frontend_plan["default_front_type"] in {40, 50}
    imports = "import { columns, searchFormSchema } from './data'\n" if uses_schema else ""
    extra = (
        "const tableColumns = columns\nconst formSchema = searchFormSchema\n"
        if uses_schema
        else "const tableColumns = []\nconst formSchema = []\n"
    )
    return dedent(
        f"""\
        <script setup lang="ts">
        {imports}import FormModal from './modules/form.vue'

        {extra}
        // TODO Yudao Pilot: 接入 Vben Table、权限点 `{context["permission_prefix"]}` 和真实字段定义
        </script>

        <template>
          <div class="p-4">
            <div class="mb-4 text-sm text-gray-500">
              {entity_name} 首版页面骨架已生成，后续请继续补齐字段和交互。
            </div>
            <FormModal />
            <pre>{{{{ tableColumns }}}}</pre>
            <pre>{{{{ formSchema }}}}</pre>
          </div>
        </template>
        """
    )


def render_vben_form(
    relative_path: str, frontend_plan: dict[str, Any], context: dict[str, Any]
) -> str:
    entity_name = context["entity_name"]
    save_fields = get_save_fields(context)
    preview_fields = "\n".join(f"      <li>{field['column_comment']}：{field['java_field']}</li>" for field in save_fields[:8])
    return dedent(
        f"""\
        <script setup lang="ts">
        // TODO Yudao Pilot: 根据字段定义补齐 Vben 表单组件与校验
        </script>

        <template>
          <div class="rounded-lg border border-dashed p-4">
            <div class="mb-3 font-medium">{entity_name} 表单骨架</div>
            <ul class="list-disc pl-5 text-sm text-gray-500">
        {preview_fields}
            </ul>
          </div>
        </template>
        """
    )


def render_vben_data(
    relative_path: str, frontend_plan: dict[str, Any], context: dict[str, Any]
) -> str:
    list_fields = get_list_fields(context)
    query_fields = get_query_fields(context)
    columns = ",\n".join(render_vben_column(field) for field in list_fields)
    search_schema = ",\n".join(render_vben_search_field(field) for field in query_fields)
    return dedent(
        f"""\
        export const columns = [
        {columns}
        ]

        export const searchFormSchema = [
        {search_schema}
        ]

        // TODO Yudao Pilot: 根据字典、状态枚举和权限进一步补齐 schema
        """
    )


def render_uniapp_index(relative_path: str, context: dict[str, Any]) -> str:
    entity_name = context["entity_name"]
    preview_field = next((field for field in get_list_fields(context) if field["java_field"] != "id"), None)
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
    query_fields = get_query_fields(context)
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
    save_fields = get_save_fields(context)
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
    return (
        f'    @Schema(description = "{escape_java_string(field["column_comment"])}")\n'
        f'    private {java_type} {field["java_field"]};'
    )


def render_page_query_field(field: dict[str, Any]) -> str:
    java_type = normalize_java_field_type(field)
    if java_type in {"LocalDateTime", "LocalDate"}:
        return (
            f'    @Schema(description = "{escape_java_string(field["column_comment"])}范围")\n'
            f'    private {java_type}[] {field["java_field"]};'
        )
    return render_java_field(field)


def normalize_java_field_type(field: dict[str, Any]) -> str:
    return "Long" if field["java_field"] == "id" else field["java_type"]


def render_ts_interface(name: str, fields: list[dict[str, Any]]) -> str:
    body = "\n".join(
        f"  {field['java_field']}?: {field['ts_type']}" for field in fields
    ) or "  id?: number"
    return f"export interface {name} {{\n{body}\n}}"


def render_vue3_table_column(field: dict[str, Any]) -> str:
    width = "120" if field["ts_type"] == "number" or field["java_field"] == "id" else "180"
    return f'              <el-table-column label="{field["column_comment"]}" prop="{field["java_field"]}" width="{width}" />'


def render_vue3_form_item(field: dict[str, Any]) -> str:
    label = field["column_comment"]
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
    return (
        "  {\n"
        f"    title: '{field['column_comment']}',\n"
        f"    dataIndex: '{field['java_field']}',\n"
        "  }"
    )


def render_vben_search_field(field: dict[str, Any]) -> str:
    component = "DatePicker" if field["html_type"] in {"datetime", "date"} else "Input"
    return (
        "  {\n"
        f"    fieldName: '{field['java_field']}',\n"
        f"    label: '{field['column_comment']}',\n"
        f"    component: '{component}',\n"
        "  }"
    )


def render_uniapp_search_item(field: dict[str, Any]) -> str:
    placeholder = escape_html_attr(f"请输入{field['column_comment']}")
    return f'    <input class="search-input" placeholder="{placeholder}" />'


def render_uniapp_form_item(field: dict[str, Any]) -> str:
    placeholder = escape_html_attr(f"请输入{field['column_comment']}")
    if field["html_type"] == "textarea":
        return f'    <textarea class="textarea" placeholder="{placeholder}" />'
    return f'    <input class="input" placeholder="{placeholder}" />'


def render_uniapp_detail_row(field: dict[str, Any]) -> str:
    return (
        f'    <view class="row"><text>{field["column_comment"]}</text>'
        f'<text>{{{{ detail?.{field["java_field"]} ?? "-" }}}}</text></view>'
    )


def escape_java_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def escape_html_attr(value: str) -> str:
    return value.replace('"', "&quot;")


def indent_block(value: str, prefix: str) -> str:
    lines = value.splitlines()
    return "\n".join(f"{prefix}{line}" if line else "" for line in lines)
