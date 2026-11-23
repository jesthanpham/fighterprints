-- Career totals and rates per fighter. Rates use only fights that have round stats (early UFC events
-- have none); they're NULL when there are no such minutes, never a division error.
with totals as (
    select
        fighter_id,
        count(*)                                                        as fights,
        count(*) filter (where result = 'W')                            as wins,
        count(*) filter (where result = 'L')                            as losses,
        count(*) filter (where result = 'D')                            as draws,
        count(*) filter (where result = 'NC')                           as no_contests,
        count(*) filter (where has_stats)                               as fights_with_stats,
        coalesce(sum(elapsed_s) filter (where has_stats), 0)            as stat_seconds,
        sum(sig_landed) filter (where has_stats)                        as sig_landed,
        sum(sig_att) filter (where has_stats)                           as sig_att,
        sum(opp_sig_landed) filter (where has_stats)                    as opp_sig_landed,
        sum(opp_sig_att) filter (where has_stats)                       as opp_sig_att,
        sum(td_landed) filter (where has_stats)                         as td_landed,
        sum(td_att) filter (where has_stats)                            as td_att,
        sum(opp_td_landed) filter (where has_stats)                     as opp_td_landed,
        sum(opp_td_att) filter (where has_stats)                        as opp_td_att,
        sum(sub_att) filter (where has_stats)                           as sub_att,
        sum(kd) filter (where has_stats)                                as kd,
        sum(ctrl_s) filter (where has_stats)                            as ctrl_s,
        sum(head_landed) filter (where has_stats)                       as head_landed,
        sum(body_landed) filter (where has_stats)                       as body_landed,
        sum(leg_landed) filter (where has_stats)                        as leg_landed,
        count(*) filter (where result = 'W' and method_group = 'KO_TKO') as ko_wins,
        count(*) filter (where result = 'W' and method_group = 'SUB')    as sub_wins,
        count(*) filter (where result = 'L' and method_group = 'KO_TKO') as ko_losses
    from {{ ref('int_fighter_fight') }}
    group by fighter_id
),

rated as (
    select *, nullif(stat_seconds / 60.0, 0) as stat_minutes from totals
)

select
    fighter_id,
    fights,
    wins,
    losses,
    draws,
    no_contests,
    fights_with_stats,
    round(stat_seconds / 60.0, 2)::float8                        as minutes,
    (sig_landed / stat_minutes)::float8                          as sig_landed_per_min,
    (opp_sig_landed / stat_minutes)::float8                      as sig_absorbed_per_min,
    (sig_landed::numeric / nullif(sig_att, 0))::float8           as sig_acc,
    (1 - opp_sig_landed::numeric / nullif(opp_sig_att, 0))::float8 as sig_def,
    (td_landed * 15 / stat_minutes)::float8                      as td_per15,
    (td_landed::numeric / nullif(td_att, 0))::float8             as td_acc,
    (1 - opp_td_landed::numeric / nullif(opp_td_att, 0))::float8 as td_def,
    (ctrl_s::numeric / nullif(stat_seconds, 0))::float8          as ctrl_share,
    (sub_att * 15 / stat_minutes)::float8                        as sub_att_per15,
    (kd * 15 / stat_minutes)::float8                             as kd_per15,
    (head_landed::numeric / nullif(sig_landed, 0))::float8       as head_pct,
    (body_landed::numeric / nullif(sig_landed, 0))::float8       as body_pct,
    (leg_landed::numeric / nullif(sig_landed, 0))::float8        as leg_pct,
    ko_wins,
    sub_wins,
    ko_losses,
    coalesce((ko_wins + sub_wins)::numeric / nullif(wins, 0), 0)::float8 as finish_rate
from rated
