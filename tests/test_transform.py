import pandas as pd

from src.etl.transform import transform

RULES = {"max_trip_hours": 6, "max_distance_miles": 100, "max_fare_usd": 1000, "max_passengers": 6}


def test_valid_rows_pass_and_invalid_rows_are_quarantined_with_reason(raw_df):
    clean, rejected = transform(raw_df, "2024-01", RULES)
    assert len(clean) == 20
    assert len(clean) + len(rejected) == len(raw_df)
    assert sorted(rejected["reason"]) == sorted([
        "non_positive_distance", "non_positive_fare", "pickup_outside_month",
        "non_positive_duration", "missing_required_field", "duplicate"])


def test_derived_features(raw_df):
    clean, _ = transform(raw_df, "2024-01", RULES)
    row = clean.iloc[0]
    assert row["duration_min"] == 20
    assert row["avg_speed_mph"] == 9.0          # 3 miles in 20 minutes
    assert row["tip_pct"] == 25.0               # 5 / 20
    assert row["pickup_date_key"] == 20240115
    assert row["time_of_day"] == "morning"


def test_trip_ids_are_unique_and_deterministic(raw_df):
    first, _ = transform(raw_df, "2024-01", RULES)
    second, _ = transform(raw_df, "2024-01", RULES)
    assert first["trip_id"].is_unique
    assert first["trip_id"].tolist() == second["trip_id"].tolist()


def test_speed_and_upper_bound_rules(raw_df):
    raw = pd.concat([raw_df.iloc[[0]].assign(trip_distance=60.0),        # 60 mi in 20 min = 180 mph
                     raw_df.iloc[[0]].assign(fare_amount=5000.0)])
    _, rejected = transform(raw, "2024-01", RULES)
    assert set(rejected["reason"]) == {"implausible_speed", "fare_too_high"}
