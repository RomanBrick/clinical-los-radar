"""
Break-even / ROI calculator for the renal wedge + "protocolized early creatinine".

The idea under test: have the hospital draw a creatinine early (within the first
hours) so the renal-dysfunction risk can be scored in time for case management.

IMPORTANT FRAMING (read this):
  The creatinine test is trivially cheap; it is NOT what saves bed-days. The
  test only buys EARLIER INFORMATION. Whether earlier information actually
  shortens length of stay is an UNPROVEN causal claim that a pilot must test.
  So this script does NOT pretend to prove savings. Instead it answers the
  honest question:
      "How small a LOS reduction would already pay for the test program,
       and what is the ROI under modest, explicit reduction scenarios?"

What it computes from YOUR DuckDB (read-only) at a chosen window:
  - $ at risk = excess bed-days in the renal cohort x bed-day cost
  - Cost of protocol = (admissions lacking an early creatinine) x test cost
  - Break-even LOS reduction needed to cover the test program (expect: tiny)
  - ROI under 5% / 10% / 20% excess-LOS-reduction scenarios

Usage:
    python scripts/wedge_roi_breakeven.py
    python scripts/wedge_roi_breakeven.py --window-hours 24 --bed-day-cost 2500 --test-cost 10
"""

import argparse
import os
import sys
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREAT_ITEMID = 50912  # creatinine
BUN_ITEMID = 51006    # BUN


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
        "select table_schema, table_name from information_schema.tables "
        "where table_type in ('BASE TABLE','VIEW')"
    ).fetchall()
    matches = [(s, t) for (s, t) in rows
               if all(k.lower() in t.lower() for k in keywords)]
    if not matches:
        raise RuntimeError(f"No table matching keywords {keywords}.")

    def score(item):
        s = item[0].lower()
        return (("marts" in s or "intermediate" in s or "staging" in s), "main" in s)

    matches.sort(key=score, reverse=True)
    s, t = matches[0]
    return f'"{s}"."{t}"'


