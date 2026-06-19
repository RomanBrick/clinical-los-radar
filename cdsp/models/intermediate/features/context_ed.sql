{{ config(
    materialized='table',
    schema='intermediate'
) }}

/*
  Renal wedge: encounter context available at ED arrival (no leakage).
  - demographics: age, gender               (raw.patients)
  - admission context: type/insurance/...    (raw.admissions)
  - ED triage: acuity (ESI) + first vitals    (raw.ed_triage, via stay_id)

  All fields are known at/near ed_intime; none come from discharge.
  Categorical columns are kept raw (one-hot is done downstream in the trainer).
*/

with spine as (
    select hadm_id, subject_id, stay_id
    from {{ ref('encounter_spine_ed_inpatient') }}
)

select
    s.hadm_id,
    try_cast(p.anchor_age as double) as age,
    p.gender                         as gender,
    a.admission_type                 as admission_type,
    a.insurance                      as insurance,
    a.marital_status                 as marital_status,
    a.race                           as race,
    try_cast(t.acuity as double)      as triage_acuity,
    try_cast(t.heartrate as double)   as triage_hr,
    try_cast(t.resprate as double)    as triage_rr,
    try_cast(t.o2sat as double)       as triage_o2,
    try_cast(t.sbp as double)         as triage_sbp,
    try_cast(t.dbp as double)         as triage_dbp,
    try_cast(t.temperature as double) as triage_temp,
    try_cast(t.pain as double)        as triage_pain
from spine s
left join {{ source('raw', 'patients') }}  p on p.subject_id = s.subject_id
left join {{ source('raw', 'admissions') }} a on a.hadm_id   = s.hadm_id
left join {{ source('raw', 'ed_triage') }}  t on t.stay_id   = s.stay_id
