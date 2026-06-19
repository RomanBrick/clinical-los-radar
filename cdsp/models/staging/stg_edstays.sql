select
  cast(stay_id as bigint) as stay_id,
  cast(subject_id as bigint) as subject_id,
  cast(hadm_id as bigint) as hadm_id,
  cast(intime as timestamp) as ed_intime,
  cast(outtime as timestamp) as ed_outtime
from {{ source('raw','edstays') }}
where hadm_id is not null  -- Only ED visits that link to inpatient admissions
