# eICU External Validation — Renal Wedge (retrained recipe)

- Multi-center eICU (~200 US hospitals). Renal cohort: **84,507** ICU stays, prolonged-LOS rate **25.0%** (P75 = 12.4 d).
- Patient-level split (no `uniquepid` in two splits): train 50,654 / cal 16,912 / test 16,941. 121 features.

| Model | ROC-AUC | PR-AUC | ECE | Top5% prec/lift |
|---|---|---|---|---|
| Logistic baseline | 0.658 | 0.379 | 0.012 | 50% / 1.98x |
| HistGradientBoosting | 0.700 | 0.435 | 0.008 | 60% / 2.37x |

**Generalization:** retrained on a different population, the renal-cohort + first-24h-labs signal ranks prolonged stays at ROC-AUC 0.700 — vs MIMIC 0.736, supporting cross-center generalization.

> Generalization check (retrain same recipe), **not** an apples-to-apples replay: populations (ICU vs ED→inpatient) and schemas differ.
