-- Anti-leakage gate: no lab measurements outside [ed_intime, ed_intime + 24h)
-- Fails (returns rows) if any admission has a charttime before ED arrival
-- or at/after the 24h window end.

select
  hadm_id,
  debug_min_charttime,
  debug_ed_intime,
  debug_max_charttime,
  debug_window_end
from {{ ref('labs_ed_w24h_dynamic') }}
where (debug_min_charttime is not null and debug_min_charttime < debug_ed_intime)
   or (debug_max_charttime is not null and debug_max_charttime >= debug_window_end)
