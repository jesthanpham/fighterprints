-- Each fighter's style on 8 dimensions, as a UFC-wide percentile: the share of established fighters
-- (not small_sample) at or below their value. Percentiles make different stats comparable, so the
-- similarity score isn't dominated by whichever stat has the biggest numbers.
{% set dims = {
    'pace_pct': 'sig_landed_per_min',
    'absorbed_pct': 'sig_absorbed_per_min',
    'accuracy_pct': 'sig_acc',
    'defense_pct': 'sig_def',
    'takedown_pct': 'td_per15',
    'control_pct': 'ctrl_share',
    'submission_pct': 'sub_att_per15',
    'finish_pct': 'finish_rate',
} %}

with fighters as (
    select * from {{ ref('fighter_fingerprint') }}
),

established as (
    select * from fighters where not small_sample
)

select
    f.fighter_id,
    f.archetype,
    {%- for name, col in dims.items() %}
    (
        select (count(*) filter (where e.{{ col }} <= f.{{ col }}))::float8 / nullif(count(e.{{ col }}), 0)
        from established e
        where f.{{ col }} is not null
    ) as {{ name }}{{ "," if not loop.last }}
    {%- endfor %}
from fighters f
