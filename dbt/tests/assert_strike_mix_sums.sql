{{ config(severity='warn') }}
-- Significant strikes split by target (head/body/leg) and by position (distance/clinch/ground) add up.
select * from {{ ref('stg_fight_round_stats') }}
where head_landed + body_landed + leg_landed <> sig_landed
   or distance_landed + clinch_landed + ground_landed <> sig_landed
