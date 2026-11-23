-- The renderer contract: exactly the inputs the fingerprint needs, one row per fighter.
-- reach_in and stance may be NULL; the renderer applies flagged defaults.
select
    fp.fighter_id,
    f.fighter_name,
    f.weight_lbs,
    fp.archetype,
    fp.sig_landed_per_min,
    fp.sig_absorbed_per_min,
    fp.head_pct,
    f.reach_in,
    f.stance,
    fp.finish_rate,
    fp.ko_losses,
    fp.wins,
    fp.losses,
    fp.draws,
    fp.no_contests,
    fp.small_sample,
    md5(concat_ws('|',
        fp.fighter_id, f.fighter_name, fp.archetype, fp.sig_landed_per_min, fp.sig_absorbed_per_min,
        fp.head_pct, f.reach_in, f.stance, fp.finish_rate, fp.ko_losses, fp.wins, fp.losses,
        fp.draws, fp.no_contests, fp.small_sample
    )) as input_hash
from {{ ref('fighter_fingerprint') }} fp
join {{ ref('stg_fighters') }} f on f.fighter_id = fp.fighter_id
