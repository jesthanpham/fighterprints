with tott as (
    select
        {{ id_from_url('url') }}  as fighter_id,
        {{ clean('fighter') }}    as fighter_name,
        {{ clean('height') }}     as height,
        {{ clean('weight') }}     as weight,
        {{ clean('reach') }}      as reach,
        {{ clean('stance') }}     as stance,
        {{ clean('dob') }}        as dob,
        row_number() over (partition by {{ id_from_url('url') }} order by _row_num) as dup_rank
    from {{ source('src', 'ufc_fighter_tott') }}
),

details as (
    select distinct on ({{ id_from_url('url') }})
        {{ id_from_url('url') }} as fighter_id,
        {{ clean('nickname') }}  as nickname
    from {{ source('src', 'ufc_fighter_details') }}
    order by {{ id_from_url('url') }}
)

select
    t.fighter_id,
    t.fighter_name,
    d.nickname,
    case when t.height ~ '^\d+'' \d+"$'
         then split_part(t.height, '''', 1)::int * 12 + regexp_replace(split_part(t.height, '''', 2), '\D', '', 'g')::int
    end                                                              as height_in,
    nullif(regexp_replace(coalesce(t.weight, ''), '\D', '', 'g'), '')::int as weight_lbs,
    nullif(regexp_replace(coalesce(t.reach, ''), '[^0-9.]', '', 'g'), '')::numeric::int as reach_in,
    case
        when t.stance in ('Orthodox', 'Southpaw', 'Switch') then t.stance
        when t.stance is null then null
        else 'Other'
    end                                                              as stance,
    to_date(t.dob, 'Mon DD, YYYY')                                   as dob
from tott t
left join details d on d.fighter_id = t.fighter_id
where t.dup_rank = 1
