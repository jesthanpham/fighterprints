{{ config(severity='warn') }}
-- Rounds are 1-5 and nobody controls more than a full 5-minute round.
select * from {{ ref('stg_fight_round_stats') }}
where round_num not between 1 and 5 or ctrl_s > 300
