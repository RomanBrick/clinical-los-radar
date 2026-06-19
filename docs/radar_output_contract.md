# Radar Output Contract (Phase 3)
## Prediction API Specification

**Status:** ✅ LOCKED (Day 1)  
**Effective Date:** 2026-02-19  
**Version:** 1.0

---

## 1. Output Structure

All predictions from the Phase 3 Longer Stay risk model return the following JSON contract:

```json
{
  "prediction_id": "string",
  "subject_id": "int",
  "hadm_id": "int",
  "ed_intime": "timestamp",
  "scored_at": "timestamp",
  
  "risk_long_stay": "float (0.0 to 1.0)",
  "tier": "string (Low | Medium | High)",
  
  "shap_top_reasons": [
    {
      "feature_name": "string",
      "shap_value": "float",
      "feature_value": "float or null"
    },
    ...  // up to 3 items
  ],
  
  "window_definition": {
    "window_start": "ed_intime",
    "window_end": "ed_intime + 6 hours",
    "duration_hours": 6
  },
  
  "model_version": "string",
  "model_id": "phase3_lgbm_longer_stay_v1",
  
  "metadata": {
    "alert_percentile_rank": "float (0 to 1)",
    "n_features_used": "int",
    "missing_features_count": "int",
    "calibration_method": "isotonic"
  }
}
```

---

## 2. Field Definitions

### Identity Fields
| Field | Type | Description |
|-------|------|-------------|
| `prediction_id` | UUID/String | Unique ID for this prediction (for audit) |
| `subject_id` | Integer | Patient identifier |
| `hadm_id` | Integer | Admission identifier |
| `ed_intime` | Timestamp | ED arrival time (anchor for window) |
| `scored_at` | Timestamp | When prediction was generated |

### Primary Prediction
| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `risk_long_stay` | Float | 0.0–1.0 | Probability patient will have LOS ≥ P75 |
| `tier` | String | Low, Medium, High | Operationally meaningful risk bucketing |

### Tier Definition Logic
```python
if risk_long_stay >= 0.10:           # Top 10%
    tier = "High"
elif risk_long_stay >= 0.05:         # Next 5%
    tier = "Medium"
else:
    tier = "Low"
```

**Rationale:** Percentile-based tiers allow operations to set alert budgets
- "Alert on all High-risk" ≈ 10% of ED admissions
- "Alert on High+Medium" ≈ 15% of ED admissions

### Explainability Fields
| Field | Type | Description |
|-------|------|-------------|
| `shap_top_reasons` | Array | Top 3 SHAP-based feature contributions (descending by abs(shap_value)) |
| `feature_name` | String | Human-readable feature name (e.g., "labs_per_hour_0_6h") |
| `shap_value` | Float | SHAP contribution to prediction (positive = increases risk, negative = decreases) |
| `feature_value` | Float or Null | Actual feature value for this patient (null if N/A) |

### Window Definition
| Field | Type | Description |
|-------|------|-------------|
| `window_start` | String | Always "ed_intime" |
| `window_end` | String | Always "ed_intime + 6 hours" |
| `duration_hours` | Integer | Always 6 |

### Model Metadata
| Field | Type | Description |
|-------|------|-------------|
| `model_version` | String | Semantic version (e.g., "1.0.0") |
| `model_id` | String | Frozen identifier for traceability |
| `alert_percentile_rank` | Float | 0–1; percentile position of this prediction in recent cohort |
| `n_features_used` | Integer | Number of features in final model |
| `missing_features_count` | Integer | Features that could not be computed (should be 0) |
| `calibration_method` | String | "isotonic" (as of Phase 3) |

---

## 3. Example Prediction

```json
{
  "prediction_id": "pred-2026-02-19-001234",
  "subject_id": 12345,
  "hadm_id": 67890,
  "ed_intime": "2026-02-19T08:30:00Z",
  "scored_at": "2026-02-19T09:15:00Z",
  
  "risk_long_stay": 0.78,
  "tier": "High",
  
  "shap_top_reasons": [
    {
      "feature_name": "labs_per_hour_0_6h",
      "shap_value": 0.25,
      "feature_value": 3.2
    },
    {
      "feature_name": "vitals_count_0_6h",
      "shap_value": 0.18,
      "feature_value": 12
    },
    {
      "feature_name": "labs_unique_0_6h",
      "shap_value": 0.15,
      "feature_value": 8
    }
  ],
  
  "window_definition": {
    "window_start": "ed_intime",
    "window_end": "ed_intime + 6 hours",
    "duration_hours": 6
  },
  
  "model_version": "1.0.0",
  "model_id": "phase3_lgbm_longer_stay_v1",
  
  "metadata": {
    "alert_percentile_rank": 0.92,
    "n_features_used": 42,
    "missing_features_count": 0,
    "calibration_method": "isotonic"
  }
}
```

---

## 4. Operational Interpretation Guide

### For ED Operations Manager

**IF Tier = "High" (top 10%):**
- ✅ Flag for **immediate case management review**
- ✅ Plan for extended bed hold / resource pre-allocation
- ✅ Consider early social work consult
- ❌ NOT: Change clinical treatment pathway

**IF Tier = "Medium" (next 5%):**
- ✅ Monitor; add to case management watch list
- ✅ Routine escalation triggers apply

**IF Tier = "Low" (remaining 85%):**
- ✅ Routine ED admission pathway
- ✅ No special operational actions

