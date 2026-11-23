-- Every fight in a fighter's career, in order: one mark on the print per row.
select
    fighter_id,
    fight_seq,
    fight_id,
    event_name,
    event_date,
    opponent_name,
    result,
    method_group,
    end_round,
    end_time_s
from {{ ref('int_fighter_fight') }}
