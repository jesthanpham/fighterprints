-- Nobody lands more strikes or takedowns than they attempt.
select * from {{ ref('stg_fight_round_stats') }}
where sig_landed > sig_att or total_landed > total_att or td_landed > td_att
   or head_landed > head_att or body_landed > body_att or leg_landed > leg_att
