{{ config(
    materialized='table',
    schema='intermediate'
) }}

/*
  Renal wedge: Labs Features 0-24h from ED arrival, with dynamic aggregations.

  Faithful clone of labs_0_6h_dynamic but with a 24h window (renal labs land
  late: median first creatinine ~14h after ED arrival, so 6h is too tight).

  Rules:
  - Join through ED->inpatient encounter spine by hadm_id
  - Window: charttime >= ed_intime AND charttime < ed_intime + 24h
  - No post-discharge labs
  - For single measurement, delta = 0

  Core labs: sodium, potassium, BUN, creatinine, WBC, hematocrit, platelets, lactate
*/

with spine as (
    select
        hadm_id,
        subject_id,
        ed_intime,
        ed_intime + interval '24 hours' as window_end,
        dischtime
    from {{ ref('encounter_spine_ed_inpatient') }}
),

core_lab_map as (
    select * from (
        values
            (50983, 'sodium'),
            (50971, 'potassium'),
            (51006, 'bun'),
            (50912, 'creatinine'),
            (51301, 'wbc'),
            (51221, 'hematocrit'),
            (51265, 'platelets'),
            (50813, 'lactate'),
            (52442, 'lactate'),
            (53154, 'lactate')
    ) as t(itemid, lab_name)
),

labs_window as (
    select
        sp.hadm_id,
        sp.subject_id,
        sp.ed_intime,
        sp.window_end,
        sp.dischtime,
        l.charttime,
        l.itemid,
        cl.lab_name,
        l.valuenum
    from {{ ref('stg_labevents') }} l
    inner join spine sp
        on l.hadm_id = sp.hadm_id
    inner join core_lab_map cl
        on l.itemid = cl.itemid
    where l.valuenum is not null
      and l.charttime >= sp.ed_intime
      and l.charttime < sp.window_end
      and (sp.dischtime is null or l.charttime <= sp.dischtime)
),

labs_with_endpoints as (
    select
        hadm_id,
        lab_name,
        charttime,
        valuenum,
        first_value(valuenum) over (
            partition by hadm_id, lab_name
            order by charttime
        ) as lab_first,
        last_value(valuenum) over (
            partition by hadm_id, lab_name
            order by charttime
            rows between unbounded preceding and unbounded following
        ) as lab_last
    from labs_window
),

lab_agg as (
    select
        hadm_id,
        lab_name,
        count(*) as value_count,
        min(valuenum) as value_min,
        max(valuenum) as value_max,
        round(avg(valuenum), 2) as value_mean,
        any_value(lab_first) as value_first,
        any_value(lab_last) as value_last,
        case
            when count(*) > 1 then round(any_value(lab_last) - any_value(lab_first), 2)
            else 0
        end as value_delta,
        case
            when count(*) > 0 then round(max(valuenum) - min(valuenum), 2)
            else 0
        end as value_range
    from labs_with_endpoints
    group by hadm_id, lab_name
),

debug_window as (
    select
        hadm_id,
        min(charttime) as debug_min_charttime,
        max(charttime) as debug_max_charttime
    from labs_window
    group by hadm_id
),