def money(x):
    return f"${x:,.0f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db")
    ap.add_argument("--window-hours", type=int, default=24,
                    help="Window from ED arrival to detect renal dysfunction (default 24)")
    ap.add_argument("--creat-high", type=float, default=1.3)
    ap.add_argument("--bun-high", type=float, default=20.0)
    ap.add_argument("--bed-day-cost", type=float, default=2500.0,
                    help="ASSUMPTION: cost of one inpatient bed-day in $ (default 2500)")
    ap.add_argument("--test-cost", type=float, default=10.0,
                    help="ASSUMPTION: marginal cost of one early creatinine/BMP in $ (default 10)")
    args = ap.parse_args()

    W = args.window_hours
    db_path = resolve_db_path(args.db)
    print(f"Using DuckDB: {db_path}")
    con = duckdb.connect(str(db_path), read_only=True)

    spine_tbl = find_table(con, "encounter_spine")
    labs_tbl = find_table(con, "stg_labevents")
    labels_tbl = find_table(con, "labels_long_stay")
    print(f"Spine:  {spine_tbl}\nLabs:   {labs_tbl}\nLabels: {labels_tbl}")

    sql = f"""
    with spine as (
        select hadm_id, ed_intime,
               ed_intime + interval '{W} hours' as wend, dischtime
        from {spine_tbl}
    ),
    labw as (
        select s.hadm_id,
            max(case when l.itemid = {CREAT_ITEMID} then l.valuenum end) as creat_max,
            max(case when l.itemid = {BUN_ITEMID}   then l.valuenum end) as bun_max,
            max(case when l.itemid = {CREAT_ITEMID} then 1 else 0 end)   as has_creat
        from spine s
        left join {labs_tbl} l
            on l.hadm_id = s.hadm_id
           and l.valuenum is not null
           and l.itemid in ({CREAT_ITEMID}, {BUN_ITEMID})
           and l.charttime >= s.ed_intime
           and l.charttime <  s.wend
        group by s.hadm_id
    ),
    joined as (
        select
            lb.hadm_id,
            lb.long_stay_flag,
            lb.los_days,
            coalesce(w.has_creat, 0) as has_creat,
            case when coalesce(w.creat_max, 0) > {args.creat_high}
                   or coalesce(w.bun_max, 0)  > {args.bun_high}
                 then 1 else 0 end as renal_flag
        from {labels_tbl} lb
        left join labw w on lb.hadm_id = w.hadm_id
    )
    select
        count(*)                                            as n_total,
        sum(has_creat)                                      as n_with_early_creat,
        sum(renal_flag)                                     as n_renal,
        avg(long_stay_flag)                                 as long_rate_overall,
        avg(case when renal_flag=1 then long_stay_flag end) as long_rate_renal,
        median(case when renal_flag=1 then los_days end)    as los_med_renal,
        median(case when renal_flag=0 then los_days end)    as los_med_nonrenal
    from joined
    """
    r = con.execute(sql).fetchone()
    (n_total, n_with_early, n_renal, long_overall, long_renal,
     los_med_renal, los_med_nonrenal) = r
    con.close()

    # --- Economics ---------------------------------------------------------
    excess_per = (los_med_renal or 0) - (los_med_nonrenal or 0)   # bed-days / renal adm
    total_excess = excess_per * n_renal
    dollars_at_risk = total_excess * args.bed_day_cost

    n_need_test = n_total - n_with_early          # admissions lacking an early creatinine
    program_cost = n_need_test * args.test_cost   # protocolized early draw for the gap

    # Break-even: LOS reduction (per renal adm) that just covers the test program
    break_even_days = program_cost / (n_renal * args.bed_day_cost) if n_renal else float("nan")

    print("\n" + "=" * 72)
    print(f"  RENAL WEDGE — BREAK-EVEN / ROI  (window = first {W}h from ED arrival)")
    print("=" * 72)
    print("  ASSUMPTIONS (override with flags):")
    print(f"    bed-day cost = {money(args.bed_day_cost)}   |   early creatinine = {money(args.test_cost)}")
    print(f"    renal dysfunction = creatinine_max > {args.creat_high} OR bun_max > {args.bun_high}")

    print("\n-- COHORT -------------------------------------------------------------")
    print(f"  ED->inpatient admissions:             {n_total:>12,}")
    print(f"  ...with early creatinine ({W}h):       {n_with_early:>12,} "
          f"({n_with_early/n_total*100:.1f}%)")
    print(f"  ...lacking early creatinine (gap):    {n_need_test:>12,} "
          f"({n_need_test/n_total*100:.1f}%)")
    print(f"  Renal-dysfunction cohort:             {n_renal:>12,} "
          f"({n_renal/n_total*100:.1f}%)")
    print(f"  Prolonged-LOS rate renal/overall:     "
          f"{long_renal*100:.1f}% / {long_overall*100:.1f}%")

    print("\n-- THE PRIZE (excess bed-days at risk) --------------------------------")
    print(f"  Excess bed-days per renal admission:  {excess_per:>12.2f}  (median basis)")
    print(f"  Aggregate excess bed-days:            {total_excess:>12,.0f}")
    print(f"  $ at risk in renal cohort:            {money(dollars_at_risk):>12}")

    print("\n-- COST OF THE PROTOCOL (early creatinine for the gap) ----------------")
    print(f"  Tests to add (gap admissions):        {n_need_test:>12,}")
    print(f"  Protocol cost:                        {money(program_cost):>12}")
    print(f"  Protocol cost as % of $ at risk:      "
          f"{program_cost/dollars_at_risk*100:>11.2f}%")

    print("\n-- BREAK-EVEN -------------------------------------------------------- ")
    print(f"  LOS reduction per renal admission to")
    print(f"  cover the ENTIRE test program:        {break_even_days*24:>10.2f} hours "
          f"({break_even_days:.4f} days)")
    print("  ^ Essentially zero. The test cost is NOT the question.")

    print("\n-- ROI IF EARLY ACTION CUTS EXCESS LOS (scenarios) --------------------")
    print(f"  {'reduction':>10} {'bed-days saved':>16} {'$ saved':>16} "
          f"{'net vs program':>16} {'ROI':>8}")
    for red in (0.05, 0.10, 0.20):
        saved_days = total_excess * red
        saved_usd = saved_days * args.bed_day_cost
        net = saved_usd - program_cost
        roi = saved_usd / program_cost if program_cost else float("inf")
        print(f"  {red*100:>9.0f}% {saved_days:>16,.0f} {money(saved_usd):>16} "
              f"{money(net):>16} {roi:>7.0f}x")
    print("=" * 72)

    print("\nHONEST CAVEAT:")
    print("  - These $ are over the full MIMIC history (single center, ~10y), NOT annual.")
    print("  - 'Bed-days saved' ASSUMES earlier risk info -> earlier case management ->")
    print("    shorter stay. That causal link is UNPROVEN here and is exactly what a")
    print("    prospective design-partner pilot must measure.")
    print("  - Many long stays are driven by post-acute placement / prior-auth delays")
    print("    (per AHA report) which an early creatinine does not fix.")
    print("  - Bottom line: the test is negligibly cheap; the real, falsifiable question")
    print("    is the achievable LOS reduction. Pilot should target that number.")


if __name__ == "__main__":
    main()
