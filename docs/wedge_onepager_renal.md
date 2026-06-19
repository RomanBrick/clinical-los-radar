# Renal Early-Risk Radar — Wedge One-Pager

**An operational early-warning tool that flags ED admissions with renal dysfunction
who are at high risk of a longer hospital stay — in time for case management to act.**

*Operational decision support, not a clinical/treatment device. Status: pre-pilot
prototype validated retrospectively on MIMIC-IV (single center). Figures below are
computed from that dataset and clearly labeled where they are assumptions.*

---

## 1. Problem (grounded in AHA "The Cost of Caring," April 2025)

Hospital margins are crushed by **length of stay and throughput**, not just price:
- Labor is **56%** of hospital cost; beds and case-management capacity are the constraint.
- Medicare Advantage patients now have substantially **longer stays** with **lower**
  reimbursement; **discharge delays to post-acute care have roughly doubled** vs.
  Traditional Medicare (2019–2024), driving **ED crowding** and excess bed-days.
- **Acute renal failure** is named in the report among the fastest-growing,
  costliest utilization drivers (**+56.5%** spending, **+50%** encounters).

Today, the patients who will occupy a bed for a week are often identified **too late** —
after the stay is already long.

## 2. Wedge (deliberately narrow)

| | |
|---|---|
| **Buyer** | Case Management / ED Operations leadership (operational budget) |
| **Cohort** | ED→inpatient admissions with **renal dysfunction in the first 24h** (creatinine > 1.3 or BUN > 20) |
| **Question** | "Which of these patients is at high risk of a longer stay (LOS ≥ P75)?" |
| **Output** | Day-1 risk score + tier (Low/Med/High) + top-3 reasons (SHAP) |

Not "predict LOS for all patients." One cohort, one user, one daily decision.

## 3. The action (this is the product — not the score)

A score alone changes nothing. The radar fires a **day-1 case-management trigger** for
high-risk renal patients to start, earlier than usual:
- nephrotoxic-medication review,
- volume/fluid-status follow-up scheduling,
- **early post-acute placement & prior-authorization paperwork** (the documented
  bottleneck behind long stays).

The product ships the worklist + reasons + alert-budget controls — not a raw probability.

## 4. Evidence from data (MIMIC-IV, ED→inpatient, first 24h)

| Metric | Value |
|---|---|
| ED→inpatient admissions | 202,337 |
| Early-creatinine coverage (24h) | **66.3%** |
| Renal-dysfunction cohort | **53,802 (26.6%)** |
| Prolonged-LOS rate, renal vs. overall | **41.0% vs. 25.0% (1.64× lift)** |
| Excess bed-days per renal admission | **2.22** (median basis) |
| Aggregate excess bed-days at risk | ~119,560 |
| $ at risk in renal cohort | **~$298.9M** (dataset lifetime, single center) |

The lift is **dose-responsive** (stricter renal thresholds → 44%→51% prolonged rate),
which argues the signal is real, not an artifact. The signal holds identically at the
6h and 24h windows (1.61× vs 1.64×).

### Model + external validation

A calibrated model on this cohort ranks long-stay risk well, and — critically — the
signal **generalizes to a different, multi-center population**:

| Population | ROC-AUC | Top-5% precision / lift | ECE | base |
|---|---|---|---|---|
| MIMIC-IV (ED→inpatient, single center) | **0.736** | **82% / 1.95×** | 0.018 | 41% |
| eICU (ICU, ~200 US hospitals) — external | **0.700** | 60% / **2.37×** | 0.008 | 25% |

Retrained on the multi-center eICU population, the renal-cohort signal **holds
(0.736 → 0.700)**, materially de-risking the single-center concern. Probabilities
are well-calibrated (ECE 0.018 MIMIC / 0.008 eICU); per-site
recalibration is part of deployment. (Recall@TopK is prevalence-capped, so we report
precision/lift at fixed alert budgets, not a fixed recall target.)

## 5. Economics — break-even, not a savings claim

The "draw an early creatinine" protocol is economically trivial:

| | |
|---|---|
| Protocol cost (early creatinine for the 33.7% coverage gap) | **~$681K** |
| Protocol cost as share of $ at risk | **0.23%** |
| LOS reduction needed to pay back the entire protocol | **~0.12 hours / patient** |

| Excess-LOS reduction | $ saved (lifetime) | ROI vs. protocol |
|---|---|---|
| 5% | ~$14.9M | 22× |
| 10% | ~$29.9M | 44× |
| 20% | ~$59.8M | 88× |

**Illustrative annualized (÷ ~10y, one large academic center):** ~$30M/yr at risk;
at a 10% reduction ≈ **$3M/yr saved** against ≈ $68K/yr protocol cost.

> The test cost is negligible. The **only** number that matters is the achievable
> LOS reduction — which is **unproven here** and is precisely what the pilot measures.

## 6. Why now / why this team

- **Tailwind:** throughput & discharge-delay pain is board-level in 2025 (AHA).
- **Engineering moat-in-progress:** the pipeline already enforces hard anti-leakage
  gates, subject-level splits, frozen label thresholds, calibrated probabilities, and
  an audited output contract — governance that most prototypes lack and that shortens
  hospital security/clinical review.

## 7. Competition & honest moat

Epic/Oracle (own the data + clinician desktop), Qventus, LeanTaaS, Bayesian Health.
**The model is a commodity** (MIMIC weights don't transfer without recalibration).
The defensible moat is **workflow integration + a prospective proof of LOS reduction +
data access via a design partner** — none of which is the model.

## 8. Regulatory posture

Positioned as an **operational resource-management tool** (bed/staffing/case-management
prioritization), it is likely **outside FDA medical-device scope**. The moment it
recommends treatment it becomes regulated Clinical Decision Support — so the wedge
stays strictly operational.

## 9. Risks & unknowns (stated up front)

- **Causal benefit unproven:** earlier information may not shorten stays; many long
  stays are post-acute/prior-auth driven and an early creatinine does not fix them.
- **Multi-center evidence, retrospective only:** validated on MIMIC-IV (single center)
  AND eICU (~200 centers) — generalization is shown, but all data is retrospective.
- **"Prescribe a lab" nudge:** protocolizing an early draw touches clinical order sets;
  must be framed as operational standard work, not treatment guidance.
- **Sickest patients already get early labs:** the protocol mainly closes the tail.

## 10. The ask / next step

**One design-partner hospital** for a prospective pilot that measures the single
unknown: *does day-1 renal-risk flagging + earlier case management reduce excess LOS,
and by how much?*

Data needed from the partner to make it real (absent in MIMIC):
medically-ready timestamps, case-management decision times, bed-management and
prior-authorization events, discharge-delay reason codes.

---

### Lean Canvas (summary)

| Block | Content |
|---|---|
| **Problem** | Long stays / ED crowding / discharge delays crush margin; long-stayers found too late |
| **Customer** | Case Management & ED Operations leadership (one hospital) |
| **Cohort** | ED→inpatient with renal dysfunction in first 24h (26.6% of admits) |
| **Unique value** | Day-1, calibrated, explainable long-stay risk for a high-yield cohort, wired to action |
| **Solution** | Risk tier + top-3 reasons + case-management worklist + alert budget |
| **Channels** | Design partner → pilot → service line → EHR marketplace |
| **Revenue** | Per-bed / per-admission SaaS, justified by bed-days saved |
| **Cost** | Integration (FHIR), recalibration per site, security (SOC2/HITRUST) |
| **Key metric** | Excess bed-days avoided per flagged renal admission |
| **Moat** | Workflow + prospective proof + data access (not the model) |
