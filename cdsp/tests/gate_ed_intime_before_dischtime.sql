-- Phase 3 Anti-Leakage Gate: ED arrival must be before hospital discharge
-- Returns violation rows: if any exist, test FAILS (as it should)
select *
from {{ ref('encounter_spine_ed_inpatient') }}
where ed_intime > dischtime
