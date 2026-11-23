{{ config(severity='warn') }}
-- The newest event should be less than 30 days old; otherwise upstream may have stalled.
select max(event_date) as latest_event
from {{ ref('stg_events') }}
having max(event_date) < current_date - 30
