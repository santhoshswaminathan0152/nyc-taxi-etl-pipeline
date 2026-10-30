"""Transform: standardise columns, flag invalid records with a reason and derive analytics features."""
import numpy as np
import pandas as pd

RENAME = {
    "VendorID": "vendor_id", "tpep_pickup_datetime": "pickup_ts", "tpep_dropoff_datetime": "dropoff_ts",
    "passenger_count": "passenger_count", "trip_distance": "trip_distance", "RatecodeID": "rate_code_id",
    "PULocationID": "pu_zone_id", "DOLocationID": "do_zone_id", "payment_type": "payment_type_id",
    "fare_amount": "fare_amount", "extra": "extra", "mta_tax": "mta_tax", "tip_amount": "tip_amount",
    "tolls_amount": "tolls_amount", "improvement_surcharge": "improvement_surcharge",
    "total_amount": "total_amount", "congestion_surcharge": "congestion_surcharge", "Airport_fee": "airport_fee",
}
REQUIRED = ["pickup_ts", "dropoff_ts", "pu_zone_id", "do_zone_id", "payment_type_id", "fare_amount", "total_amount"]


def standardise(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(columns={c: RENAME[c] for c in raw.columns if c in RENAME})[list(RENAME.values())].copy()
    df["pickup_ts"] = pd.to_datetime(df["pickup_ts"])
    df["dropoff_ts"] = pd.to_datetime(df["dropoff_ts"])
    for col in ["vendor_id", "pu_zone_id", "do_zone_id", "payment_type_id"]:
        df[col] = df[col].astype("Int64")
    for col in ["passenger_count", "rate_code_id"]:
        df[col] = df[col].astype("Int64")
    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df["duration_min"] = (df["dropoff_ts"] - df["pickup_ts"]).dt.total_seconds() / 60
    hours = df["duration_min"] / 60
    df["avg_speed_mph"] = np.where(hours > 0, df["trip_distance"] / hours.where(hours > 0), np.nan)
    df["tip_pct"] = np.where(df["fare_amount"] > 0, 100 * df["tip_amount"] / df["fare_amount"].where(df["fare_amount"] > 0), np.nan)
    df["pickup_date_key"] = df["pickup_ts"].dt.strftime("%Y%m%d").astype("Int64")
    df["pickup_hour"] = df["pickup_ts"].dt.hour
    df["time_of_day"] = pd.cut(df["pickup_hour"], bins=[-1, 5, 11, 16, 20, 23],
                               labels=["night", "morning", "afternoon", "evening", "late_evening"]).astype(str)
    return df


def rejection_reasons(df: pd.DataFrame, month: str, rules: dict) -> pd.Series:
    """Return the first rule each row violates (None = valid). Order defines priority."""
    start = pd.Timestamp(f"{month}-01")
    end = start + pd.offsets.MonthBegin(1)
    checks = [
        ("missing_required_field", df[REQUIRED].isna().any(axis=1)),
        ("pickup_outside_month", (df["pickup_ts"] < start) | (df["pickup_ts"] >= end)),
        ("non_positive_duration", df["duration_min"] <= 0),
        ("duration_too_long", df["duration_min"] > rules["max_trip_hours"] * 60),
        ("non_positive_distance", df["trip_distance"] <= 0),
        ("distance_too_long", df["trip_distance"] > rules["max_distance_miles"]),
        ("non_positive_fare", df["fare_amount"] <= 0),
        ("fare_too_high", df["fare_amount"] > rules["max_fare_usd"]),
        ("negative_amount", df[["tip_amount", "tolls_amount", "total_amount"]].lt(0).any(axis=1)),
        ("implausible_speed", df["avg_speed_mph"] > 80),
        ("too_many_passengers", df["passenger_count"].fillna(0) > rules["max_passengers"]),
    ]
    conditions = [c.fillna(False).to_numpy(dtype=bool) for _, c in checks]
    reason = np.select(conditions, [name for name, _ in checks], default="")
    return pd.Series(reason, index=df.index).replace("", None)


def transform(raw: pd.DataFrame, month: str, rules: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (clean, rejected). Rejected rows keep their columns plus a `reason`."""
    df = add_features(standardise(raw))
    dup = df.duplicated(keep="first")
    df["reason"] = rejection_reasons(df, month, rules)
    df.loc[dup & df["reason"].isna(), "reason"] = "duplicate"
    df["source_month"] = month
    rejected = df[df["reason"].notna()].copy()
    clean = df[df["reason"].isna()].drop(columns="reason").reset_index(drop=True)
    clean.insert(0, "trip_id", int(month.replace("-", "")) * 10**8 + clean.index.to_numpy())
    return clean, rejected
