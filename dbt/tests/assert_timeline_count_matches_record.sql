-- One timeline row (one mark on the print) per fight in the fighter's record.
select p.fighter_id, p.wins + p.losses + p.draws + p.no_contests as record_fights, count(t.fight_id) as timeline_rows
from {{ ref('fighter_print_params') }} p
left join {{ ref('fighter_fight_timeline') }} t on t.fighter_id = p.fighter_id
group by 1, 2
having p.wins + p.losses + p.draws + p.no_contests <> count(t.fight_id)
