"""Extract: download raw files once and cache them locally (idempotent)."""
import logging
import time
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)


def download(url: str, dest: Path, retries: int = 3, backoff: float = 2.0) -> Path:
    """Download url to dest unless it is already cached. Retries with exponential backoff."""
    if dest.exists() and dest.stat().st_size > 0:
        log.info("cache hit %s", dest.name)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            tmp.rename(dest)  # atomic: a half-written file is never treated as cached
            log.info("downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
            return dest
        except requests.RequestException as e:
            log.warning("download failed (attempt %d/%d): %s", attempt, retries, e)
            if attempt == retries:
                raise
            time.sleep(backoff ** attempt)


def extract_trips(month: str, cfg: dict) -> pd.DataFrame:
    path = download(cfg["trip_url_template"].format(month=month),
                    Path(cfg["raw_dir"]) / f"yellow_tripdata_{month}.parquet", cfg["download_retries"])
    return pd.read_parquet(path)


def extract_zones(cfg: dict) -> pd.DataFrame:
    path = download(cfg["zone_url"], Path(cfg["raw_dir"]) / "taxi_zone_lookup.csv", cfg["download_retries"])
    # keep_default_na=False: the zone file uses the literal string "N/A" as a borough name
    return pd.read_csv(path, keep_default_na=False)
