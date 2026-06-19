{{
  config(
    materialized='table',
    indexes=[
      {'columns': ['hadm_id'], 'unique': True},
    ]
  )
}}

-- Phase 3: Create "longer stay" label using fixed P75 threshold
-- Joins: spine + threshold (ensures same threshold for train/test)
-- Output: 1 row per hadm_id with label flag

with threshold as (
  select
    p75_los_days,
    cohort_size,
    calculated_at,
    cohort_version
  from {{ ref('long_stay_threshold_p75') }}
)

select
  s.subject_id,
  s.hadm_id,
  s.los_days,
  t.p75_los_days,
  case 
    when s.los_days >= t.p75_los_days then 1 
    else 0 
  end as long_stay_flag,
  t.calculated_at,
  t.cohort_version
from {{ ref('encounter_spine_ed_inpatient') }} s
cross join threshold t
