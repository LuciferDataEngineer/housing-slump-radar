{% macro tidy(name) %}
read_csv_auto('{{ var("tidy_dir") }}/{{ name }}.csv', header=true)
{% endmacro %}
