"""Load: star schema in DuckDB. Each month is replaced atomically, so re-runs never duplicate rows."""
from pathlib import Path

import duckdb
import pandas as pd

FACT_COLUMNS = ["trip_id", "source_month", "vendor_id", "pickup_ts", "dropoff_ts", "pickup_date_key", "pickup_hour",
                "time_of_day", "pu_zone_id", "do_zone_id", "payment_type_id", "rate_code_id", "passenger_count",
                "trip_distance", "duration_min", "avg_speed_mph", "fare_amount", "extra", "mta_tax", "tip_amount",
                "tip_pct", "tolls_amount", "improvement_surcharge", "congestion_surcharge", "airport_fee", "total_amount"]
QUARANTINE_COLUMNS = ["source_month", "reason", "vendor_id", "pickup_ts", "dropoff_ts", "pu_zone_id", "do_zone_id",
                      "payment_type_id", "passenger_count", "trip_distance", "fare_amount", "tip_amount", "total_amount"]
# TLC data dictionary payment codes
PAYMENT_TYPES = [(0, "Flex Fare"), (1, "Credit card"), (2, "Cash"), (3, "No charge"), (4, "Dispute"),
                 (5, "Unknown"), (6, "Voided trip")]

SCHEMA = """
CREATE TABLE IF NOT EXISTS dim_zone (zone_id INTEGER PRIMARY KEY, borough VARCHAR, zone VARCHAR, service_zone VARCHAR);
CREATE TABLE IF NOT EXISTS dim_payment_type (payment_type_id INTEGER PRIMARY KEY, description VARCHAR);
CREATE TABLE IF NOT EXISTS dim_date (date_key INTEGER PRIMARY KEY, date DATE, year INTEGER, month INTEGER,
    day INTEGER, day_of_week INTEGER, day_name VARCHAR, is_weekend BOOLEAN);
CREATE TABLE IF NOT EXISTS fact_trips (trip_id BIGINT PRIMARY KEY, source_month VARCHAR, vendor_id INTEGER,
    pickup_ts TIMESTAMP, dropoff_ts TIMESTAMP, pickup_date_key INTEGER, pickup_hour INTEGER, time_of_day VARCHAR,
    pu_zone_id INTEGER, do_zone_id INTEGER, payment_type_id INTEGER, rate_code_id INTEGER, passenger_count INTEGER,
    trip_distance DOUBLE, duration_min DOUBLE, avg_speed_mph DOUBLE, fare_amount DOUBLE, extra DOUBLE, mta_tax DOUBLE,
    tip_amount DOUBLE, tip_pct DOUBLE, tolls_amount DOUBLE, improvement_surcharge DOUBLE, congestion_surcharge DOUBLE,
    airport_fee DOUBLE, total_amount DOUBLE);
CREATE TABLE IF NOT EXISTS quarantine_trips (source_month VARCHAR, reason VARCHAR, vendor_id INTEGER,
    pickup_ts TIMESTAMP, dropoff_ts TIMESTAMP, pu_zone_id INTEGER, do_zone_id INTEGER, payment_type_id INTEGER,
    passenger_count INTEGER, trip_distance DOUBLE, fare_amount DOUBLE, tip_amount DOUBLE, total_amount DOUBLE);
CREATE TABLE IF NOT EXISTS etl_run_log (run_id VARCHAR, month VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP,
    duration_s DOUBLE, rows_extracted BIGINT, rows_loaded BIGINT, rows_rejected BIGINT, status VARCHAR, message VARCHAR);
"""


def connect(path: str) -> duckdb.DuckDBPyConnection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(path)
    con.execute(SCHEMA)
    return con


def load_dimensions(con, zones: pd.DataFrame, month: str):
    """Dimensions are upserted, so they are safe to reload on every run."""
    z = zones.rename(columns={"LocationID": "zone_id", "Borough": "borough", "Zone": "zone"})[
        ["zone_id", "borough", "zone", "service_zone"]]
    con.execute("INSERT OR REPLACE INTO dim_zone SELECT * FROM z")
    con.executemany("INSERT OR REPLACE INTO dim_payment_type VALUES (?, ?)", PAYMENT_TYPES)
    dates = pd.DataFrame({"date": pd.date_range(f"{month}-01", periods=pd.Period(month).days_in_month)})
    con.execute("""INSERT OR REPLACE INTO dim_date
        SELECT CAST(strftime(date, '%Y%m%d') AS INTEGER), CAST(date AS DATE), year(date), month(date), day(date),
               isodow(date), dayname(date), isodow(date) >= 6 FROM dates""")


def load_month(con, month: str, clean: pd.DataFrame, rejected: pd.DataFrame):
    """Delete-then-insert for the month inside the caller's transaction (idempotent incremental load)."""
    fact = clean[FACT_COLUMNS]
    quarantine = rejected[QUARANTINE_COLUMNS]
    con.execute("DELETE FROM fact_trips WHERE source_month = ?", [month])
    con.execute("DELETE FROM quarantine_trips WHERE source_month = ?", [month])
    con.execute("INSERT INTO fact_trips SELECT * FROM fact")
    con.execute("INSERT INTO quarantine_trips SELECT * FROM quarantine")
