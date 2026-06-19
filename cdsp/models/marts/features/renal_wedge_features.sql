{{ config(
    materialized='table',
    schema='marts'
) }}

/*
  Renal wedge feature mart (one row per ED->inpatient admission).

  Combines the 0-24h ED-anchored lab dynamics + lab burden + encounter context,
  and flags the renal-dysfunction cohort (creatinine_max > 1.3 OR bun_max > 20).

  The downstream training mart filters to renal_dysfunction_flag = 1.
*/

with f as (
    select * exclude (
        debug_min_charttime, debug_max_charttime,
        debug_ed_intime, debug_window_end, debug_dischtime
    )
    from {{ ref('labs_ed_w24h_dynamic') }}
),

sp as (
    select hadm_id, subject_id, ed_intime
    from {{ ref('encounter_spine_ed_inpatient') }}
)

select
    f.* ,
    sp.subject_id,
    sp.ed_intime,

    -- lab burden
    b.total_labs_ordered_w24h,
    b.unique_labs_ordered_w24h,
    b.labs_per_hour_w24h,
    b.repeat_rate_w24h,

    -- encounter context
    c.age,
    c.gender,
    c.admission_type,
    c.insurance,
    c.marital_status,
    c.race,
    c.triage_acuity,
    c.triage_hr,
    c.triage_rr,
    c.triage_o2,
    c.triage_sbp,
    c.triage_dbp,
    c.triage_temp,
    c.triage_pain,

    -- cohort flag
    case
        when coalesce(f.creatinine_max, 0) > 1.3
          or coalesce(f.bun_max, 0) > 20
        then 1 else 0
    end as renal_dysfunction_flag

from f
join sp on f.hadm_id = sp.hadm_id
left join {{ ref('burden_ed_w24h') }} b on b.hadm_id = f.hadm_id
left join {{ ref('context_ed') }} c on c.hadm_id = f.hadm_id
