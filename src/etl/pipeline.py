"""ETL entry point.

Usage: python -m src.etl.pipeline --months 2024-01 2024-02 2024-03
"""
import argparse
import json
import logging
import time
import uuid
from datetime import datetime

from src.etl.config import load_config
from src.etl.extract import extract_trips, extract_zones
from src.etl.load import connect, load_dimensions, load_month
from src.etl.quality import DataQualityError, check_batch, check_referential_integrity
from src.etl.transform import transform

log = logging.getLogger("etl")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), "level": record.levelname,
                 "logger": record.name, "msg": record.getMessage()}
        entry.update(getattr(record, "extra_fields", {}))
        return json.dumps(entry)


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def run_month(con, month: str, cfg: dict, run_id: str) -> dict:
    started = datetime.now()
    t0 = time.time()
    stats = {"rows_extracted": 0, "rows_loaded": 0, "rows_rejected": 0}
    try:
        raw = extract_trips(month, cfg)
        stats["rows_extracted"] = len(raw)
        clean, rejected = transform(raw, month, cfg["rules"])
        stats["rows_rejected"] = len(rejected)

        batch = check_batch(clean, len(raw), len(rejected), cfg["quality"])
        if not batch["passed"]:
            raise DataQualityError(f"batch checks failed: {batch}")

        con.execute("BEGIN TRANSACTION")
        try:
            load_dimensions(con, extract_zones(cfg), month)
            load_month(con, month, clean, rejected)
            ri = check_referential_integrity(con, month)
            if not ri["passed"]:
                raise DataQualityError(f"referential integrity failed: {ri['orphans']}")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        stats["rows_loaded"] = len(clean)
        status, message = "success", json.dumps({"quality": batch["checks"], "rejection_pct": batch["rejection_pct"]})
    except Exception as e:
        status, message = "failed", str(e)[:500]
    duration = round(time.time() - t0, 2)
    con.execute("INSERT INTO etl_run_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [run_id, month, started, datetime.now(), duration, stats["rows_extracted"], stats["rows_loaded"],
                 stats["rows_rejected"], status, message])
    result = {"month": month, "status": status, "duration_s": duration, **stats}
    (log.info if status == "success" else log.error)(f"month {status}", extra={"extra_fields": {**result, "run_id": run_id}})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="NYC Yellow Taxi ETL pipeline")
    parser.add_argument("--months", nargs="+", required=True, help="Months to process, e.g. 2024-01 2024-02")
    args = parser.parse_args(argv)
    setup_logging()
    cfg = load_config()
    run_id = uuid.uuid4().hex[:12]
    con = connect(cfg["warehouse_path"])
    log.info("run started", extra={"extra_fields": {"run_id": run_id, "months": args.months}})
    results = [run_month(con, m, cfg, run_id) for m in args.months]
    con.close()
    failed = [r["month"] for r in results if r["status"] != "success"]
    log.info("run finished", extra={"extra_fields": {"run_id": run_id, "failed_months": failed}})
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
