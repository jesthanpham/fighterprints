-- One row per resolved fighter per fight: their result, their own stat totals, and their opponent's
-- totals (= what they absorbed). Fights where we couldn't resolve the fighter are left out.
with fights as (
    select * from {{ ref('stg_fights') }}
),

sides as (
    select fight_id, fighter_a_name as name, fighter_b_name as opponent_name, outcome_a as result from fights
    union all
    select fight_id, fighter_b_name, fighter_a_name, outcome_b from fights
),

round_sums as (
    select
        fight_id,
        fighter_name,
        sum(sig_landed)   as sig_landed,
        sum(sig_att)      as sig_att,
        sum(td_landed)    as td_landed,
        sum(td_att)       as td_att,
        sum(sub_att)      as sub_att,
        sum(kd)           as kd,
        sum(ctrl_s)       as ctrl_s,
        sum(head_landed)  as head_landed,
        sum(body_landed)  as body_landed,
        sum(leg_landed)   as leg_landed
    from {{ ref('stg_fight_round_stats') }}
    group by fight_id, fighter_name
),

resolved as (
    select s.*, me.fighter_id, opp.fighter_id as opponent_id
    from sides s
    left join {{ ref('stg_fighter_identity') }} me
        on me.fight_id = s.fight_id and me.name_as_written = s.name
    left join {{ ref('stg_fighter_identity') }} opp
        on opp.fight_id = s.fight_id and opp.name_as_written = s.opponent_name
)

select
    r.fighter_id,
    r.opponent_id,
    r.opponent_name,
    r.fight_id,
    f.event_name,
    f.event_date,
    row_number() over (partition by r.fighter_id order by f.event_date nulls last, r.fight_id) as fight_seq,
    r.result,
    f.method_group,
    f.end_round,
    f.end_time_s,
    f.elapsed_s,
    (own.fight_id is not null and theirs.fight_id is not null) as has_stats,
    own.sig_landed,
    own.sig_att,
    own.td_landed,
    own.td_att,
    own.sub_att,
    own.kd,
    own.ctrl_s,
    own.head_landed,
    own.body_landed,
    own.leg_landed,
    theirs.sig_landed  as opp_sig_landed,
    theirs.sig_att     as opp_sig_att,
    theirs.td_landed   as opp_td_landed,
    theirs.td_att      as opp_td_att
from resolved r
join fights f on f.fight_id = r.fight_id
left join round_sums own    on own.fight_id = r.fight_id    and own.fighter_name = r.name
left join round_sums theirs on theirs.fight_id = r.fight_id and theirs.fighter_name = r.opponent_name
where r.fighter_id is not null
