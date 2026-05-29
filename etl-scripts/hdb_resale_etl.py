import os
import time
from pathlib import Path
import requests
import pandas as pd
from bq_helper import get_logger

logger = get_logger("hdb_resale_etl")

DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"

DATA_DIR_ENV = os.getenv("DATA_DIR")
if DATA_DIR_ENV:
    DATA_DIR = DATA_DIR_ENV
else:
    DATA_DIR = Path(__file__).parent.parent / "data"

# Validate GCS utilization
is_gcs = isinstance(DATA_DIR, str) and DATA_DIR.startswith("gs://")
logger.info(f"Active DATA_DIR: {DATA_DIR} (GCS: {is_gcs})")

def get_path(filename: str) -> str:
    if isinstance(DATA_DIR, str) and DATA_DIR.startswith("gs://"):
        return f"{DATA_DIR.rstrip('/')}/{filename}"
    return str(Path(DATA_DIR) / filename)

RAW_PATH = get_path("hdb_downloaded.parquet")
TRANSFORMED_PATH = get_path("hdbresale_transactions_transformed.parquet")

API_BASE = "https://api-open.data.gov.sg/v1/public/api/datasets"
STR_COLS = ["town", "flat_type", "block", "street_name", "storey_range", "flat_model"]
INT_COLS = ["floor_area_sqm", "lease_commence_date", "resale_price"]
SQM_TO_SQFT = 10.764


def download_file(dataset_id: str = DATASET_ID, max_polls: int = 5, poll_interval: float = 3.0) -> pd.DataFrame:
    s = requests.Session()
    init = s.get(f"{API_BASE}/{dataset_id}/initiate-download", json={}, timeout=30)
    init.raise_for_status()
    logger.info(init.json()["data"]["message"])

    for i in range(max_polls):
        poll = s.get(f"{API_BASE}/{dataset_id}/poll-download", json={}, timeout=30)
        poll.raise_for_status()
        data = poll.json()["data"]
        if "url" in data:
            logger.info(f"Download ready (poll {i+1}/{max_polls})")
            # Memory optimization: specify compact dtypes and use pyarrow engine
            dtypes = {
                "town": "category",
                "flat_type": "category",
                "storey_range": "category",
                "flat_model": "category",
                "lease_commence_date": "int16",
                "resale_price": "int32",
                "floor_area_sqm": "float32",
            }
            return pd.read_csv(data["url"], dtype=dtypes, engine="pyarrow")
        logger.warning(f"{i+1}/{max_polls}: not ready, status={data.get('status')}")
        time.sleep(poll_interval)
    raise RuntimeError(f"No download URL after {max_polls} polls")


def transform_data(df: pd.DataFrame) -> pd.DataFrame:
    # Perform operations directly on the dataframe or reassign columns to avoid copying
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    for col in INT_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int32")
    for col in STR_COLS:
        df[col] = df[col].astype("category") # use category to save massive memory
    df["flat_model"] = df["flat_model"].str.upper().astype("category")

    df["date"] = pd.to_datetime(df["month"], format="%Y-%m", errors="coerce")
    df["year"] = df["date"].dt.year.astype("int16")
    df["mth"] = df["date"].dt.month.astype("int8")

    df["floor_area_sqft"] = (df["floor_area_sqm"] * SQM_TO_SQFT).astype("float32")
    df["priceper_sqm"] = (df["resale_price"] / df["floor_area_sqm"]).astype("float32")
    df["priceper_sqft"] = (df["resale_price"] / df["floor_area_sqft"]).astype("float32")

    lease = df["remaining_lease"].astype("string").str.extract(
        r"(?P<years>\d+)\s*years?(?:\s*(?P<months>\d+)\s*months?)?"
    )
    years = pd.to_numeric(lease["years"], errors="coerce").fillna(0).astype("int16")
    months = pd.to_numeric(lease["months"], errors="coerce").fillna(0).astype("int8")
    df["remaining_lease_years"] = (years + months / 12).astype("float32")

    return df.sort_values("date").reset_index(drop=True)


def load(df: pd.DataFrame, raw: pd.DataFrame, raw_path = RAW_PATH, transformed_path = TRANSFORMED_PATH) -> None:
    if not str(raw_path).startswith("gs://"):
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    if not str(transformed_path).startswith("gs://"):
        Path(transformed_path).parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(str(raw_path), index=False)
    df.to_parquet(str(transformed_path), index=False)


def run_etl() -> pd.DataFrame:
    import gc
    raw = download_file()
    
    # Save raw file immediately to GCS/local and clear raw memory
    logger.info("Saving raw data...")
    if not str(RAW_PATH).startswith("gs://"):
        Path(RAW_PATH).parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(str(RAW_PATH), index=False)
    
    logger.info("Transforming data...")
    df = transform_data(raw)
    
    # Save transformed data to GCS/local
    logger.info("Saving transformed data...")
    if not str(TRANSFORMED_PATH).startswith("gs://"):
        Path(TRANSFORMED_PATH).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(TRANSFORMED_PATH), index=False)
    
    # Clean up memory explicitly
    del raw
    gc.collect()
    
    return df


if __name__ == "__main__":
    run_etl()
