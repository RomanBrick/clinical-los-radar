{{
  config(
    materialized='table',
    indexes=[
      {'columns': ['hadm_id'], 'unique': True},
    ]
  )
}}

with ed_admissions as (
  select
    e.stay_id,
    e.subject_id,
    e.hadm_id,
    e.ed_intime,
    e.ed_outtime,
    a.admittime,
    a.dischtime,
    a.hospital_expire_flag,
    -- Deduplicate: take earliest ED stay per hadm_id
    row_number() over (partition by e.hadm_id order by e.ed_intime asc) as ed_visit_seq
  from {{ ref('stg_edstays') }} e
  inner join {{ ref('stg_admissions') }} a
    on e.hadm_id = a.hadm_id
    and e.subject_id = a.subject_id
),

first_ed_stay as (
  select
    stay_id,
    subject_id,
    hadm_id,
    ed_intime,
    ed_outtime,
    admittime,
    dischtime,
    hospital_expire_flag
  from ed_admissions
  where ed_visit_seq = 1  -- Keep only first ED stay per admission
)

select
  stay_id,
  subject_id,
  hadm_id,
  ed_intime,
  ed_outtime,
  admittime,
  dischtime,
  hospital_expire_flag,
  -- Length of stay in days (from inpatient admission to discharge)
  -- Kept with high precision (no rounding) for accurate P75 percentile calculation
  (extract(epoch from (dischtime - admittime)) / 86400.0) as los_days,
  -- Length of stay rounded to 2 decimal places (for reporting)
  cast((extract(epoch from (dischtime - admittime)) / 86400.0) as decimal(10, 2)) as los_days_2dp,
  -- Window start and end for Phase 3 analysis
  ed_intime as window_start,
  cast((ed_intime + interval '6 hours') as timestamp) as window_end
from first_ed_stay
where ed_intime <= dischtime  -- ED arrival before discharge (no time travel)
  and dischtime > admittime  -- Positive LOS (dischtime after admission)
