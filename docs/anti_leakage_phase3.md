# Anti-leakage controls (Phase 3)

This document summarizes leakage controls implemented for the 0-6h ED pipeline.

## Scope

- Target: long stay prediction (`long_stay_flag`) from first 6 hours after ED arrival.
- Feature window: `[ed_intime, ed_intime + 6h)`.
- Core entities:
  - ED event ownership via `stay_id` (vitals/triage)
  - Hospital admission via `hadm_id` (labs, labels)
  - Subject-level splitting via `subject_id`

## Hard controls

### 1) Correct ED encounter ownership

- `encounter_spine_ed_inpatient` carries `stay_id`.
- `vitals_0_6h_dynamic` joins triage and vital signs to spine using `stay_id` (+ subject safety).
- Gate: `gate_vitals_correct_stay_mapping.sql`.

### 2) Strict temporal windowing

- Vitals/labs are filtered to `charttime >= ed_intime and charttime < window_end`.
- Gates:
  - `gate_vitals_anti_leakage.sql`
  - `gate_labs_0_6h_anti_leakage.sql`
  - `gate_radar_features_0_6h_within_window.sql`

### 3) No post-discharge data in features

- Lab source constraints prevent post-discharge rows.
- Final feature mart excludes discharge/LOS-like columns.
- Gates:
  - `gate_labs_0_6h_no_post_discharge.sql`
  - `gate_no_discharge_info_in_radar_features_0_6h.sql`

### 4) Label isolation

- Feature mart (`radar_features_0_6h`) does not contain target label columns.
- Labels are joined only in training mart (`training_long_stay_0_6h`).
- Gate: `gate_no_label_in_radar_features_0_6h.sql`.

### 5) Subject-level split integrity

- Split assignment is deterministic and subject-based in `training_long_stay_0_6h`.
- A subject can appear in only one split.
- Gate: `gate_training_long_stay_0_6h_subject_split_leakage.sql`.

## Operational notes

- Day 4-6 models provide component-level leakage diagnostics (`debug_max_charttime`).
- Day 7 composes only 0-6h bounded component outputs.
- New models:
  - `marts/features/radar_features_0_6h.sql`
  - `marts/training/training_long_stay_0_6h.sql`
