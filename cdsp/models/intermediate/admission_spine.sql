select
  a.hadm_id,
  a.subject_id,
  a.admittime,
  a.dischtime,
  a.hospital_expire_flag,
  p.is_male,
  p.anchor_age,
  -- Calculate length of stay in days
  extract(day from (a.dischtime - a.admittime)) as los_days
from {{ ref('stg_admissions') }} a
join {{ ref('stg_patients') }} p
  on a.subject_id = p.subject_id
