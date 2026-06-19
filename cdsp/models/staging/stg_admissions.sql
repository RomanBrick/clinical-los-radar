select
  cast(hadm_id as bigint) as hadm_id,
  cast(subject_id as bigint) as subject_id,
  cast(admittime as timestamp) as admittime,
  cast(dischtime as timestamp) as dischtime,
  cast(hospital_expire_flag as integer) as hospital_expire_flag
from {{ source('raw','admissions') }}

