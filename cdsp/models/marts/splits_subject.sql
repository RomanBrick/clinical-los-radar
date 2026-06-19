-- filepath: models/marts/splits_subject.sql
-- Day 21: Deterministic train/calibration/test splits by subject_id
-- Purpose: Prevent patient leakage - same patient never in multiple splits
-- Key: Deterministic hashing ensures reproducibility

{{ config(
  materialized = 'table'
) }}

with subject_splits as (
  select distinct
    subject_id,
    case
      when mod(hash(subject_id), 100) < 60 then 'train'
      when mod(hash(subject_id), 100) < 80 then 'calibration'
      else 'test'
    end as split
  from {{ ref('admission_spine') }}
),

admissions_with_split as (
  select
    a.hadm_id,
    a.subject_id,
    s.split
  from {{ ref('admission_spine') }} a
  join subject_splits s using (subject_id)
)

select * from admissions_with_split
