import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path = ROOT / "config.yaml") -> dict:
    cfg = yaml.safe_load(path.read_text())
    for key in ("raw_dir", "warehouse_path"):
        cfg[key] = os.getenv(f"ETL_{key.upper()}", cfg[key])
        if not Path(cfg[key]).is_absolute():
            cfg[key] = str(ROOT / cfg[key])
    return cfg
