import time
from pathlib import Path
import requests
import pandas as pd

DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
DATA_DIR = Path(__file__).parent / "data"
RAW_PATH = DATA_DIR / "hdb_downloaded.parquet"
TRANSFORMED_PATH = DATA_DIR / "hdbresale_transactions_transformed.parquet"

API_BASE = "https://api-open.data.gov.sg/v1/public/api/datasets"
STR_COLS = ["town", "flat_type", "block", "street_name", "storey_range", "flat_model"]
INT_COLS = ["floor_area_sqm", "lease_commence_date", "resale_price"]
SQM_TO_SQFT = 10.764


def download_file(dataset_id: str = DATASET_ID, max_polls: int = 5, poll_interval: float = 3.0) -> pd.DataFrame:
    s = requests.Session()
    init = s.get(f"{API_BASE}/{dataset_id}/initiate-download", json={})
    init.raise_for_status()
    print(init.json()["data"]["message"])

    for i in range(max_polls):
        poll = s.get(f"{API_BASE}/{dataset_id}/poll-download", json={})
        poll.raise_for_status()
        data = poll.json()["data"]
        if "url" in data:
            print(f"Download ready (poll {i+1}/{max_polls})")
            return pd.read_csv(data["url"])
        print(f"{i+1}/{max_polls}: not ready, status={data.get('status')}")
        time.sleep(poll_interval)
    raise RuntimeError(f"No download URL after {max_polls} polls")


def transform_data(df: pd.DataFrame) -> pd.DataFrame:
    t = df.copy()
    t.columns = t.columns.str.strip().str.lower().str.replace(" ", "_")

    for col in INT_COLS:
        t[col] = pd.to_numeric(t[col], errors="coerce").fillna(0).astype("int64")
    for col in STR_COLS:
        t[col] = t[col].astype("string")
    t["flat_model"] = t["flat_model"].str.upper()

    t["date"] = pd.to_datetime(t["month"], format="%Y-%m", errors="coerce")
    t["year"] = t["date"].dt.year.astype("int64")
    t["mth"] = t["date"].dt.month.astype("int64")

    t["floor_area_sqft"] = t["floor_area_sqm"] * SQM_TO_SQFT
    t["priceper_sqm"] = t["resale_price"] / t["floor_area_sqm"]
    t["priceper_sqft"] = t["resale_price"] / t["floor_area_sqft"]

    lease = t["remaining_lease"].astype("string").str.extract(
        r"(?P<years>\d+)\s*years?(?:\s*(?P<months>\d+)\s*months?)?"
    )
    years = pd.to_numeric(lease["years"], errors="coerce").fillna(0)
    months = pd.to_numeric(lease["months"], errors="coerce").fillna(0)
    t["remaining_lease_years"] = years + months / 12

    return t.sort_values("date").reset_index(drop=True)


def load(df: pd.DataFrame, raw: pd.DataFrame, raw_path: Path = RAW_PATH, transformed_path: Path = TRANSFORMED_PATH) -> None:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    transformed_path.parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(raw_path, index=False)
    df.to_parquet(transformed_path, index=False)


def run_etl() -> pd.DataFrame:
    raw = download_file()
    df = transform_data(raw)
    load(df, raw)
    return df


if __name__ == "__main__":
    run_etl()
