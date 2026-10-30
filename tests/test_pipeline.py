import pytest

from src.etl import pipeline
from src.etl.load import connect


@pytest.fixture
def patched_extract(monkeypatch, raw_df, zones):
    monkeypatch.setattr(pipeline, "extract_trips", lambda month, cfg: raw_df.copy())
    monkeypatch.setattr(pipeline, "extract_zones", lambda cfg: zones.copy())


def counts(con):
    return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ["fact_trips", "quarantine_trips", "etl_run_log"]}


def test_rerunning_a_month_is_idempotent(cfg, patched_extract):
    con = connect(cfg["warehouse_path"])
    first = pipeline.run_month(con, "2024-01", cfg, "run1")
    after_first = counts(con)
    second = pipeline.run_month(con, "2024-01", cfg, "run2")
    after_second = counts(con)
    assert first["status"] == second["status"] == "success"
    assert after_first["fact_trips"] == after_second["fact_trips"] == 20
    assert after_first["quarantine_trips"] == after_second["quarantine_trips"] == 6
    assert after_second["etl_run_log"] == 2          # every run is logged


def test_referential_integrity_failure_rolls_back(cfg, patched_extract, monkeypatch, zones):
    monkeypatch.setattr(pipeline, "extract_zones", lambda c: zones[zones["LocationID"] != 236])  # dropoff zone missing
    con = connect(cfg["warehouse_path"])
    result = pipeline.run_month(con, "2024-01", cfg, "run1")
    assert result["status"] == "failed"
    assert counts(con)["fact_trips"] == 0            # nothing half-loaded
    status, message = con.execute("SELECT status, message FROM etl_run_log").fetchone()
    assert status == "failed" and "referential integrity" in message


def test_failed_quality_check_blocks_load(cfg, patched_extract):
    cfg["quality"]["max_rejection_pct"] = 1.0
    con = connect(cfg["warehouse_path"])
    assert pipeline.run_month(con, "2024-01", cfg, "run1")["status"] == "failed"
    assert counts(con)["fact_trips"] == 0
