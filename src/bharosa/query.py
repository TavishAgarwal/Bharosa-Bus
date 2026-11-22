"""Query the crowding tables from the command line.

  python -m bharosa.query --route 717AUP --day weekday --band "pm peak 17-20"
  python -m bharosa.query --route 717AUP --day weekday --hour 18
Shows level, estimated load with its range, tickets and days behind each stretch. Cells without
enough tickets print as insufficient_evidence.
"""
from __future__ import annotations

import argparse

import duckdb

from . import config


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--route", required=True)
    ap.add_argument("--day", choices=["weekday", "weekend"], default="weekday")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--hour", type=int)
    g.add_argument("--band", help="early 5-6 | am peak 7-10 | midday 11-16 | pm peak 17-20 | late 21-4")
    a = ap.parse_args()
    if a.hour is None and not a.band:
        a.band = "pm peak 17-20"
    src = "crowding_levels" if a.hour is not None else "crowding_band_levels"
    where = "hour = ?" if a.hour is not None else "band = ?"
    val = a.hour if a.hour is not None else a.band
    q = f"""SELECT seg, from_stop, to_stop, level, abstain_reason, round(load) AS load, round(load_lo) AS low,
                   round(load_hi) AS high, n_tickets AS tickets, n_days AS days
            FROM read_parquet('{config.OUT_DIR / (src + '.parquet')}')
            WHERE route = upper(?) AND day_type = ? AND {where} ORDER BY seg"""
    df = duckdb.connect().execute(q, [a.route, a.day, val]).df()
    print(df.to_string(index=False) if len(df) else "no data for that route/time (route name, e.g. 717AUP, includes direction)")


if __name__ == "__main__":
    main()
