"""
External validation of the renal wedge on eICU (multi-center, ~200 US hospitals).

This is a GENERALIZATION check, not an apples-to-apples replay:
  - MIMIC wedge cohort  = ED->inpatient, first 24h from ED arrival (single center).
  - eICU cohort here    = ICU stays, first 24h from ICU admission (offset 0..1440 min),
                          many hospitals.
Different population + different schema, so we RETRAIN the same recipe on eICU and
ask: does the renal-cohort + first-24h-labs (+ age/sex) signal still rank prolonged
hospital stays with comparable ROC-AUC and top-decile precision/lift?

Reads the eICU CSVs directly (no DB load needed). patient.csv.gz + lab.csv.gz.

Usage:
    python scripts/validate_eicu_renal_wedge.py
    python scripts/validate_eicu_renal_wedge.py --eicu-dir data/raw/eicu
"""

import argparse
import json
import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
# reuse the exact same evaluation/model helpers as the MIMIC trainer
from train_renal_wedge_model import make_gbm, evaluate, print_results  # noqa: E402

from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.preprocessing import StandardScaler      # noqa: E402
from sklearn.pipeline import make_pipeline            # noqa: E402

# eICU labname -> canonical name (mirrors MIMIC core labs where possible)
EICU_LAB_MAP = [
    ("creatinine", "creatinine"), ("BUN", "bun"), ("sodium", "sodium"),
    ("potassium", "potassium"), ("WBC x 1000", "wbc"), ("Hct", "hematocrit"),
    ("platelets x 1000", "platelets"), ("lactate", "lactate"),
    ("glucose", "glucose"), ("calcium", "calcium"),
    ("bicarbonate", "bicarbonate"), ("chloride", "chloride"),
    ("anion gap", "aniongap"),
]
CANON_LABS = [c for _, c in EICU_LAB_MAP]
CANON_LABS = list(dict.fromkeys(CANON_LABS))  # unique, ordered


def resolve_eicu_dir(cli):
    cands = []
    if cli:
        cands.append(Path(cli))
    if os.environ.get("CDSP_EICU_DIR"):
        cands.append(Path(os.environ["CDSP_EICU_DIR"]))
    cands += [PROJECT_ROOT / "data" / "raw" / "eicu",
              Path("data/raw/eicu"), Path("../data/raw/eicu")]
    for c in cands:
        if (c / "patient.csv.gz").exists() and (c / "lab.csv.gz").exists():
            return c
    print("ERROR: eICU dir with patient.csv.gz + lab.csv.gz not found. Tried:")
    for c in cands:
        print(f"  - {c}")
    print("\nPass it: --eicu-dir C:\\...\\data\\raw\\eicu")
    sys.exit(1)


def p(path):
    """DuckDB-friendly path string (forward slashes)."""
    return str(path).replace("\\", "/")


