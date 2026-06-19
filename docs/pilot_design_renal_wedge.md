# Prospective Pilot Design — Renal Early-Risk Radar (short form)

**One question this pilot answers:** *Does a day-1 renal-risk flag + earlier case
management reduce excess length of stay (LOS) for the renal cohort — and by how much?*

Everything else (cohort signal, model discrimination, cross-center generalization,
economics) is already established retrospectively on MIMIC-IV and eICU. The **only
unproven link** is the causal one: earlier information → earlier action → shorter
stay. That is what a prospective pilot must measure.

---

## 0. Theory of change (why this could work)

The flag does **not** treat anyone and does not need to. Its only job is to
**prioritize a scarce resource — case management — one day earlier.**

There are two possible mechanisms; we deliberately bet on the operational one:

| | Clinical path (NOT our bet) | Operational path (our bet) |
|---|---|---|
| Mechanism | high creatinine → clinician treats kidney faster | flag → CM starts discharge / post-acute / prior-auth on day 1 |
| Who acts | physician | case manager |
| Does the model add value? | little — the clinician already sees the lab | yes — ranks *all* admits for limited CM capacity, ~1 day earlier |
| Hits the documented bottleneck (AHA: post-acute + prior-auth delays)? | no | **yes** |
| FDA exposure | yes (influences treatment) | no (operational resource management) |

**Causal chain we test:**
protocolized early creatinine (~6h) → calibrated renal-risk flag on the **day-1**
worklist → case manager starts **post-acute placement + prior-authorization +
discharge documentation in parallel from day 1** (instead of day 4–5) → fewer idle
"waiting-for-discharge" bed-days at the **end** of the stay.

**Why it scales with hospital size:** the model is a *triage filter* for a limited CM
team. At a high-volume hospital (~150+ admits/day) CM cannot work up everyone;
ranking the ~10% who will actually stay long, **one day earlier**, is where a single
day × many patients compounds into millions. At a low-volume hospital the
prioritization matters far less — so the wedge targets large, high-throughput systems.

**Honest:** this chain is plausible and aims at the *real* bottleneck, but it is
**unproven**. Prior "generic" LOS interventions often failed precisely because they
did not target the discharge bottleneck. The pilot's job is to measure the size of
the effect — or its absence.

---

## 1. Hypothesis

- **H1 (primary):** Among ED→inpatient adults with renal dysfunction in the first
  24h, high-risk flagging + an earlier case-management trigger reduces mean LOS vs
  usual care.
- **H0:** No difference in LOS.

## 2. Population / cohort

- Adults admitted ED→inpatient.
- **Renal cohort:** creatinine_max > 1.3 mg/dL **OR** BUN_max > 20 mg/dL within 24h
  of ED arrival (the validated wedge definition).
- Exclusions: comfort-care/hospice at admission, expected <24h stay, transfers in.

## 3. Intervention vs control

| | |
|---|---|
| **Intervention** | High-tier patients (top ~10% risk) appear on the case-management worklist on day 1 with top-3 reasons. CM starts **early**: nephrotoxic-med review, volume follow-up scheduling, and **early post-acute placement + prior-auth initiation**. |
| **Control** | Usual care (no early flag). |
| **Not changed** | Clinical/treatment decisions. This is operational prioritization only. |

## 4. Study design (recommended)

- **Stepped-wedge cluster** by unit/week: units cross from control→intervention on a
  randomized schedule. Pragmatic, ethical (everyone eventually gets it), controls for
  secular trends and unit effects.
- *Fallback if a single unit:* patient-level randomization of the alert (intervention
  vs held-back), or pre/post with concurrent non-renal controls.

## 5. Endpoints

- **Primary:** hospital LOS (days). Because LOS is right-skewed, analyze on
  **log-LOS** (or excess bed-days vs cohort-expected) and report median + mean.
- **Secondary:** time from admission to first CM action; discharge-delay days;
  post-acute prior-auth turnaround.
- **Balancing / safety (must not worsen):** 30-day readmission, in-hospital
  mortality, ICU transfer. Alert volume and CM workload (feasibility).

## 6. Model operating point & deployment

- Alert at **top 10% risk** within the renal cohort (validated precision ~77%,
  ~1.8× base) — tune to the site's CM capacity (top 5% ≈ ~82% precision, fewer alerts).
- **Recalibrate the model on the partner's historical data before go-live**
  (cross-center result shows the signal transfers but probabilities need per-site
  isotonic/Platt recalibration). Re-check ECE < 0.05 on site data.

## 7. Sample size (illustrative)

Detecting a **0.5-day** mean LOS reduction (SD ≈ 6 days), α=0.05, power=0.80:

```
n per arm ≈ 2 · (1.96 + 0.84)² · 6² / 0.5²  ≈  ~2,260
```

→ ~**4,500 renal-cohort patients total**. At a mid-size ED (~150 admits/day → ~40
renal/day), that is roughly a **4–6 month** pilot at one site. (Skew/clustering will
adjust this; finalize with the partner's real LOS distribution.)

## 8. Data the partner must provide (absent in MIMIC/eICU)

These are required to measure the *action* and the *delay*, not just the outcome:
- medically-ready / "discharge-ready" timestamps,
- case-management decision timestamps,
- bed-management + **prior-authorization** event logs,
- discharge-delay reason codes,
- live EHR feed (labs + ADT + triage) for real-time 24h scoring.

## 9. Governance & success criteria

- IRB / quality-improvement determination; operational-tool framing (not a medical
  device) provided no treatment recommendation is issued.
- **Go decision:** statistically significant LOS reduction with **no degradation** in
  readmission/mortality, and CM workload within capacity.
- **Pre-register** the analysis plan (endpoints, model version, operating point)
  before go-live to keep the result credible.

---

*Retrospective evidence backing this pilot: renal cohort 26.6% of ED→inpatient;
prolonged-LOS enrichment 1.64× (41% vs 25%); model ROC-AUC 0.736 (MIMIC) / 0.700
(eICU, external), top-5% precision 82%/60%, ECE 0.018/0.008; protocol (early creatinine) cost ≈ 0.23% of
the bed-day dollars at risk.*
