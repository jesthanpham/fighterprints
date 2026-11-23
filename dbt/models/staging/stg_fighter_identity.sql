select fight_id, name_as_written, fighter_id, method
from {{ source('src', 'fighter_identity') }}
