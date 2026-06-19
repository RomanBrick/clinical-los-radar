select
  cast(l.hadm_id as bigint) as hadm_id,
  cast(l.itemid as integer) as itemid,
  cast(l.charttime as timestamp) as charttime,
  cast(l.valuenum as double) as valuenum,
  l.valuenum
from {{ source('raw', 'labevents') }} as l
where l.hadm_id is not null
