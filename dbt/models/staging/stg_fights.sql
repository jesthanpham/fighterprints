-- One row per fight. Upstream can list a fight more than once (e.g. a renamed event), so dedupe by fight URL.
with results as (
    select
        {{ id_from_url('url') }}                     as fight_id,
        {{ clean('event') }}                         as event_name_raw,
        {{ clean('bout') }}                          as bout,
        {{ clean('outcome') }}                       as outcome,
        {{ clean('weightclass') }}                   as weight_class,
        {{ clean('method') }}                        as method_raw,
        {{ clean('round') }}::int                    as end_round,
        {{ mmss_to_seconds('time') }}                as end_time_s,
        {{ clean('time_format') }}                   as time_format,
        row_number() over (partition by {{ id_from_url('url') }} order by _row_num) as dup_rank
    from {{ source('src', 'ufc_fight_results') }}
),

-- Every name this fight has been listed under; whichever one matches the events file wins.
listed_names as (
    select fight_id, event_name_raw as event_name from results
    union
    select {{ id_from_url('url') }}, {{ clean('event') }} from {{ source('src', 'ufc_fight_details') }}
),

fight_event as (
    select distinct on (n.fight_id) n.fight_id, e.event_id, e.event_name, e.event_date
    from listed_names n
    join {{ ref('stg_events') }} e on e.event_name = n.event_name
    order by n.fight_id, e.event_date desc
)

select
    r.fight_id,
    fe.event_id,
    coalesce(fe.event_name, r.event_name_raw)        as event_name,
    fe.event_date,
    trim(split_part(r.bout, ' vs. ', 1))             as fighter_a_name,
    trim(split_part(r.bout, ' vs. ', 2))             as fighter_b_name,
    split_part(r.outcome, '/', 1)                    as outcome_a,
    split_part(r.outcome, '/', 2)                    as outcome_b,
    r.weight_class,
    r.method_raw,
    case
        when r.method_raw in ('KO/TKO', 'TKO - Doctor''s Stoppage') then 'KO_TKO'
        when r.method_raw = 'Submission' then 'SUB'
        when r.method_raw like 'Decision%' then 'DEC'
        else 'OTHER'
    end                                              as method_group,
    r.end_round,
    r.end_time_s,
    r.time_format,
    {{ elapsed_seconds('r.end_round', 'r.end_time_s', 'r.time_format') }} as elapsed_s
from results r
left join fight_event fe on fe.fight_id = r.fight_id
where r.dup_rank = 1
