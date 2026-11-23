-- Career stats + a rule-based style label. Thresholds are percentiles across fighters with a real
-- sample (3+ fights with stats and 15+ minutes). The first matching rule wins.
with stats as (
    select *, (fights_with_stats < 3 or minutes < 15) as small_sample
    from {{ ref('fighter_career_stats') }}
),

thresholds as (
    select
        percentile_cont(0.80) within group (order by sub_att_per15)        as p80_sub_att,
        percentile_cont(0.75) within group (order by td_per15)             as p75_td,
        percentile_cont(0.60) within group (order by ctrl_share)           as p60_ctrl,
        percentile_cont(0.60) within group (order by sig_landed_per_min)   as p60_pace,
        percentile_cont(0.75) within group (order by sig_absorbed_per_min) as p75_absorbed
    from stats
    where not small_sample
)

select
    s.*,
    case
        when s.sub_att_per15 >= t.p80_sub_att
          or (s.wins >= 3 and s.sub_wins::numeric / s.wins >= 0.5)                     then 'Grappler'
        when s.td_per15 >= t.p75_td and s.ctrl_share >= t.p60_ctrl                     then 'Wrestler'
        when s.sig_landed_per_min >= t.p60_pace and s.sig_absorbed_per_min >= t.p75_absorbed then 'Brawler'
        when s.sig_landed_per_min >= t.p60_pace
          or (s.wins >= 3 and s.ko_wins::numeric / s.wins >= 0.5)                      then 'Striker'
        else 'Balanced'
    end as archetype
from stats s
cross join thresholds t
