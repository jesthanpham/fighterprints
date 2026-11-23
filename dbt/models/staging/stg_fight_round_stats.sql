-- One row per fighter per round. Stats are keyed by (event name, bout) only, so map them to a fight_id
-- through every listing in fight_details (a fight can be listed under two event names), then attach
-- the resolved fighter_id.
with listings as (
    select distinct
        {{ clean('event') }}         as event_name,
        {{ clean('bout') }}          as bout,
        {{ id_from_url('url') }}     as fight_id
    from {{ source('src', 'ufc_fight_details') }}
),

rows as (
    select
        l.fight_id,
        replace({{ clean('s.round') }}, 'Round ', '')::int  as round_num,
        {{ clean('s.fighter') }}                            as fighter_name,
        s.*
    from {{ source('src', 'ufc_fight_stats') }} s
    join listings l on l.event_name = {{ clean('s.event') }} and l.bout = {{ clean('s.bout') }}
    where {{ clean('s.round') }} is not null and {{ clean('s.fighter') }} is not null
),

deduped as (
    select *, row_number() over (partition by fight_id, round_num, fighter_name order by _row_num) as dup_rank
    from rows
)

select
    d.fight_id,
    d.round_num,
    d.fighter_name,
    i.fighter_id,
    {{ to_int('d.kd') }}        as kd,
    {{ of_landed('d.sig_str') }}    as sig_landed,
    {{ of_attempted('d.sig_str') }} as sig_att,
    {{ of_landed('d.total_str') }}  as total_landed,
    {{ of_attempted('d.total_str') }} as total_att,
    {{ of_landed('d.td') }}         as td_landed,
    {{ of_attempted('d.td') }}      as td_att,
    {{ to_int('d.sub_att') }}   as sub_att,
    {{ to_int('d.rev') }}       as rev,
    {{ mmss_to_seconds('d.ctrl') }} as ctrl_s,
    {{ of_landed('d.head') }}       as head_landed,
    {{ of_attempted('d.head') }}    as head_att,
    {{ of_landed('d.body') }}       as body_landed,
    {{ of_attempted('d.body') }}    as body_att,
    {{ of_landed('d.leg') }}        as leg_landed,
    {{ of_attempted('d.leg') }}     as leg_att,
    {{ of_landed('d.distance') }}   as distance_landed,
    {{ of_landed('d.clinch') }}     as clinch_landed,
    {{ of_landed('d.ground') }}     as ground_landed
from deduped d
left join {{ ref('stg_fighter_identity') }} i
    on i.fight_id = d.fight_id and i.name_as_written = d.fighter_name
where d.dup_rank = 1
