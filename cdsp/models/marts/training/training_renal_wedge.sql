{{ config(
    materialized='table',
    schema='marts'
) }}

/*
  Renal wedge training table: renal cohort features + long-stay label + split.

  - cohort:  renal_dysfunction_flag = 1 (creatinine_max > 1.3 OR bun_max > 20, 0-24h)
  - label:   long_stay_flag from labels_long_stay_p75 (LOS >= cohort P75)
  - split:   subject-level split from splits_subject (no subject in two splits)

  This is the table the renal-wedge model trains on.
*/

select
    ff.*,
    lbl.long_stay_flag,
    lbl.los_days,
    spl.split
from {{ ref('renal_wedge_features') }} ff
inner join {{ ref('labels_long_stay_p75') }} lbl on ff.hadm_id = lbl.hadm_id
inner join {{ ref('splits_subject') }} spl on ff.hadm_id = spl.hadm_id
where ff.renal_dysfunction_flag = 1
order by ff.hadm_id
