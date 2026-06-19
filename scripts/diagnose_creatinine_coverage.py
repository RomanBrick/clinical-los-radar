"""
Coverage diagnostic for the renal wedge: WHY is early creatinine only ~20%?

The wedge depends on having creatinine in the first 0-6h after ED arrival.
Phase 3 showed only ~20% coverage. This script diagnoses artifact vs reality:

  A. ED boarding time (admittime - ed_intime): if the 6h window from ed_intime
     often ends BEFORE the patient is even admitted, that alone explains low
     coverage and is fixable by re-anchoring the window.
  B. When does the FIRST creatinine actually appear (hours from ed_intime)?
     Distribution + buckets.
  C. Coverage if we widen the window (6h / 12h / 24h) and if we anchor on
     admittime instead of ed_intime.

Read-only. Auto-discovers the staged labevents + spine tables.

Usage:
    python scripts/diagnose_creatinine_coverage.py
    python scripts/diagnose_creatinine_coverage.py --db /path/to/mimic.duckdb
    python scripts/diagnose_creatinine_coverage.py --creat-itemid 50912
"""

import argparse
import os
import sys
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREAT_ITEMID_DEFAULT = 50912  # creatinine, serum (from core_lab_map in labs_0_6h_dynamic)


def resolve_db_path(cli_path):
    candidates = []
    if cli_path:
        candidates.append(Path(cli_path))
    if os.environ.get("CDSP_DB"):
        candidates.append(Path(os.environ["CDSP_DB"]))
    candidates += [
        PROJECT_ROOT / "data" / "processed" / "mimic.duckdb",
        PROJECT_ROOT / "cdsp" / "data" / "processed" / "mimic.duckdb",
        Path("data/processed/mimic.duckdb"),
        Path("../data/processed/mimic.duckdb"),
    ]
    for c in candidates:
        if c.exists():
            return c
    print("ERROR: could not find the DuckDB file. Tried:")
    for c in candidates:
        print(f"  - {c}")
    print("\nPass it explicitly:  --db C:\\path\\to\\mimic.duckdb  (or set CDSP_DB).")
    sys.exit(1)


def find_table(con, *keywords):
    rows = con.execute(
        """
        select table_schema, table_name
        from information_schema.tables
        where table_type in ('BASE TABLE', 'VIEW')
        """
    ).fetchall()
    matches = [(s, t) for (s, t) in rows
               if all(k.lower() in t.lower() for k in keywords)]
    if not matches:
        raise RuntimeError(f"No table matching keywords {keywords}.")

    def score(item):
        s = item[0].lower()
        return (("staging" in s or "intermediate" in s), "main" in s)

    matches.sort(key=score, reverse=True)
    s, t = matches[0]
    return f'"{s}"."{t}"'