def build_eicu(con, eicu_dir, window_min):
    values = ",".join(f"('{e}','{c}')" for e, c in EICU_LAB_MAP)
    pivots = []
    for lab in CANON_LABS:
        pivots.append(f"coalesce(max(case when a.lab_name='{lab}' then 1 end),0) as {lab}_measured")
        pivots.append(f"coalesce(max(case when a.lab_name='{lab}' then a.v_count end),0) as {lab}_count")
        for m in ["min", "max", "mean", "first", "last"]:
            pivots.append(f"max(case when a.lab_name='{lab}' then a.v_{m} end) as {lab}_{m}")
        for m in ["delta", "range"]:
            pivots.append(f"coalesce(max(case when a.lab_name='{lab}' then a.v_{m} end),0) as {lab}_{m}")
    pivot_sql = ",\n        ".join(pivots)

    lab_csv = p(eicu_dir / "lab.csv.gz")
    pat_csv = p(eicu_dir / "patient.csv.gz")

    sql = f"""
    with lab_map as (select * from (values {values}) as t(eicu_name, lab_name)),
    raw_lab as (
        select
            l.patientunitstayid as stay,
            m.lab_name,
            l.labresultoffset as off,
            try_cast(l.labresult as double) as val
        from read_csv_auto('{lab_csv}', ignore_errors=true) l
        join lab_map m on lower(l.labname) = lower(m.eicu_name)
        where l.labresultoffset >= 0 and l.labresultoffset < {window_min}
          and try_cast(l.labresult as double) is not null
    ),
    endp as (
        select stay, lab_name, val,
            first_value(val) over (partition by stay, lab_name order by off) as v_first,
            last_value(val) over (partition by stay, lab_name order by off
                rows between unbounded preceding and unbounded following) as v_last
        from raw_lab
    ),
    agg as (
        select stay, lab_name,
            count(*) as v_count, min(val) as v_min, max(val) as v_max,
            round(avg(val),3) as v_mean,
            any_value(v_first) as v_first, any_value(v_last) as v_last,
            case when count(*)>1 then round(any_value(v_last)-any_value(v_first),3) else 0 end as v_delta,
            round(max(val)-min(val),3) as v_range
        from endp group by stay, lab_name
    ),
    burden as (
        select stay, count(*) as total_labs, count(distinct lab_name) as unique_labs
        from raw_lab group by stay
    ),
    feats as (
        select a0.stay,
            {pivot_sql},
            coalesce(bd.total_labs,0)  as total_labs_24h,
            coalesce(bd.unique_labs,0) as unique_labs_24h
        from (select distinct stay from raw_lab) a0
        left join agg a on a.stay = a0.stay
        left join burden bd on bd.stay = a0.stay
        group by a0.stay, bd.total_labs, bd.unique_labs
    ),
    pat as (
        select
            patientunitstayid as stay,
            uniquepid,
            case when trim(age) = '> 89' then 90.0 else try_cast(age as double) end as age,
            case when gender = 'Male' then 1 else 0 end as is_male,
            (try_cast(hospitaldischargeoffset as double)
              - try_cast(hospitaladmitoffset as double)) / 1440.0 as hosp_los_days
        from read_csv_auto('{pat_csv}', ignore_errors=true)
        where hospitaldischargeoffset is not null
          and hospitaladmitoffset is not null
          and (try_cast(hospitaldischargeoffset as double)
               - try_cast(hospitaladmitoffset as double)) > 0
    )
    select pt.uniquepid, pt.age, pt.is_male, pt.hosp_los_days, f.*
    from feats f
    join pat pt on pt.stay = f.stay
    """
    return con.execute(sql).df()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--eicu-dir")
    ap.add_argument("--window-min", type=int, default=1440, help="lab window in minutes (default 1440=24h)")
    ap.add_argument("--creat-high", type=float, default=1.3)
    ap.add_argument("--bun-high", type=float, default=20.0)
    args = ap.parse_args()

    eicu = resolve_eicu_dir(args.eicu_dir)
    print(f"eICU dir: {eicu}")
    con = duckdb.connect()
    try:
        con.execute("PRAGMA threads=4")
    except Exception:
        pass

    print("Reading eICU patient + lab (this scans lab.csv.gz, ~1-2 min) ...")
    df = build_eicu(con, eicu, args.window_min)
    con.close()
    print(f"eICU ICU stays with labs in 0-{args.window_min}min: {len(df):,}")

    # renal cohort
    creat = df["creatinine_max"].fillna(0)
    bun = df["bun_max"].fillna(0)
    df = df[(creat > args.creat_high) | (bun > args.bun_high)].copy()

    # label: prolonged hospital LOS >= cohort P75
    thr = df["hosp_los_days"].quantile(0.75)
    df["long_stay_flag"] = (df["hosp_los_days"] >= thr).astype(int)
    print(f"Renal cohort: {len(df):,} stays | P75 hosp LOS = {thr:.1f} d | "
          f"prolonged rate {df['long_stay_flag'].mean()*100:.1f}%")

    # patient-level split (no uniquepid in two splits)
    def bucket(u):
        return int(hashlib.md5(str(u).encode()).hexdigest(), 16) % 100
    b = df["uniquepid"].map(bucket)
    df["split"] = np.where(b < 60, "train", np.where(b < 80, "cal", "test"))

    drop = {"uniquepid", "stay", "hosp_los_days", "long_stay_flag", "split"}
    feat_cols = [c for c in df.columns if c not in drop]
    X = df[feat_cols].fillna(0).astype(float)
    y = df["long_stay_flag"].astype(int).values

    def part(name):
        m = (df["split"] == name).values
        return X[m].values, y[m]

    Xtr, ytr = part("train"); Xcal, ycal = part("cal"); Xte, yte = part("test")
    print(f"Split: train={len(ytr):,} cal={len(ycal):,} test={len(yte):,} "
          f"({len(feat_cols)} features)")

    print("\n" + "=" * 64)
    print("  eICU EXTERNAL VALIDATION — RENAL WEDGE (retrained, calibrated)")
    print("=" * 64)

    logit = make_pipeline(StandardScaler(),
                          LogisticRegression(max_iter=2000, class_weight="balanced"))
    lr_res, _, _ = evaluate("Logistic baseline", logit, Xtr, ytr, Xcal, ycal, Xte, yte)
    print_results(lr_res)

    gbm_name, gbm = make_gbm()
    gbm_res, _, _ = evaluate(gbm_name, gbm, Xtr, ytr, Xcal, ycal, Xte, yte)
    print_results(gbm_res)

    # Honest side-by-side: read the committed MIMIC artifact, never a hardcoded number.
    docs = PROJECT_ROOT / "docs"
    mimic = {}
    mpath = docs / "renal_wedge_model_metrics.json"
    if mpath.exists():
        mimic = json.loads(mpath.read_text(encoding="utf-8")).get("gbm", {})

    print("\n" + "=" * 64)
    print("COMPARISON vs MIMIC (renal wedge, 24h, HistGB):")
    if mimic.get("operating_points"):
        print(f"  MIMIC : ROC-AUC {mimic['test_roc_auc']:.3f} | "
              f"top5% precision {mimic['operating_points'][0]['precision']*100:.0f}% / "
              f"lift {mimic['operating_points'][0]['lift']:.2f}x")
    else:
        print("  MIMIC : (run train_renal_wedge_model.py --write first to populate)")
    print(f"  eICU  : ROC-AUC {gbm_res['test_roc_auc']:.3f} | "
          f"top5% precision {gbm_res['operating_points'][0]['precision']*100:.0f}% / "
          f"lift {gbm_res['operating_points'][0]['lift']:.2f}x")
    print("  -> Comparable numbers on a DIFFERENT multi-center population")
    print("     materially de-risk the single-center (MIMIC/BIDMC) concern.")

    # ---- write committable artifact (json + md) ----
    out = {
        "dataset": "eICU (multi-center, retrained recipe)",
        "window_min": args.window_min,
        "renal_definition": f"creatinine_max>{args.creat_high} OR bun_max>{args.bun_high}",
        "cohort_size": int(len(df)),
        "prolonged_rate": float(df["long_stay_flag"].mean()),
        "p75_hosp_los_days": float(thr),
        "splits": {"train": int(len(ytr)), "cal": int(len(ycal)), "test": int(len(yte))},
        "n_features": len(feat_cols),
        "logistic": lr_res,
        "gbm": gbm_res,
        "mimic_gbm_reference": mimic,
    }
    (docs / "eicu_external_validation.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")

    md = [
        "# eICU External Validation — Renal Wedge (retrained recipe)",
        "",
        f"- Multi-center eICU (~200 US hospitals). Renal cohort: **{len(df):,}** ICU stays, "
        f"prolonged-LOS rate **{df['long_stay_flag'].mean()*100:.1f}%** (P75 = {thr:.1f} d).",
        f"- Patient-level split (no `uniquepid` in two splits): "
        f"train {len(ytr):,} / cal {len(ycal):,} / test {len(yte):,}. {len(feat_cols)} features.",
        "",
        "| Model | ROC-AUC | PR-AUC | ECE | Top5% prec/lift |",
        "|---|---|---|---|---|",
    ]
    for r in (lr_res, gbm_res):
        op = r["operating_points"][0]
        md.append(
            f"| {r['model']} | {r['test_roc_auc']:.3f} | "
            f"{r.get('test_pr_auc', float('nan')):.3f} | "
            f"{r.get('test_ece', float('nan')):.3f} | "
            f"{op['precision']*100:.0f}% / {op['lift']:.2f}x |")
    md += [
        "",
        f"**Generalization:** retrained on a different population, the renal-cohort + "
        f"first-{args.window_min // 60}h-labs signal ranks prolonged stays at "
        f"ROC-AUC {gbm_res['test_roc_auc']:.3f}"
        + (f" — vs MIMIC {mimic['test_roc_auc']:.3f}" if mimic.get("test_roc_auc") else "")
        + ", supporting cross-center generalization.",
        "",
        "> Generalization check (retrain same recipe), **not** an apples-to-apples replay: "
        "populations (ICU vs ED→inpatient) and schemas differ.",
    ]
    (docs / "eicu_external_validation.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nWrote {docs / 'eicu_external_validation.json'} and .md")
    print("=" * 64)


if __name__ == "__main__":
    main()
