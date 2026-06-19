-- Phase 3 Anti-Leakage Gate: Check positive rate is within expected P75 range
-- Expected: ~25% (0.75 → 0.25 positives), allowing 2-3% margin for ties
-- Acceptable range: 22-28%

select 
  count(*) as violation_count,
  round(100.0 * sum(case when long_stay_flag = 1 then 1 else 0 end) / count(*), 2) as positive_rate_pct
from {{ ref('labels_long_stay_p75') }}
having 
  round(100.0 * sum(case when long_stay_flag = 1 then 1 else 0 end) / count(*), 2) < 22.0
  or round(100.0 * sum(case when long_stay_flag = 1 then 1 else 0 end) / count(*), 2) > 28.0
