from src.etl.quality import check_batch
from src.etl.transform import transform
from tests.test_transform import RULES

QUALITY = {"min_rows": 1, "max_rejection_pct": 50.0, "max_null_pct": 1.0}


def test_batch_passes_on_good_data(raw_df):
    clean, rejected = transform(raw_df, "2024-01", RULES)
    result = check_batch(clean, len(raw_df), len(rejected), QUALITY)
    assert result["passed"], result


def test_batch_fails_when_rejection_rate_too_high(raw_df):
    clean, rejected = transform(raw_df, "2024-01", RULES)
    result = check_batch(clean, len(raw_df), len(rejected), {**QUALITY, "max_rejection_pct": 5.0})
    assert not result["passed"]
    assert result["checks"]["rejection_rate"] is False


def test_batch_fails_when_rows_do_not_reconcile(raw_df):
    clean, rejected = transform(raw_df, "2024-01", RULES)
    result = check_batch(clean, len(raw_df) + 10, len(rejected), QUALITY)
    assert result["checks"]["rows_reconcile"] is False
