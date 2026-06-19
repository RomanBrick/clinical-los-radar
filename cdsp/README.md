# cdsp — dbt project (renal longer-stay wedge)

dbt + DuckDB models for the renal-dysfunction longer-stay wedge. Lineage:

```
staging (stg_*) → encounter_spine_ed_inpatient
  → {labs_ed_w24h_dynamic, burden_ed_w24h, context_ed}
  → renal_wedge_features
  → training_renal_wedge   (+ labels_long_stay_p75, splits_subject)
```

Anti-leakage and integrity checks live in `tests/` (e.g. `gate_labs_ed_w24h_anti_leakage`,
`gate_training_renal_wedge_subject_split_leakage`). See the repository-root README for
the full case study and results.

## Run
1. Copy `profiles.yml.example` to your dbt profiles dir and point it at a built
   MIMIC-IV DuckDB database (data not included — obtain via credentialed PhysioNet).
2. `dbt build --select +training_renal_wedge`  — builds the lineage and runs the gates.
