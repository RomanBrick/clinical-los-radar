select
  cast(subject_id as bigint) as subject_id,

  case
    when gender = 'M' then 1
    when gender = 'F' then 0
    else null
  end as is_male,

  cast(anchor_age as integer) as anchor_age
from {{ source('raw','patients') }}