def pct(n, d):
    return f"{(n/d)*100:.1f}%" if d else "n/a"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db")
    ap.add_argument("--creat-itemid", type=int, default=CREAT_ITEMID_DEFAULT)
    args = ap.parse_args()

    db_path = resolve_db_path(args.db)
    print(f"Using DuckDB: {db_path}")
    con = duckdb.connect(str(db_path), read_only=True)

    spine_tbl = find_table(con, "encounter_spine")
    labs_tbl = find_table(con, "stg_labevents")
    print(f"Spine table:  {spine_tbl}")
    print(f"Labs table:   {labs_tbl}")
    print(f"Creatinine itemid: {args.creat_itemid}\n")

    # One pass: per-admission first-creatinine timing (relative to ed_intime AND
    # admittime) plus ED boarding gap.
    sql = f"""
    with spine as (
        select hadm_id, ed_intime, admittime, dischtime
        from {spine_tbl}
    ),
    creat as (
        select hadm_id, charttime
        from {labs_tbl}
        where itemid = {args.creat_itemid}
          and valuenum is not null
    ),
    per_adm as (
        select
            s.hadm_id,
            date_diff('second', s.ed_intime, s.admittime)/3600.0 as boarding_h,
            -- first creatinine after ED arrival, within the encounter
            min(case when c.charttime >= s.ed_intime and c.charttime <= s.dischtime
                     then c.charttime end) as first_after_ed,
            -- first creatinine after inpatient admission, within the encounter
            min(case when c.charttime >= s.admittime and c.charttime <= s.dischtime
                     then c.charttime end) as first_after_adm,
            -- any creatinine at all during the encounter (incl. before ed_intime)
            count(case when c.charttime <= s.dischtime then 1 end) as creat_events,
            s.ed_intime  as ed_intime,
            s.admittime  as admittime
        from spine s
        left join creat c on s.hadm_id = c.hadm_id
        group by s.hadm_id, s.ed_intime, s.admittime
    ),
    timed as (
        select
            hadm_id,
            boarding_h,
            creat_events,
            case when first_after_ed is not null
                 then date_diff('second', ed_intime, first_after_ed)/3600.0 end as h_ed,
            case when first_after_adm is not null
                 then date_diff('second', admittime, first_after_adm)/3600.0 end as h_adm
        from per_adm
    )
    select
        count(*)                                          as n_total,
        count(creat_events) filter (where creat_events>0) as n_any_creat,
        -- boarding distribution
        median(boarding_h)                                as board_median,
        quantile_cont(boarding_h, 0.75)                   as board_p75,
        quantile_cont(boarding_h, 0.90)                   as board_p90,
        count(*) filter (where boarding_h > 6)            as n_board_gt6,
        -- first-creatinine-after-ED timing
        median(h_ed)                                      as hed_median,
        quantile_cont(h_ed, 0.25)                         as hed_p25,
        quantile_cont(h_ed, 0.75)                         as hed_p75,
        -- coverage windows anchored on ED arrival
        count(*) filter (where h_ed >= 0 and h_ed < 6)    as n_ed_6h,
        count(*) filter (where h_ed >= 0 and h_ed < 12)   as n_ed_12h,
        count(*) filter (where h_ed >= 0 and h_ed < 24)   as n_ed_24h,
        -- coverage windows anchored on inpatient admission
        count(*) filter (where h_adm >= 0 and h_adm < 6)  as n_adm_6h,
        count(*) filter (where h_adm >= 0 and h_adm < 12) as n_adm_12h,
        count(*) filter (where h_adm >= 0 and h_adm < 24) as n_adm_24h,
        -- buckets of first-creatinine-after-ED
        count(*) filter (where h_ed >= 0 and h_ed < 6)    as b_0_6,
        count(*) filter (where h_ed >= 6 and h_ed < 12)   as b_6_12,
        count(*) filter (where h_ed >= 12 and h_ed < 24)  as b_12_24,
        count(*) filter (where h_ed >= 24)                as b_24p,
        count(*) filter (where h_ed < 0)                  as b_neg
    from timed
    """
    r = con.execute(sql).fetchone()
    k = [
        "n_total", "n_any_creat",
        "board_median", "board_p75", "board_p90", "n_board_gt6",
        "hed_median", "hed_p25", "hed_p75",
        "n_ed_6h", "n_ed_12h", "n_ed_24h",
        "n_adm_6h", "n_adm_12h", "n_adm_24h",
        "b_0_6", "b_6_12", "b_12_24", "b_24p", "b_neg",
    ]
    d = dict(zip(k, r))
    N = d["n_total"]

    print("=" * 72)
    print("  CREATININE COVERAGE DIAGNOSTIC")
    print("=" * 72)
    print(f"  ED->inpatient admissions:             {N:>10,}")
    print(f"  ...with ANY creatinine in encounter:  {d['n_any_creat']:>10,} "
          f"({pct(d['n_any_creat'], N)})")

    print("\n-- A. ED BOARDING (admittime - ed_intime) -----------------------------")
    print(f"  Median boarding:                      {d['board_median']:.1f} h")
    print(f"  p75 / p90 boarding:                   {d['board_p75']:.1f} / {d['board_p90']:.1f} h")
    print(f"  Admitted AFTER the 6h window closes:  {d['n_board_gt6']:>10,} "
          f"({pct(d['n_board_gt6'], N)})")
    print("    ^ if large, the 0-6h-from-ED window ends before admission = fixable artifact")

    print("\n-- B. WHEN DOES FIRST CREATININE APPEAR? (hours after ED arrival) ------")
    if d["hed_median"] is not None:
        print(f"  Median / p25 / p75:                   "
              f"{d['hed_median']:.1f} / {d['hed_p25']:.1f} / {d['hed_p75']:.1f} h")
    print(f"  Buckets (first creatinine after ED arrival):")
    print(f"    0-6h:   {d['b_0_6']:>9,} ({pct(d['b_0_6'], N)})")
    print(f"    6-12h:  {d['b_6_12']:>9,} ({pct(d['b_6_12'], N)})")
    print(f"    12-24h: {d['b_12_24']:>9,} ({pct(d['b_12_24'], N)})")
    print(f"    >24h:   {d['b_24p']:>9,} ({pct(d['b_24p'], N)})")
    print(f"    before ED arrival (<0): {d['b_neg']:>6,} ({pct(d['b_neg'], N)})")

    print("\n-- C. COVERAGE BY WINDOW & ANCHOR -------------------------------------")
    print(f"  {'window':>8} {'anchor=ed_intime':>20} {'anchor=admittime':>20}")
    for lab, ed_k, adm_k in [("6h", "n_ed_6h", "n_adm_6h"),
                             ("12h", "n_ed_12h", "n_adm_12h"),
                             ("24h", "n_ed_24h", "n_adm_24h")]:
        print(f"  {lab:>8} {d[ed_k]:>10,} ({pct(d[ed_k],N):>6}) "
              f"   {d[adm_k]:>10,} ({pct(d[adm_k],N):>6})")
    print("=" * 72)

    # Plain-language verdict
    print("\nREAD:")
    art = d["n_board_gt6"] / N if N else 0
    gained = (d["n_ed_24h"] - d["n_ed_6h"])
    print(f"  - {pct(d['n_any_creat'], N)} of admissions have creatinine SOMEWHERE in "
          f"the stay, but only {pct(d['n_ed_6h'], N)} within 6h of ED arrival.")
    if art > 0.10:
        print(f"  - {pct(d['n_board_gt6'], N)} are admitted only AFTER the 6h ED window "
              f"closes -> a chunk of the gap is a window/anchor artifact, not missing labs.")
    print(f"  - Widening ED window 6h->24h recovers ~{gained:,} more admissions "
          f"({pct(gained, N)}).")
    print(f"  - Anchoring on admittime@6h gives {pct(d['n_adm_6h'], N)} coverage "
          f"(vs {pct(d['n_ed_6h'], N)} on ed_intime@6h).")

    con.close()


if __name__ == "__main__":
    main()
