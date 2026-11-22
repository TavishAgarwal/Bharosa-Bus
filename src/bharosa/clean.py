"""I-F1: read the tickets CSV, parse and validate, log row counts per step.

Writes data/interim/tickets.parquet and data/interim/clean_report.json.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import duckdb

from . import config

DATE_MIN, DATE_MAX = "2026-10-01", "2026-10-31"  # README: 1-31 October 2026


def _resolve_csv(path: Path, workdir: Path) -> Path:
    """Accept the CSV itself, or the .zip from the organisers (extracted once into workdir)."""
    if path.suffix.lower() == ".zip":
        zpath = path
    elif path.exists():
        return path
    else:
        zpath = path.with_suffix(path.suffix + ".zip")
        if not zpath.exists():
            zpath = path.parent / "October-Delhi.csv.zip"
    if not zpath.exists():
        raise FileNotFoundError(f"tickets not found: {path} (or a .zip next to it)")
    with zipfile.ZipFile(zpath) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX")]
        if not names:
            raise FileNotFoundError(f"no .csv inside {zpath}")
        workdir.mkdir(parents=True, exist_ok=True)
        out = workdir / Path(names[0]).name
        if not out.exists():
            with zf.open(names[0]) as src, open(out, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
    return out


def clean_tickets(csv_path: Path, out_path: Path, report_path: Path) -> dict:
    csv = _resolve_csv(Path(csv_path), Path(out_path).parent)
    out_path, report_path = Path(out_path), Path(report_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    # Everything read as text first: the README says amount is a quoted string and
    # vehicle_number is the literal NULL on about half the rows.
    con.execute(
        "CREATE TABLE raw AS SELECT * FROM read_csv(?, header=true, all_varchar=true, "
        "null_padding=true, ignore_errors=false)",
        [str(csv)],
    )
    cols = {r[0] for r in con.execute("DESCRIBE raw").fetchall()}
    need = {"passenger_count", "amount", "vehicle_number", "ticket_type_id", "end_stop_name",
            "route", "start_stop_name", "created_at", "is_ac"}
    if missing := need - cols:
        raise ValueError(f"tickets CSV is missing columns: {sorted(missing)}")

    steps: list[tuple[str, int]] = []

    def count(table: str) -> int:
        return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    steps.append(("raw_rows", count("raw")))

    # Parse. created_at carries an offset (+05:30); convert to IST wall-clock.
    con.execute("""
        CREATE TABLE parsed AS
        SELECT
          timezone('Asia/Kolkata', TRY_CAST(created_at AS TIMESTAMPTZ))            AS ts_ist,
          TRY_CAST(passenger_count AS INTEGER)                                      AS passenger_count,
          TRY_CAST(replace(trim(amount), '"', '') AS DOUBLE)                        AS amount,
          CASE WHEN upper(trim(coalesce(vehicle_number, ''))) IN ('', 'NULL', 'NONE', 'NAN')
               THEN NULL ELSE upper(trim(vehicle_number)) END                       AS vehicle_number,
          TRY_CAST(ticket_type_id AS INTEGER)                                       AS ticket_type_id,
          upper(regexp_replace(trim(coalesce(route, '')), '\\s+', '', 'g'))         AS route,
          regexp_replace(trim(coalesce(start_stop_name, '')), '\\s+', ' ', 'g')     AS start_stop_name,
          regexp_replace(trim(coalesce(end_stop_name, '')), '\\s+', ' ', 'g')       AS end_stop_name,
          CASE WHEN lower(trim(is_ac)) IN ('true', 't', '1', 'yes') THEN TRUE
               WHEN lower(trim(is_ac)) IN ('false', 'f', '0', 'no') THEN FALSE END  AS is_ac
        FROM raw
    """)

    def keep(name: str, where: str, src: str) -> str:
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM {src} WHERE {where}")
        steps.append((name, count(name)))
        return name

    t = keep("ok_timestamp", "ts_ist IS NOT NULL", "parsed")
    t = keep("ok_count", "passenger_count IS NOT NULL AND passenger_count > 0", t)
    t = keep("ok_route", "route <> '' AND upper(route) <> 'NULL'", t)
    t = keep("ok_stops", "start_stop_name <> '' AND end_stop_name <> '' "
             "AND upper(start_stop_name) <> 'NULL' AND upper(end_stop_name) <> 'NULL'", t)
    t = keep("ok_dates",
             f"CAST(ts_ist AS DATE) BETWEEN DATE '{DATE_MIN}' AND DATE '{DATE_MAX}'", t)

    con.execute(f"CREATE TABLE deduped AS SELECT DISTINCT * FROM {t}")
    steps.append(("deduped", count("deduped")))

    con.execute("""
        CREATE TABLE final AS
        SELECT
          ts_ist,
          CAST(ts_ist AS DATE)                                  AS date,
          hour(ts_ist)                                          AS hour,
          isodow(ts_ist) - 1                                    AS dow,
          CASE WHEN isodow(ts_ist) >= 6 THEN 'weekend' ELSE 'weekday' END AS day_type,
          passenger_count, amount, vehicle_number, ticket_type_id, route,
          start_stop_name, end_stop_name, is_ac,
          (lower(start_stop_name) = lower(end_stop_name))       AS same_stop
        FROM deduped
        ORDER BY ts_ist
    """)
    con.execute("COPY final TO ? (FORMAT PARQUET)", [str(out_path)])

    stats = con.execute("""
        SELECT count(*), sum(passenger_count), min(date), max(date),
               avg((vehicle_number IS NULL)::INT), avg(same_stop::INT), count(DISTINCT route)
        FROM final
    """).fetchone()
    report = {
        "source_csv": str(csv),
        "steps": [{"step": n, "rows": r} for n, r in steps],
        "final_rows": stats[0],
        "final_passengers": int(stats[1] or 0),
        "date_min": str(stats[2]), "date_max": str(stats[3]),
        "vehicle_number_blank_share": round(stats[4] or 0, 4),
        "same_stop_share": round(stats[5] or 0, 4),
        "distinct_routes": stats[6],
        "dropped_total": steps[0][1] - stats[0],
    }
    report_path.write_text(json.dumps(report, indent=2))
    for s in report["steps"]:
        print(f"{s['step']:>14}: {s['rows']:>10,}")
    print(f"{'final':>14}: {report['final_rows']:>10,}  (dropped {report['dropped_total']:,})")
    return report


def run() -> None:
    clean_tickets(
        config.TICKETS_CSV,
        config.INTERIM_DIR / "tickets.parquet",
        config.INTERIM_DIR / "clean_report.json",
    )


if __name__ == "__main__":
    run()
