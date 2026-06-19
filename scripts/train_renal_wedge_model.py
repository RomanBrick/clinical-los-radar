"""
Train + calibrate a longer-stay risk model on the RENAL-DYSFUNCTION cohort (24h).

This is the step that moves the wedge from "correlation (lift)" to "does a model
actually rank these patients well enough to be useful?".

Pipeline (self-contained, reads your DuckDB read-only; builds features from raw
labs so it does NOT depend on which dbt feature tables are materialized):
  1. Build 24h dynamic lab features per admission (count/min/max/mean/first/last/
     delta/range + measured flags for 8 core labs) + lab-burden.
  2. Keep the RENAL cohort: creatinine_max > 1.3 OR bun_max > 20 (first 24h).
  3. Subject-level split (no subject in two splits): 70% train / 15% cal / 15% test.
  4. Train Logistic baseline + a gradient-boosted model (LightGBM if available,
     else sklearn HistGradientBoosting).
  5. Calibrate probabilities (isotonic) on the calibration split.
  6. Evaluate on test: ROC-AUC, PR-AUC, Brier, and operating points (top 5/10/20%)
     with precision / recall / lift AND the theoretical recall ceiling.

HONEST NOTE on targets: the project's radar_output_contract sets Recall@Top10% > 0.6.
At a 41% base rate the MAX possible Recall@Top10% is ~0.24 (=0.10/0.41). That target
is mathematically infeasible at this prevalence; this script reports ceilings and
proposes corrected, lift-based targets instead.

Usage:
    python scripts/train_renal_wedge_model.py
    python scripts/train_renal_wedge_model.py --window-hours 24 --write
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CORE_LABS = ["sodium", "potassium", "bun", "creatinine",
             "wbc", "hematocrit", "platelets", "lactate"]
LAB_ITEMS = [
    (50983, "sodium"), (50971, "potassium"), (51006, "bun"), (50912, "creatinine"),
    (51301, "wbc"), (51221, "hematocrit"), (51265, "platelets"),
    (50813, "lactate"), (52442, "lactate"), (53154, "lactate"),
]
METRICS = ["min", "max", "mean", "first", "last", "delta", "range", "count"]


def resolve_db_path(cli_path):
    cands = []
    if cli_path:
        cands.append(Path(cli_path))
    if os.environ.get("CDSP_DB"):
        cands.append(Path(os.environ["CDSP_DB"]))
    cands += [PROJECT_ROOT / "data" / "processed" / "mimic.duckdb",
              Path("data/processed/mimic.duckdb"),
              Path("../data/processed/mimic.duckdb")]
    for c in cands:
        if c.exists():
            return c
    print("ERROR: DuckDB not found. Pass --db or set CDSP_DB.")
    sys.exit(1)


def find_table(con, *kw):
    rows = con.execute(
        "select table_schema, table_name from information_schema.tables "
        "where table_type in ('BASE TABLE','VIEW')").fetchall()
    m = [(s, t) for s, t in rows if all(k.lower() in t.lower() for k in kw)]
    if not m:
        raise RuntimeError(f"No table matching {kw}.")
    m.sort(key=lambda i: (("marts" in i[0] or "intermediate" in i[0]
                           or "staging" in i[0]), "main" in i[0]), reverse=True)
    return f'"{m[0][0]}"."{m[0][1]}"'


def build_features(con, spine, labs, W):
    """Generate the 24h dynamic feature matrix (one row per hadm_id)."""
    values = ",".join(f"({i},'{n}')" for i, n in LAB_ITEMS)
    pivots = []
    for lab in CORE_LABS:
        pivots.append(
            f"coalesce(max(case when a.lab_name='{lab}' then 1 end),0) as {lab}_measured")
        pivots.append(
            f"coalesce(max(case when a.lab_name='{lab}' then a.v_count end),0) as {lab}_count")
        for mtr in ["min", "max", "mean", "first", "last"]:
            pivots.append(
                f"max(case when a.lab_name='{lab}' then a.v_{mtr} end) as {lab}_{mtr}")
        for mtr in ["delta", "range"]:
            pivots.append(
                f"coalesce(max(case when a.lab_name='{lab}' then a.v_{mtr} end),0) "
                f"as {lab}_{mtr}")
    pivot_sql = ",\n        ".join(pivots)

    sql = f"""
    with spine as (
        select hadm_id, subject_id, ed_intime,
               ed_intime + interval '{W} hours' as wend
        from {spine}
    ),
    lab_map as (select * from (values {values}) as t(itemid, lab_name)),
    lw as (
        select s.hadm_id, m.lab_name, l.charttime, l.valuenum
        from spine s
        join {labs} l
          on l.hadm_id = s.hadm_id and l.valuenum is not null
         and l.charttime >= s.ed_intime and l.charttime < s.wend
        join lab_map m on m.itemid = l.itemid
    ),
    endp as (
        select hadm_id, lab_name, valuenum,
            first_value(valuenum) over (partition by hadm_id, lab_name
                order by charttime) as v_first,
            last_value(valuenum) over (partition by hadm_id, lab_name
                order by charttime
                rows between unbounded preceding and unbounded following) as v_last
        from lw
    ),
    agg as (
        select hadm_id, lab_name,
            count(*) as v_count, min(valuenum) as v_min, max(valuenum) as v_max,
            round(avg(valuenum),3) as v_mean,
            any_value(v_first) as v_first, any_value(v_last) as v_last,
            case when count(*)>1 then round(any_value(v_last)-any_value(v_first),3)
                 else 0 end as v_delta,
            round(max(valuenum)-min(valuenum),3) as v_range
        from endp group by hadm_id, lab_name
    ),
    burden as (
        select hadm_id, count(*) as total_labs, count(distinct lab_name) as unique_labs
        from lw group by hadm_id
    )
    select
        s.hadm_id, s.subject_id,
        {pivot_sql},
        coalesce(b.total_labs,0)  as total_labs_24h,
        coalesce(b.unique_labs,0) as unique_labs_24h
    from spine s
    left join agg a on a.hadm_id = s.hadm_id
    left join burden b on b.hadm_id = s.hadm_id
    group by s.hadm_id, s.subject_id, b.total_labs, b.unique_labs
    """
    return con.execute(sql).df()


def find_raw(con, name):
    """Find a table by exact name, preferring schemas that look like 'raw'."""
    rows = con.execute(
        "select table_schema, table_name from information_schema.tables").fetchall()
    cand = [(s, t) for s, t in rows if t.lower() == name.lower()]
    if not cand:
        return None
    cand.sort(key=lambda i: ("raw" in i[0].lower()), reverse=True)
    return f'"{cand[0][0]}"."{cand[0][1]}"'


def build_context_features(con, spine):
    """Demographics (patients) + admission context (admissions) + ED triage.
    Returns a per-hadm_id dataframe, or None if the raw tables aren't present."""
    pat = find_raw(con, "patients")
    adm = find_raw(con, "admissions")
    tri = find_raw(con, "ed_triage") or find_raw(con, "triage")
    if not (pat and adm):
        print("  (context) raw patients/admissions not found -> labs-only model")
        return None
    tri_join = f"left join {tri} t on t.stay_id = s.stay_id" if tri else ""
    tri_cols = ("""
        , try_cast(t.acuity as double)      as triage_acuity
        , try_cast(t.heartrate as double)   as triage_hr
        , try_cast(t.resprate as double)    as triage_rr
        , try_cast(t.o2sat as double)       as triage_o2
        , try_cast(t.sbp as double)         as triage_sbp
        , try_cast(t.dbp as double)         as triage_dbp
        , try_cast(t.temperature as double) as triage_temp
        , try_cast(t.pain as double)        as triage_pain
    """ if tri else "")
    if not tri:
        print("  (context) ed_triage not found -> adding demographics only")
    sql = f"""
        select
            s.hadm_id,
            try_cast(p.anchor_age as double) as age,
            p.gender          as gender,
            a.admission_type  as admission_type,
            a.insurance       as insurance,
            a.marital_status  as marital_status,
            a.race            as race
            {tri_cols}
        from {spine} s
        left join {pat} p on p.subject_id = s.subject_id
        left join {adm} a on a.hadm_id   = s.hadm_id
        {tri_join}
    """
    return con.execute(sql).df()


