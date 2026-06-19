"""
Wedge feasibility check: "Renal-dysfunction" cohort vs prolonged length of stay.

Goal (no modeling yet — just sizing the opportunity on YOUR data):
  1. How many ED->inpatient admissions show renal dysfunction in the first 0-6h?
  2. Do those patients actually have more "longer stays" (LOS >= P75)?
  3. How many EXTRA bed-days (and $) does the cohort represent?
  4. Is there any early signal at all (does 0-6h creatinine separate long vs short stays)?

This reads the dbt-built tables already in your DuckDB (Phase 3). It does NOT
rebuild anything and opens the DB read-only. If your table/schema names differ,
it auto-discovers them by keyword.

Usage:
    python scripts/wedge_feasibility_renal.py
    python scripts/wedge_feasibility_renal.py --db /path/to/mimic.duckdb --cost-per-day 2500
    python scripts/wedge_feasibility_renal.py --write     # also save docs/wedge_feasibility_renal.{md,json}

Definitions (configurable):
    Renal dysfunction (first 6h) = creatinine_max > CREAT_HIGH  OR  bun_max > BUN_HIGH
    Normal lab reference ranges come from your seed: creatinine 0.7-1.3, BUN 7-20.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Reference ranges from cdsp/seeds/lab_thresholds.csv
CREAT_HIGH_DEFAULT = 1.3   # mg/dL  (normal 0.7-1.3)
BUN_HIGH_DEFAULT = 20.0    # mg/dL  (normal 7-20)


def resolve_db_path(cli_path: str | None) -> Path:
    """Pick the DuckDB file from CLI arg, env, or common locations."""
    candidates = []
    if cli_path:
        candidates.append(Path(cli_path))
    if os.environ.get("CDSP_DB"):
        candidates.append(Path(os.environ["CDSP_DB"]))
    candidates += [
        PROJECT_ROOT / "data" / "processed" / "mimic.duckdb",
        PROJECT_ROOT / "cdsp" / "data" / "processed" / "mimic.duckdb",
        Path("data/processed/mimic.duckdb"),
    ]
    for c in candidates:
        if c.exists():
            return c
    print("ERROR: could not find the DuckDB file. Tried:")
    for c in candidates:
        print(f"  - {c}")
    print("\nPass it explicitly:  --db C:\\path\\to\\mimic.duckdb  (or set CDSP_DB).")
    sys.exit(1)


def find_table(con, *keywords: str) -> str:
    """Find a fully-qualified table whose name contains ALL keywords.
    Prefers schemas with 'marts'/'intermediate' in the name."""
    rows = con.execute(
        """
        select table_schema, table_name
        from information_schema.tables
        where table_type in ('BASE TABLE', 'VIEW')
        """
    ).fetchall()
    matches = [
        (s, t) for (s, t) in rows
        if all(k.lower() in t.lower() for k in keywords)
    ]
    if not matches:
        raise RuntimeError(
            f"No table matching keywords {keywords}. "
            f"Have you built the Phase 3 dbt models? (dbt build)"
        )

    def score(item):
        s, _ = item
        s = s.lower()
        return (("marts" in s or "intermediate" in s), "main" in s)

    matches.sort(key=score, reverse=True)
    s, t = matches[0]
    return f'"{s}"."{t}"'


def pct(x):
    return f"{x*100:.1f}%"


def run(con, labs_tbl, labels_tbl, creat_high, bun_high, cost_per_day):
    """Compute the feasibility metrics for one renal-dysfunction definition."""
    sql = f"""
    with base as (
        select
            lb.hadm_id,
            lb.long_stay_flag,
            lb.los_days,
            lb.p75_los_days,
            coalesce(la.creatinine_measured_flag, 0) as creat_measured,
            coalesce(la.bun_measured_flag, 0)        as bun_measured,
            la.creatinine_max,
            la.bun_max,
            -- renal dysfunction within first 6h
            case
              when coalesce(la.creatinine_max, 0) > {creat_high}
                or coalesce(la.bun_max, 0) > {bun_high}
              then 1 else 0
            end as renal_flag
        from {labels_tbl} lb
        left join {labs_tbl} la on lb.hadm_id = la.hadm_id
    )
    select
        count(*)                                              as n_total,
        sum(creat_measured)                                   as n_creat_measured,
        sum(renal_flag)                                       as n_renal,
        avg(long_stay_flag)                                   as long_rate_overall,
        avg(case when renal_flag=1 then long_stay_flag end)   as long_rate_renal,
        avg(case when renal_flag=0 then long_stay_flag end)   as long_rate_nonrenal,
        avg(case when renal_flag=1 then los_days end)         as los_mean_renal,
        avg(case when renal_flag=0 then los_days end)         as los_mean_nonrenal,
        median(case when renal_flag=1 then los_days end)      as los_med_renal,
        median(case when renal_flag=0 then los_days end)      as los_med_nonrenal,
        max(p75_los_days)                                     as p75_los,
        -- early-signal sanity: mean 0-6h max creatinine, long vs short stay (renal cohort)
        avg(case when renal_flag=1 and long_stay_flag=1 then creatinine_max end) as creat_long,
        avg(case when renal_flag=1 and long_stay_flag=0 then creatinine_max end) as creat_short
    from base
    """
    r = con.execute(sql).fetchone()
    cols = [
        "n_total", "n_creat_measured", "n_renal",
        "long_rate_overall", "long_rate_renal", "long_rate_nonrenal",
        "los_mean_renal", "los_mean_nonrenal", "los_med_renal", "los_med_nonrenal",
        "p75_los", "creat_long", "creat_short",
    ]
    d = dict(zip(cols, r))

    # Derived: excess bed-days attributable to the renal cohort (vs non-renal),
    # using median to blunt the long LOS outliers, and aggregate $ at cost_per_day.
    excess_per_med = (d["los_med_renal"] or 0) - (d["los_med_nonrenal"] or 0)
    excess_per_mean = (d["los_mean_renal"] or 0) - (d["los_mean_nonrenal"] or 0)
    d["excess_beddays_per_adm_median"] = excess_per_med
    d["excess_beddays_per_adm_mean"] = excess_per_mean
    d["excess_beddays_total_median"] = excess_per_med * (d["n_renal"] or 0)
    d["excess_beddays_dollars_median"] = excess_per_med * (d["n_renal"] or 0) * cost_per_day
    d["lift_vs_overall"] = (
        (d["long_rate_renal"] / d["long_rate_overall"])
        if d["long_rate_overall"] else float("nan")
    )
    d["creat_high"] = creat_high
    d["bun_high"] = bun_high
    return d


def print_report(d, cost_per_day):
    print("\n" + "=" * 72)
    print("  WEDGE FEASIBILITY — RENAL-DYSFUNCTION COHORT vs PROLONGED LOS")
    print("=" * 72)
    print(f"  Renal dysfunction (0-6h) = creatinine_max > {d['creat_high']} "
          f"OR bun_max > {d['bun_high']}")
    print(f"  Bed-day cost assumption  = ${cost_per_day:,.0f}/day (illustrative)\n")

    print("-- 1. COHORT SIZE -----------------------------------------------------")
    print(f"  ED->inpatient admissions (total):     {d['n_total']:>10,}")
    print(f"  ...with creatinine measured in 0-6h:  {d['n_creat_measured']:>10,} "
          f"({pct(d['n_creat_measured']/d['n_total'])} coverage)")
    print(f"  ...with renal dysfunction in 0-6h:    {d['n_renal']:>10,} "
          f"({pct(d['n_renal']/d['n_total'])} of all admissions)")

    print("\n-- 2. DOES IT DRIVE LONGER STAYS? (LOS >= P75 = "
          f"{d['p75_los']:.1f} days) ------")
    print(f"  Prolonged-LOS rate, ALL admissions:   {pct(d['long_rate_overall'])}")
    print(f"  Prolonged-LOS rate, RENAL cohort:     {pct(d['long_rate_renal'])}")
    print(f"  Prolonged-LOS rate, NON-renal:        {pct(d['long_rate_nonrenal'])}")
    print(f"  >> Lift (renal vs overall):           {d['lift_vs_overall']:.2f}x")

    print("\n-- 3. EXTRA BED-DAYS / $ -----------------------------------------------")
    print(f"  Median LOS  renal / non-renal:        "
          f"{d['los_med_renal']:.1f} / {d['los_med_nonrenal']:.1f} days")
    print(f"  Mean   LOS  renal / non-renal:        "
          f"{d['los_mean_renal']:.1f} / {d['los_mean_nonrenal']:.1f} days "
          f"(mean inflated by outliers)")
    print(f"  Excess bed-days per renal admission:  "
          f"{d['excess_beddays_per_adm_median']:.2f} (median basis)")
    print(f"  Aggregate excess bed-days (cohort):   "
          f"{d['excess_beddays_total_median']:,.0f}")
    print(f"  Illustrative $ at ${cost_per_day:,.0f}/day:      "
          f"${d['excess_beddays_dollars_median']:,.0f}")

    print("\n-- 4. EARLY SIGNAL SANITY (renal cohort) -------------------------------")
    cl, cs = d["creat_long"], d["creat_short"]
    if cl and cs:
        print(f"  Mean 0-6h max creatinine, LONG stay:  {cl:.2f} mg/dL")
        print(f"  Mean 0-6h max creatinine, SHORT stay: {cs:.2f} mg/dL")
        verdict = "separation present" if cl > cs else "WEAK/INVERTED — investigate"
        print(f"  >> {verdict} (long minus short = {cl-cs:+.2f})")
    else:
        print("  Not enough data to compute creatinine separation.")
    print("=" * 72)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", help="Path to mimic.duckdb (else env CDSP_DB / common paths)")
    ap.add_argument("--cost-per-day", type=float, default=2500.0,
                    help="Illustrative bed-day cost in $ (default 2500)")
    ap.add_argument("--creat-high", type=float, default=CREAT_HIGH_DEFAULT,
                    help="Creatinine upper-normal threshold (default 1.3)")
    ap.add_argument("--bun-high", type=float, default=BUN_HIGH_DEFAULT,
                    help="BUN upper-normal threshold (default 20)")
    ap.add_argument("--write", action="store_true",
                    help="Also write docs/wedge_feasibility_renal.{md,json}")
    args = ap.parse_args()

    db_path = resolve_db_path(args.db)
    print(f"Using DuckDB: {db_path}")
    con = duckdb.connect(str(db_path), read_only=True)

    labs_tbl = find_table(con, "labs_0_6h_dynamic")
    labels_tbl = find_table(con, "labels_long_stay")
    print(f"Labs table:   {labs_tbl}")
    print(f"Labels table: {labels_tbl}")

    # Primary definition
    primary = run(con, labs_tbl, labels_tbl, args.creat_high, args.bun_high,
                  args.cost_per_day)
    print_report(primary, args.cost_per_day)

    # Sensitivity sweep: how the cohort/lift moves as we tighten the definition
    print("\n-- 5. SENSITIVITY (how definition changes the cohort) ------------------")
    print(f"  {'creat>':>7} {'bun>':>6} {'n_renal':>10} {'%total':>8} "
          f"{'long_rate':>10} {'lift':>6}")
    sweep = [(1.3, 20), (1.5, 25), (2.0, 30), (2.5, 40), (3.0, 50)]
    sweep_out = []
    for ch, bh in sweep:
        s = run(con, labs_tbl, labels_tbl, ch, bh, args.cost_per_day)
        print(f"  {ch:>7.1f} {bh:>6.0f} {s['n_renal']:>10,} "
              f"{pct(s['n_renal']/s['n_total']):>8} "
              f"{pct(s['long_rate_renal']):>10} {s['lift_vs_overall']:>5.2f}x")
        sweep_out.append({
            "creat_high": ch, "bun_high": bh, "n_renal": s["n_renal"],
            "pct_total": s["n_renal"] / s["n_total"],
            "long_rate_renal": s["long_rate_renal"],
            "lift": s["lift_vs_overall"],
        })

    con.close()

    if args.write:
        docs = PROJECT_ROOT / "docs"
        docs.mkdir(exist_ok=True)
        out = {"primary": primary, "sensitivity": sweep_out,
               "cost_per_day": args.cost_per_day}
        (docs / "wedge_feasibility_renal.json").write_text(
            json.dumps(out, indent=2, default=float))
        md = [
            "# Wedge Feasibility — Renal-Dysfunction Cohort vs Prolonged LOS",
            "",
            f"- Definition: creatinine_max > {primary['creat_high']} OR "
            f"bun_max > {primary['bun_high']} (first 0-6h)",
            f"- Bed-day cost: ${args.cost_per_day:,.0f} (illustrative)",
            "",
            "## Headline",
            f"- Cohort: **{primary['n_renal']:,}** admissions "
            f"({pct(primary['n_renal']/primary['n_total'])} of all ED->inpatient)",
            f"- Prolonged-LOS rate: **{pct(primary['long_rate_renal'])}** "
            f"vs {pct(primary['long_rate_overall'])} overall "
            f"(**{primary['lift_vs_overall']:.2f}x** lift)",
            f"- Excess bed-days: **{primary['excess_beddays_per_adm_median']:.2f}/adm** "
            f"(median), ~{primary['excess_beddays_total_median']:,.0f} aggregate "
            f"(~${primary['excess_beddays_dollars_median']:,.0f})",
            f"- Early signal: mean 0-6h creatinine long={primary['creat_long']:.2f} "
            f"vs short={primary['creat_short']:.2f} mg/dL",
        ]
        (docs / "wedge_feasibility_renal.md").write_text("\n".join(md))
        print(f"\nWrote {docs/'wedge_feasibility_renal.md'} and .json")


if __name__ == "__main__":
    main()