### Alert Budget Planning Example
```
Example ED with 150 admissions/day:

"High" tier (top 10%) = ~15 alerts/day
  → Can assign dedicated case manager (1 person = ~20 alerts/day capacity)

"High+Medium" tier (top 15%) = ~22 alerts/day
  → Requires 2 case managers on duty
```

---

## 5. Probability Calibration Guarantee

### What "78% risk" Means
```
If 100 patients similar to this one are scored at 0.78,
approximately 78 of them will experience a "longer stay" 
(LOS ≥ P75 in their cohort).
```

### Calibration Method
- **Isotonic or Platt** fit on a held-out calibration split; the lower-Brier one is kept
- Primary calibration metric: **ECE (10-bin) < 0.05**
- Brier score is reported but not gated (its floor is bounded by base rate; see §8)

### Caveat
- Calibration assumes **similar population** to training cohort
- Different hospitals/time periods may show different calibration
- Always validate on new deployment environment

---

## 6. Data Quality Signals in Output

### When to Trust This Prediction

✅ `missing_features_count == 0`
- All features successfully computed; normal reliability

⚠️ `missing_features_count > 0`
- Some features could not be computed (e.g., no vitals in window)
- **Action:** Flag for human review; consider prediction unreliable
- **Do NOT alert** if missing features relate to key risk drivers

---

## 7. Audit & Compliance

### What to Log
Every prediction output should be logged with:
- Timestamp of generation (`scored_at`)
- Unique `prediction_id` (for linkage to EHR)
- Model version (for reproducibility)
- All SHAP explanations (for interpretability review)

### Data Retention
- Keep predictions for 7 years (medical record standard)
- Link to actual outcome (whether patient had "long stay" or not)
- Compute retrospective calibration metrics (e.g., monthly)

---

## 8. Performance Targets (By Design)

> **Revised (renal-wedge validation).** The original targets below assumed a
> recall budget that is **mathematically impossible** at this cohort's prevalence.
> When a fraction `q` of patients is alerted, the maximum achievable
> `Recall@TopQ` is `min(q, base_rate) / base_rate`. For the renal cohort
> (base rate ~0.41) the ceiling on `Recall@Top10%` is `0.10/0.41 ≈ 0.24` — so a
> ">60%" recall target can never be met regardless of model quality. We therefore
> evaluate at fixed **alert budgets** using **precision and lift** (operationally
> what a worklist owner cares about), and measure calibration with **ECE**, not a
> prevalence-bound Brier threshold.

### Operating-point targets (prevalence-aware)
| Metric | Target | Notes |
|--------|--------|-------|
| ROC-AUC | ≥ 0.70 (beat logistic baseline) | Overall ranking quality |
| PR-AUC | ≥ 1.4 × base rate | Beats the constant-rate classifier |
| Precision@Top5% | ≥ 1.8 × base rate (lift) | High-confidence worklist, low alert fatigue |
| Precision@Top10% | ≥ 1.6 × base rate (lift) | Broader alert budget |
| ECE (10-bin) | < 0.05 | Calibration quality (replaces Brier threshold) |
| Brier Score | reported, not gated | Bounded by base rate; see note above |

### Validated results (renal wedge, 24h, HistGB, isotonic)
| Population | ROC-AUC | Top5% precision / lift | Top10% precision / lift | base |
|---|---|---|---|---|
| MIMIC-IV (ED→inpatient, single center) | 0.736 | 82% / 1.95× | 76% / 1.80× | 41% |
| eICU (ICU, ~200 centers) — external | 0.700 | 60% / 2.37× | 55% / 2.17× | 25% |

> Retrained on the multi-center eICU population, the renal-cohort signal **holds
> (0.736 → 0.700)**, materially de-risking the single-center concern. ECE 0.018
> (MIMIC) / 0.008 (eICU). Source: `docs/renal_wedge_model_metrics.json`,
> `docs/eicu_external_validation.json`.

---

## 9. Version Control & Updates

### When Output Contract Changes
1. **Increment `model_version`** (semantic versioning)
2. **Update this document** with date and change summary
3. **Notify stakeholders** of schema changes
4. **Test backward compatibility** (if possible)

### Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-19 | Initial contract; locked at Day 1 |

---

## 10. Exception Handling

### What to Do If Prediction Fails

```json
{
  "prediction_id": "pred-FAILED-001",
  "hadm_id": 67890,
  "error": "Missing vital data in window",
  "error_code": "INSUFFICIENT_VITALS",
  "scored_at": "2026-02-19T09:15:00Z"
}
```

**Error Codes:**
- `INSUFFICIENT_VITALS` – No vital signs in 0–6h window
- `INSUFFICIENT_LABS` – No lab values in 0–6h window
- `MISSING_ENCOUNTER` – No encounter record found
- `PREDICTION_SERVICE_ERROR` – Model inference failed

**Operational Response:**
- Log error with `prediction_id`
- Escalate to data engineering for investigation
- Do NOT return a default "Low" prediction

---

## Appendix: FAQ

### Q: Why not show confidence intervals?
A: Calibration curves + top-3 SHAP features provide sufficient uncertainty context for operational decisions. Full credible intervals added in Phase 4 (if Bayesian model selected).

### Q: Can I use this for individual treatment decisions?
A: **NO.** This is operational triage (bed/staffing), not clinical recommendation. Physicians must use independent clinical judgment.

### Q: What if this prediction disagrees with clinical assessment?
A: **Trust clinical judgment.** Model is advisory only. Always document override decisions for future model refinement.
