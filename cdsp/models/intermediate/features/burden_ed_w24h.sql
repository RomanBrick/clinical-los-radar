{{ config(
    materialized='table',
    schema='intermediate'
) }}

/*
  Renal wedge: Operational lab burden 0-24h from ED arrival.
  Mirrors burden_0_6h but over the 24h ED window (and divides by 24).
*/

with labs as (
    select
        hadm_id,
        coalesce(sodium_count, 0)
      + coalesce(potassium_count, 0)
      + coalesce(bun_count, 0)
      + coalesce(creatinine_count, 0)
      + coalesce(wbc_count, 0)
      + coalesce(hematocrit_count, 0)
      + coalesce(platelets_count, 0)
      + coalesce(lactate_count, 0) as total_labs_ordered_w24h,

        coalesce(sodium_measured_flag, 0)
      + coalesce(potassium_measured_flag, 0)
      + coalesce(bun_measured_flag, 0)
      + coalesce(creatinine_measured_flag, 0)
      + coalesce(wbc_measured_flag, 0)
      + coalesce(hematocrit_measured_flag, 0)
      + coalesce(platelets_measured_flag, 0)
      + coalesce(lactate_measured_flag, 0) as unique_labs_ordered_w24h
    from {{ ref('labs_ed_w24h_dynamic') }}
)

select
    hadm_id,
    total_labs_ordered_w24h,
    unique_labs_ordered_w24h,
    round(total_labs_ordered_w24h / 24.0, 4) as labs_per_hour_w24h,
    case
        when unique_labs_ordered_w24h = 0 then 0
        else round(total_labs_ordered_w24h * 1.0 / unique_labs_ordered_w24h, 4)
    end as repeat_rate_w24h
from labs
order by hadm_id
