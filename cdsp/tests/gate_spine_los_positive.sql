-- Phase 3 Anti-Leakage Gate: LOS must be positive (dischtime > admittime)
-- Returns violation rows: if any exist, test FAILS (as it should)
select *
from {{ ref('encounter_spine_ed_inpatient') }}
where dischtime <= admittime
   or los_days <= 0
