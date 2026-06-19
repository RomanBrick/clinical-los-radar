-- Hard gate: each subject must belong to exactly one split (no patient leakage).

with per_subject as (
  select
    subject_id,
    count(distinct split) as split_cnt
  from {{ ref('training_renal_wedge') }}
  group by subject_id
)

select
  subject_id,
  split_cnt
from per_subject
where split_cnt > 1
