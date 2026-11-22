import json

import duckdb

from bharosa.clean import clean_tickets

HEADER = "passenger_count,amount,vehicle_number,ticket_type_id,end_stop_name,route,start_stop_name,created_at,is_ac\n"
ROWS = [
    '1,"22",DL1PD6826,1,Mahamaya Flyover West,8UP,Ali Village,2026-10-28 10:19:18.780611+05:30,True',   # good, Wed
    '2,"15",NULL,1,Nehru Place,8UP,Ali  Village,2026-10-31 23:30:00.000000+05:30,False',                # blank vehicle, spaces, Sat? (31 Oct 2026 = Sat)
    '0,"10",DL1X1,1,B,8UP,A,2026-10-05 08:00:00.000000+05:30,True',                                    # passenger_count 0 -> drop
    '1,"10",DL1X1,1,B,8UP,A,not-a-date,True',                                                          # bad timestamp -> drop
    '1,"10",DL1X1,1,B,,A,2026-10-05 08:00:00.000000+05:30,True',                                       # empty route -> drop
    '1,"10",DL1X1,1,,8UP,A,2026-10-05 08:00:00.000000+05:30,True',                                     # empty end stop -> drop
    '1,"10",DL1X1,1,B,8UP,A,2026-11-02 08:00:00.000000+05:30,True',                                    # out of range -> drop
    '1,"22",DL1PD6826,1,Mahamaya Flyover West,8UP,Ali Village,2026-10-28 10:19:18.780611+05:30,True',   # exact duplicate -> drop
    '1,"12",,2,Same Stop,12,same stop,2026-10-04 09:00:00.000000+05:30,False',                         # same_stop flag, Sunday
    '1,"12",,2,B,8up,A,2026-10-30 18:00:00.000000+00:00,True',                                         # UTC offset -> 23:30 IST
]


def _run(tmp_path):
    csv = tmp_path / "t.csv"
    csv.write_text(HEADER + "\n".join(ROWS) + "\n")
    out, rep = tmp_path / "t.parquet", tmp_path / "r.json"
    report = clean_tickets(csv, out, rep)
    df = duckdb.connect().execute("SELECT * FROM read_parquet(?) ORDER BY ts_ist", [str(out)]).df()
    return report, df


def test_counts_and_drops(tmp_path):
    report, df = _run(tmp_path)
    assert report["steps"][0] == {"step": "raw_rows", "rows": 10}
    assert report["final_rows"] == 4
    assert report["dropped_total"] == 6
    assert json.loads((tmp_path / "r.json").read_text())["final_rows"] == 4


def test_fields(tmp_path):
    _, df = _run(tmp_path)
    assert set(df["route"]) == {"8UP", "12"}                      # upper-cased, spaces removed
    assert (df["start_stop_name"] == "Ali Village").sum() == 2    # double space collapsed
    assert df["vehicle_number"].isna().sum() == 3                 # 'NULL' and '' become NULL
    assert df["same_stop"].sum() == 1
    row = df[df["route"] == "12"].iloc[0]
    assert row["day_type"] == "weekend" and row["dow"] == 6       # 4 Oct 2026 is a Sunday
    utc = df[df["ts_ist"].astype(str).str.contains("2026-10-30 23:30")]
    assert len(utc) == 1                                          # 18:00 UTC -> 23:30 IST
    assert df["amount"].dtype == float
