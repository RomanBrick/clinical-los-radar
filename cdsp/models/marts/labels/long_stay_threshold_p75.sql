{{
  config(
    materialized='table'
  )
}}

-- Phase 3: Compute P75 threshold for "longer stay" classification
-- Returns: 1 row with p75_los_days value and metadata
-- Purpose: Ensures train/test use same threshold (prevents leakage)

select
  percentile_cont(0.75) within group (order by los_days) as p75_los_days,
  count(*) as cohort_size,
  current_timestamp as calculated_at,
  'phase3_ed_0_6h_p75' as cohort_version
from {{ ref('encounter_spine_ed_inpatient') }}