def operating_point(y, p, q):
    """At top-q fraction by score: precision, recall, lift, recall ceiling."""
    n = len(y)
    k = max(1, int(round(q * n)))
    idx = np.argsort(-p)[:k]
    base = y.mean()
    tp = y[idx].sum()
    precision = tp / k
    recall = tp / y.sum() if y.sum() else float("nan")
    lift = precision / base if base else float("nan")
    ceiling = min(q, base) / base if base else float("nan")
    return {"q": q, "k": int(k), "precision": float(precision),
            "recall": float(recall), "lift": float(lift),
            "recall_ceiling": float(ceiling)}


def make_gbm():
    try:
        from lightgbm import LGBMClassifier
        return ("LightGBM",
                LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=31,
                               subsample=0.8, colsample_bytree=0.8,
                               class_weight="balanced", random_state=42, n_jobs=-1,
                               verbose=-1))
    except Exception:
        from sklearn.ensemble import HistGradientBoostingClassifier
        return ("HistGradientBoosting",
                HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05,
                                                max_depth=None, random_state=42,
                                                class_weight="balanced"))


def expected_calibration_error(y, p, bins=10):
    """Mean |confidence - accuracy| over equal-width probability bins (ECE)."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    ece = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            ece += abs(p[m].mean() - y[m].mean()) * m.mean()
    return float(ece)


def evaluate(name, model, Xtr, ytr, Xcal, ycal, Xte, yte):
    model.fit(Xtr, ytr)
    raw_cal = model.predict_proba(Xcal)[:, 1]
    raw_te = model.predict_proba(Xte)[:, 1]

    # Two calibrators on the held-out calibration split; pick lower cal Brier.
    iso = IsotonicRegression(out_of_bounds="clip").fit(raw_cal, ycal)
    platt = LogisticRegression(max_iter=1000).fit(raw_cal.reshape(-1, 1), ycal)
    iso_cal = iso.predict(raw_cal)
    platt_cal = platt.predict_proba(raw_cal.reshape(-1, 1))[:, 1]
    if brier_score_loss(ycal, iso_cal) <= brier_score_loss(ycal, platt_cal):
        p, method = iso.predict(raw_te), "isotonic"
    else:
        p, method = platt.predict_proba(raw_te.reshape(-1, 1))[:, 1], "platt"

    res = {
        "model": name,
        "calibration_method": method,
        "test_roc_auc": float(roc_auc_score(yte, p)),
        "test_pr_auc": float(average_precision_score(yte, p)),
        "test_brier": float(brier_score_loss(yte, p)),
        "test_ece": expected_calibration_error(yte, p),
        "test_base_rate": float(yte.mean()),
        "operating_points": [operating_point(yte, p, q) for q in (0.05, 0.10, 0.20)],
    }
    return res, model, p


def print_results(res):
    print(f"\n--- {res['model']} ({res.get('calibration_method','?')}-calibrated) "
          f"{'-'*max(0,40-len(res['model']))}")
    print(f"  ROC-AUC: {res['test_roc_auc']:.4f}   "
          f"PR-AUC: {res['test_pr_auc']:.4f}   "
          f"Brier: {res['test_brier']:.4f}   "
          f"ECE: {res.get('test_ece', float('nan')):.4f}   "
          f"base rate: {res['test_base_rate']*100:.1f}%")
    print(f"  {'top':>5} {'precision':>10} {'recall':>8} "
          f"{'ceiling':>8} {'lift':>6}")
    for op in res["operating_points"]:
        print(f"  {op['q']*100:>4.0f}% {op['precision']*100:>9.1f}% "
              f"{op['recall']*100:>7.1f}% {op['recall_ceiling']*100:>7.1f}% "
              f"{op['lift']:>5.2f}x")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db")
    ap.add_argument("--window-hours", type=int, default=24)
    ap.add_argument("--creat-high", type=float, default=1.3)
    ap.add_argument("--bun-high", type=float, default=20.0)
    ap.add_argument("--write", action="store_true",
                    help="write docs/renal_wedge_model_metrics.{json,md}")
    ap.add_argument("--from-mart", action="store_true",
                    help="read features from the dbt table main_marts.training_renal_wedge "
                         "(single source of truth) instead of rebuilding from raw labs")
    args = ap.parse_args()

    db = resolve_db_path(args.db)
    print(f"Using DuckDB: {db}")
    con = duckdb.connect(str(db), read_only=True)
    spine = find_table(con, "encounter_spine")
    labs = find_table(con, "stg_labevents")
    labels = find_table(con, "labels_long_stay")
    print(f"Spine:  {spine}\nLabs:   {labs}\nLabels: {labels}")
    if os.environ.get("CDSP_LIST_TABLES"):
        print("\nTables in DB:")
        for s, t in con.execute(
                "select table_schema, table_name from information_schema.tables "
                "order by 1,2").fetchall():
            print(f"  {s}.{t}")

    if args.from_mart:
        mart = find_table(con, "training_renal_wedge")
        print(f"\nReading features from dbt mart: {mart}")
        df = con.execute(f"select * from {mart}").df()
        con.close()
        # align split naming with this script's convention
        df["split"] = df["split"].replace({"calibration": "cal"})
        print(f"Renal cohort (from mart): {len(df):,} admissions "
              f"(prolonged rate {df['long_stay_flag'].mean()*100:.1f}%)")
    else:
        print("\nBuilding 24h feature matrix from raw labs ...")
        feat = build_features(con, spine, labs, args.window_hours)
        ctx = None
        try:
            ctx = build_context_features(con, spine)
        except Exception as e:
            print(f"  (context) skipped due to: {e}")
        lab_df = con.execute(
            f"select hadm_id, long_stay_flag from {labels}").df()
        con.close()

        df = feat.merge(lab_df, on="hadm_id", how="inner")
        if ctx is not None:
            df = df.merge(ctx, on="hadm_id", how="left")
            print(f"Added context features (demographics/admission/triage): "
                  f"+{ctx.shape[1]-1} raw columns")

        # renal cohort
        creat = df["creatinine_max"].fillna(0)
        bun = df["bun_max"].fillna(0)
        df = df[(creat > args.creat_high) | (bun > args.bun_high)].copy()
        print(f"Renal cohort: {len(df):,} admissions "
              f"(prolonged rate {df['long_stay_flag'].mean()*100:.1f}%)")

        # subject-level split (deterministic, no subject in two splits)
        bucket = (df["subject_id"].astype("int64") % 100)
        df["split"] = np.where(bucket < 70, "train",
                      np.where(bucket < 85, "cal", "test"))

    # one-hot categoricals (cap cardinality) + median-fill context numerics
    cat_cols = [c for c in ["gender", "admission_type", "insurance",
                            "marital_status", "race"] if c in df.columns]
    for c in cat_cols:
        keep = df[c].value_counts().nlargest(6).index
        df[c] = np.where(df[c].isin(keep), df[c].astype(str), "OTHER")
    if cat_cols:
        df = pd.get_dummies(df, columns=cat_cols, dummy_na=False)
    for c in [x for x in ["age", "triage_acuity", "triage_hr", "triage_rr",
                          "triage_o2", "triage_sbp", "triage_dbp",
                          "triage_temp", "triage_pain"] if x in df.columns]:
        df[c] = df[c].fillna(df[c].median())

    drop_cols = {"hadm_id", "subject_id", "long_stay_flag", "split",
                 "los_days", "renal_dysfunction_flag", "ed_intime"}
    feat_cols = [c for c in df.columns if c not in drop_cols]
    X = df[feat_cols].fillna(0).astype(float)
    y = df["long_stay_flag"].astype(int).values

    def part(name):
        m = (df["split"] == name).values
        return X[m].values, y[m]

    Xtr, ytr = part("train")
    Xcal, ycal = part("cal")
    Xte, yte = part("test")
    print(f"Split: train={len(ytr):,}  cal={len(ycal):,}  test={len(yte):,}  "
          f"({len(feat_cols)} features)")

    print("\n" + "=" * 64)
    print("  RENAL WEDGE MODEL — TEST METRICS (24h, calibrated)")
    print("=" * 64)

    # Logistic baseline (scaled)
    logit = make_pipeline(StandardScaler(),
                          LogisticRegression(max_iter=2000, class_weight="balanced"))
    lr_res, _, _ = evaluate("Logistic baseline", logit, Xtr, ytr, Xcal, ycal, Xte, yte)
    print_results(lr_res)

    gbm_name, gbm = make_gbm()
    gbm_res, gbm_model, _ = evaluate(gbm_name, gbm, Xtr, ytr, Xcal, ycal, Xte, yte)
    print_results(gbm_res)

    # global feature importance from the GBM (best effort; HistGB lacks it)
    importance = None
    if hasattr(gbm_model, "feature_importances_"):
        importance = sorted(zip(feat_cols, gbm_model.feature_importances_),
                            key=lambda t: -t[1])[:15]
        print(f"\n  Top features ({gbm_name}):")
        for f, v in importance:
            print(f"    {f:32s} {v:.4f}")

    print("\n" + "=" * 64)
    print("HONEST READ:")
    best = max(lr_res, gbm_res, key=lambda r: r["test_roc_auc"])
    op10 = next(o for o in best["operating_points"] if o["q"] == 0.10)
    print(f"  - Best ROC-AUC: {best['test_roc_auc']:.3f} ({best['model']}).")
    print(f"  - At top 10% of renal patients: precision {op10['precision']*100:.0f}% "
          f"(={op10['lift']:.2f}x base), recall {op10['recall']*100:.0f}% "
          f"(ceiling {op10['recall_ceiling']*100:.0f}%).")
    print("  - Contract's Recall@Top10%>0.6 is INFEASIBLE here (ceiling < 60% at this")
    print("    prevalence). Use lift/precision at the operating point instead.")
    print("=" * 64)

    if args.write:
        docs = PROJECT_ROOT / "docs"
        docs.mkdir(exist_ok=True)
        out = {"window_hours": args.window_hours,
               "renal_definition": f"creatinine_max>{args.creat_high} OR bun_max>{args.bun_high}",
               "cohort_size": int(len(df)),
               "splits": {"train": int(len(ytr)), "cal": int(len(ycal)),
                          "test": int(len(yte))},
               "n_features": len(feat_cols),
               "logistic": lr_res, "gbm": gbm_res,
               "top_features": [{"feature": f, "importance": float(v)}
                                for f, v in (importance or [])]}
        (docs / "renal_wedge_model_metrics.json").write_text(
            json.dumps(out, indent=2), encoding="utf-8")

        def op_row(r):
            o = {x["q"]: x for x in r["operating_points"]}
            return (f"| {r['model']} | {r['test_roc_auc']:.3f} | {r['test_pr_auc']:.3f} "
                    f"| {r['test_brier']:.3f} | {o[0.05]['precision']*100:.0f}% "
                    f"/ {o[0.05]['lift']:.2f}x | {o[0.10]['precision']*100:.0f}% "
                    f"/ {o[0.10]['lift']:.2f}x |")
        md = [
            "# Renal Wedge Model — Metrics (24h, calibrated)",
            "",
            f"- Cohort: renal dysfunction in first {args.window_hours}h "
            f"(creatinine>{args.creat_high} OR BUN>{args.bun_high}), "
            f"**{len(df):,}** admissions, base rate "
            f"**{df['long_stay_flag'].mean()*100:.1f}%**.",
            f"- Subject-level split: train {len(ytr):,} / cal {len(ycal):,} "
            f"/ test {len(yte):,}. Isotonic calibration on cal split.",
            "",
            "| Model | ROC-AUC | PR-AUC | Brier | Top5% prec/lift | Top10% prec/lift |",
            "|---|---|---|---|---|---|",
            op_row(lr_res), op_row(gbm_res),
            "",
            "**Note on targets:** at this base rate the contract's "
            "`Recall@Top10% > 0.6` is mathematically infeasible "
            f"(ceiling ~{op10['recall_ceiling']*100:.0f}%). "
            "Report precision/lift at the operating point instead.",
        ]
        (docs / "renal_wedge_model_metrics.md").write_text(
            "\n".join(md), encoding="utf-8")
        print(f"\nWrote {docs/'renal_wedge_model_metrics.md'} and .json")


if __name__ == "__main__":
    main()
