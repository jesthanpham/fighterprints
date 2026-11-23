-- Every fight where both names resolved has exactly two fighters.
select fight_id, count(*) as fighters
from {{ ref('int_fighter_fight') }}
where fight_id not in (select fight_id from {{ ref('stg_fighter_identity') }} where fighter_id is null)
group by fight_id
having count(*) <> 2
