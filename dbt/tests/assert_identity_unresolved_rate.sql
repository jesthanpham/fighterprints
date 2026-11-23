-- More than 1% unresolved means identity resolution is broken, not just a few odd names.
select count(*) filter (where fighter_id is null)::numeric / count(*) as unresolved_share
from {{ ref('stg_fighter_identity') }}
having count(*) filter (where fighter_id is null)::numeric / nullif(count(*), 0) > 0.01
