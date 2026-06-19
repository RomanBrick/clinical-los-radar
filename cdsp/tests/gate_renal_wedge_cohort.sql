-- Cohort integrity: every row in the training table must truly be renal cohort.
-- Fails (returns rows) if any training row does not satisfy the renal definition.

select
  hadm_id,
  creatinine_max,
  bun_max,
  renal_dysfunction_flag
from {{ ref('training_renal_wedge') }}
where renal_dysfunction_flag != 1
   or not (coalesce(creatinine_max, 0) > 1.3 or coalesce(bun_max, 0) > 20)
