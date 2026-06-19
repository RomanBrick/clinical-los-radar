{% macro parquet(relpath) -%}
    read_parquet('{{ (env_var("CDSP_ROOT", ".") ~ "/" ~ relpath) | replace("\\", "/") }}')
{%- endmacro %}
