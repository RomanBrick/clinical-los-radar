# Renal Wedge Model — Metrics (24h, calibrated)

- Cohort: renal dysfunction in first 24h (creatinine>1.3 OR BUN>20.0), **53,792** admissions, base rate **41.0%**.
- Subject-level split: train 32,244 / cal 10,635 / test 10,913. Isotonic calibration on cal split.

| Model | ROC-AUC | PR-AUC | Brier | Top5% prec/lift | Top10% prec/lift |
|---|---|---|---|---|---|
| Logistic baseline | 0.722 | 0.623 | 0.205 | 80% / 1.90x | 74% / 1.76x |
| HistGradientBoosting | 0.736 | 0.642 | 0.201 | 82% / 1.95x | 76% / 1.80x |

**Note on targets:** at this base rate the contract's `Recall@Top10% > 0.6` is mathematically infeasible (ceiling ~24%). Report precision/lift at the operating point instead.