select
    {{ id_from_url('url') }}                          as event_id,
    {{ clean('event') }}                              as event_name,
    to_date({{ clean('date') }}, 'FMMonth DD, YYYY')  as event_date,
    {{ clean('location') }}                           as location
from {{ source('src', 'ufc_event_details') }}
