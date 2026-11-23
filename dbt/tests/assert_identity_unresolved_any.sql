{{ config(severity='warn') }}
-- Names we couldn't match to a fighter. Fix by adding them to src/ufc/identity/aliases.csv.
select * from {{ ref('stg_fighter_identity') }} where fighter_id is null