final as (
    select
        sp.hadm_id,

        coalesce(max(case when la.lab_name = 'sodium' then 1 end), 0) as sodium_measured_flag,
        coalesce(max(case when la.lab_name = 'sodium' then la.value_count end), 0) as sodium_count,
        max(case when la.lab_name = 'sodium' then la.value_min end) as sodium_min,
        max(case when la.lab_name = 'sodium' then la.value_max end) as sodium_max,
        max(case when la.lab_name = 'sodium' then la.value_mean end) as sodium_mean,
        max(case when la.lab_name = 'sodium' then la.value_first end) as sodium_first,
        max(case when la.lab_name = 'sodium' then la.value_last end) as sodium_last,
        coalesce(max(case when la.lab_name = 'sodium' then la.value_delta end), 0) as sodium_delta,
        coalesce(max(case when la.lab_name = 'sodium' then la.value_range end), 0) as sodium_range,

        coalesce(max(case when la.lab_name = 'potassium' then 1 end), 0) as potassium_measured_flag,
        coalesce(max(case when la.lab_name = 'potassium' then la.value_count end), 0) as potassium_count,
        max(case when la.lab_name = 'potassium' then la.value_min end) as potassium_min,
        max(case when la.lab_name = 'potassium' then la.value_max end) as potassium_max,
        max(case when la.lab_name = 'potassium' then la.value_mean end) as potassium_mean,
        max(case when la.lab_name = 'potassium' then la.value_first end) as potassium_first,
        max(case when la.lab_name = 'potassium' then la.value_last end) as potassium_last,
        coalesce(max(case when la.lab_name = 'potassium' then la.value_delta end), 0) as potassium_delta,
        coalesce(max(case when la.lab_name = 'potassium' then la.value_range end), 0) as potassium_range,

        coalesce(max(case when la.lab_name = 'bun' then 1 end), 0) as bun_measured_flag,
        coalesce(max(case when la.lab_name = 'bun' then la.value_count end), 0) as bun_count,
        max(case when la.lab_name = 'bun' then la.value_min end) as bun_min,
        max(case when la.lab_name = 'bun' then la.value_max end) as bun_max,
        max(case when la.lab_name = 'bun' then la.value_mean end) as bun_mean,
        max(case when la.lab_name = 'bun' then la.value_first end) as bun_first,
        max(case when la.lab_name = 'bun' then la.value_last end) as bun_last,
        coalesce(max(case when la.lab_name = 'bun' then la.value_delta end), 0) as bun_delta,
        coalesce(max(case when la.lab_name = 'bun' then la.value_range end), 0) as bun_range,

        coalesce(max(case when la.lab_name = 'creatinine' then 1 end), 0) as creatinine_measured_flag,
        coalesce(max(case when la.lab_name = 'creatinine' then la.value_count end), 0) as creatinine_count,
        max(case when la.lab_name = 'creatinine' then la.value_min end) as creatinine_min,
        max(case when la.lab_name = 'creatinine' then la.value_max end) as creatinine_max,
        max(case when la.lab_name = 'creatinine' then la.value_mean end) as creatinine_mean,
        max(case when la.lab_name = 'creatinine' then la.value_first end) as creatinine_first,
        max(case when la.lab_name = 'creatinine' then la.value_last end) as creatinine_last,
        coalesce(max(case when la.lab_name = 'creatinine' then la.value_delta end), 0) as creatinine_delta,
        coalesce(max(case when la.lab_name = 'creatinine' then la.value_range end), 0) as creatinine_range,

        coalesce(max(case when la.lab_name = 'wbc' then 1 end), 0) as wbc_measured_flag,
        coalesce(max(case when la.lab_name = 'wbc' then la.value_count end), 0) as wbc_count,
        max(case when la.lab_name = 'wbc' then la.value_min end) as wbc_min,
        max(case when la.lab_name = 'wbc' then la.value_max end) as wbc_max,
        max(case when la.lab_name = 'wbc' then la.value_mean end) as wbc_mean,
        max(case when la.lab_name = 'wbc' then la.value_first end) as wbc_first,
        max(case when la.lab_name = 'wbc' then la.value_last end) as wbc_last,
        coalesce(max(case when la.lab_name = 'wbc' then la.value_delta end), 0) as wbc_delta,
        coalesce(max(case when la.lab_name = 'wbc' then la.value_range end), 0) as wbc_range,

        coalesce(max(case when la.lab_name = 'hematocrit' then 1 end), 0) as hematocrit_measured_flag,
        coalesce(max(case when la.lab_name = 'hematocrit' then la.value_count end), 0) as hematocrit_count,
        max(case when la.lab_name = 'hematocrit' then la.value_min end) as hematocrit_min,
        max(case when la.lab_name = 'hematocrit' then la.value_max end) as hematocrit_max,
        max(case when la.lab_name = 'hematocrit' then la.value_mean end) as hematocrit_mean,
        max(case when la.lab_name = 'hematocrit' then la.value_first end) as hematocrit_first,
        max(case when la.lab_name = 'hematocrit' then la.value_last end) as hematocrit_last,
        coalesce(max(case when la.lab_name = 'hematocrit' then la.value_delta end), 0) as hematocrit_delta,
        coalesce(max(case when la.lab_name = 'hematocrit' then la.value_range end), 0) as hematocrit_range,

        coalesce(max(case when la.lab_name = 'platelets' then 1 end), 0) as platelets_measured_flag,
        coalesce(max(case when la.lab_name = 'platelets' then la.value_count end), 0) as platelets_count,
        max(case when la.lab_name = 'platelets' then la.value_min end) as platelets_min,
        max(case when la.lab_name = 'platelets' then la.value_max end) as platelets_max,
        max(case when la.lab_name = 'platelets' then la.value_mean end) as platelets_mean,
        max(case when la.lab_name = 'platelets' then la.value_first end) as platelets_first,
        max(case when la.lab_name = 'platelets' then la.value_last end) as platelets_last,
        coalesce(max(case when la.lab_name = 'platelets' then la.value_delta end), 0) as platelets_delta,
        coalesce(max(case when la.lab_name = 'platelets' then la.value_range end), 0) as platelets_range,

        coalesce(max(case when la.lab_name = 'lactate' then 1 end), 0) as lactate_measured_flag,
        coalesce(max(case when la.lab_name = 'lactate' then la.value_count end), 0) as lactate_count,
        max(case when la.lab_name = 'lactate' then la.value_min end) as lactate_min,
        max(case when la.lab_name = 'lactate' then la.value_max end) as lactate_max,
        max(case when la.lab_name = 'lactate' then la.value_mean end) as lactate_mean,
        max(case when la.lab_name = 'lactate' then la.value_first end) as lactate_first,
        max(case when la.lab_name = 'lactate' then la.value_last end) as lactate_last,
        coalesce(max(case when la.lab_name = 'lactate' then la.value_delta end), 0) as lactate_delta,
        coalesce(max(case when la.lab_name = 'lactate' then la.value_range end), 0) as lactate_range,

        1 - coalesce(max(case when la.lab_name = 'sodium' then 1 end), 0) as sodium_missing,
        1 - coalesce(max(case when la.lab_name = 'potassium' then 1 end), 0) as potassium_missing,
        1 - coalesce(max(case when la.lab_name = 'bun' then 1 end), 0) as bun_missing,
        1 - coalesce(max(case when la.lab_name = 'creatinine' then 1 end), 0) as creatinine_missing,
        1 - coalesce(max(case when la.lab_name = 'wbc' then 1 end), 0) as wbc_missing,
        1 - coalesce(max(case when la.lab_name = 'hematocrit' then 1 end), 0) as hematocrit_missing,
        1 - coalesce(max(case when la.lab_name = 'platelets' then 1 end), 0) as platelets_missing,
        1 - coalesce(max(case when la.lab_name = 'lactate' then 1 end), 0) as lactate_missing,

        dw.debug_min_charttime,
        dw.debug_max_charttime,
        sp.ed_intime as debug_ed_intime,
        sp.window_end as debug_window_end,
        sp.dischtime as debug_dischtime
    from spine sp
    left join lab_agg la
        on sp.hadm_id = la.hadm_id
    left join debug_window dw
        on sp.hadm_id = dw.hadm_id
    group by
        sp.hadm_id,
        dw.debug_min_charttime,
        dw.debug_max_charttime,
        sp.ed_intime,
        sp.window_end,
        sp.dischtime
)

select *
from final
order by hadm_id
