import pandas as pd
import pytest

from src.etl.config import load_config


def raw_trip(**overrides):
    """One valid raw TLC record (source column names); override fields to make it invalid."""
    row = {
        "VendorID": 2, "tpep_pickup_datetime": pd.Timestamp("2024-01-15 08:00"),
        "tpep_dropoff_datetime": pd.Timestamp("2024-01-15 08:20"), "passenger_count": 1.0, "trip_distance": 3.0,
        "RatecodeID": 1.0, "store_and_fwd_flag": "N", "PULocationID": 161, "DOLocationID": 236, "payment_type": 1,
        "fare_amount": 20.0, "extra": 0.0, "mta_tax": 0.5, "tip_amount": 5.0, "tolls_amount": 0.0,
        "improvement_surcharge": 1.0, "total_amount": 29.0, "congestion_surcharge": 2.5, "Airport_fee": 0.0,
    }
    row.update(overrides)
    return row


@pytest.fixture
def raw_df():
    rows = [raw_trip(tpep_pickup_datetime=pd.Timestamp("2024-01-15 08:00") + pd.Timedelta(minutes=i),
                     tpep_dropoff_datetime=pd.Timestamp("2024-01-15 08:20") + pd.Timedelta(minutes=i))
            for i in range(20)]
    rows += [
        raw_trip(trip_distance=0.0),                                                     # non_positive_distance
        raw_trip(fare_amount=-5.0),                                                      # non_positive_fare
        raw_trip(tpep_pickup_datetime=pd.Timestamp("2002-12-31 22:00"),
                 tpep_dropoff_datetime=pd.Timestamp("2002-12-31 22:30")),                # pickup_outside_month
        raw_trip(tpep_dropoff_datetime=pd.Timestamp("2024-01-15 07:00")),                # non_positive_duration
        raw_trip(PULocationID=None),                                                     # missing_required_field
    ]
    rows.append(rows[0])                                                                 # duplicate of a valid row
    return pd.DataFrame(rows)


@pytest.fixture
def zones():
    return pd.DataFrame({"LocationID": [161, 236], "Borough": ["Manhattan", "Manhattan"],
                         "Zone": ["Midtown Center", "Upper East Side North"], "service_zone": ["Yellow Zone"] * 2})


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c["warehouse_path"] = str(tmp_path / "test.duckdb")
    c["quality"] = {**c["quality"], "min_rows": 1, "max_rejection_pct": 50.0}
    return c
