{# Trim, and treat upstream's three spellings of "missing" ('', '--', '---') as NULL. #}
{% macro clean(col) -%}
    nullif(nullif(nullif(trim({{ col }}), ''), '--'), '---')
{%- endmacro %}

{# The id at the end of a UFCStats URL: .../fighter-details/93fe7332d16c6ad9 -> 93fe7332d16c6ad9 #}
{% macro id_from_url(col) -%}
    regexp_replace(trim({{ col }}), '^.*/', '')
{%- endmacro %}

{# "11 of 25" -> 11 #}
{% macro of_landed(col) -%}
    nullif(split_part({{ clean(col) }}, ' of ', 1), '')::int
{%- endmacro %}

{# "11 of 25" -> 25 #}
{% macro of_attempted(col) -%}
    nullif(split_part({{ clean(col) }}, ' of ', 2), '')::int
{%- endmacro %}

{# "2:30" -> 150 #}
{% macro mmss_to_seconds(col) -%}
    (split_part({{ clean(col) }}, ':', 1)::int * 60 + split_part({{ clean(col) }}, ':', 2)::int)
{%- endmacro %}

{# Seconds from the opening bell to the finish: the lengths of all completed rounds (from the round
   lengths in e.g. "5 Rnd (5-5-5-5-5)" or "1 Rnd + OT (12-3)"), plus the time into the final round.
   Formats without a list (e.g. "No Time Limit") are assumed to have 5-minute rounds. #}
{% macro elapsed_seconds(end_round, end_time_s, time_format) -%}
    (
        coalesce(
            (
                select sum(minutes::int) * 60
                from unnest(string_to_array(substring({{ time_format }} from '\(([0-9-]+)\)'), '-'))
                    with ordinality as rounds(minutes, round_index)
                where round_index < {{ end_round }}
            ),
            ({{ end_round }} - 1) * 300
        ) + {{ end_time_s }}
    )
{%- endmacro %}
