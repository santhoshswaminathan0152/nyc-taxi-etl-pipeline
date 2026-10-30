"""Data quality checks. Any failure aborts the load for that month."""
import duckdb
import pandas as pd

from src.etl.transform import REQUIRED


class DataQualityError(Exception):
    pass


def check_batch(clean: pd.DataFrame, rows_extracted: int, rows_rejected: int, q: dict) -> dict:
    """Checks on the transformed batch before it touches the warehouse."""
    rejection_pct = 100 * rows_rejected / max(rows_extracted, 1)
    null_pct = 100 * clean[REQUIRED].isna().mean().max() if len(clean) else 0.0
    results = {
        "row_count": len(clean) >= q["min_rows"],
        "rejection_rate": rejection_pct <= q["max_rejection_pct"],
        "required_nulls": null_pct <= q["max_null_pct"],
        "positive_values": bool((clean[["duration_min", "trip_distance", "fare_amount"]] > 0).all().all()),
        "rows_reconcile": len(clean) + rows_rejected == rows_extracted,
    }
    results = {k: bool(v) for k, v in results.items()}
    return {"passed": all(results.values()), "checks": results,
            "rejection_pct": round(float(rejection_pct), 2), "max_required_null_pct": round(float(null_pct), 4)}


def check_referential_integrity(con: duckdb.DuckDBPyConnection, month: str) -> dict:
    """Every foreign key in the newly loaded fact rows must exist in its dimension."""
    orphans = {
        "pu_zone": "SELECT count(*) FROM fact_trips f LEFT JOIN dim_zone z ON f.pu_zone_id = z.zone_id WHERE f.source_month = ? AND z.zone_id IS NULL",
        "do_zone": "SELECT count(*) FROM fact_trips f LEFT JOIN dim_zone z ON f.do_zone_id = z.zone_id WHERE f.source_month = ? AND z.zone_id IS NULL",
        "payment_type": "SELECT count(*) FROM fact_trips f LEFT JOIN dim_payment_type p ON f.payment_type_id = p.payment_type_id WHERE f.source_month = ? AND p.payment_type_id IS NULL",
        "date": "SELECT count(*) FROM fact_trips f LEFT JOIN dim_date d ON f.pickup_date_key = d.date_key WHERE f.source_month = ? AND d.date_key IS NULL",
    }
    counts = {k: con.execute(sql, [month]).fetchone()[0] for k, sql in orphans.items()}
    return {"passed": not any(counts.values()), "orphans": counts}
