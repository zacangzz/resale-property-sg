import os
from pathlib import Path

import requests
import pandas as pd
from dotenv import load_dotenv
from bq_helper import get_logger

logger = get_logger("mapping_etl")

load_dotenv()

DATA_DIR_ENV = os.getenv("DATA_DIR")
if DATA_DIR_ENV:
    DATA_DIR = DATA_DIR_ENV
else:
    DATA_DIR = Path(__file__).parent.parent / "data"

def get_path(filename: str) -> str:
    if isinstance(DATA_DIR, str) and DATA_DIR.startswith("gs://"):
        return f"{DATA_DIR.rstrip('/')}/{filename}"
    return str(Path(DATA_DIR) / filename)

HDB_TRANSFORMED_PATH = get_path("hdbresale_transactions_transformed.parquet")
GEOCODES_PARQUET = get_path("onemap_address_geocodes.parquet")

GEOCODE_COLS = [
    "address", "searchval", "blk_no", "road_name", "building",
    "full_address", "postal", "x", "y", "latitude", "longitude",
]

ONEMAP_BASE = "https://www.onemap.gov.sg/api"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246"
)


def get_token() -> str:
    url = f"{ONEMAP_BASE}/auth/post/getToken"
    params = {
        "email": os.getenv("ONEMAPSG_EMAIL"),
        "password": os.getenv("ONEMAPSG_PW"),
    }
    headers = {"User-Agent": USER_AGENT}
    response = requests.post(url, headers=headers, json=params)
    response.raise_for_status()
    return response.json()["access_token"]


def get_latlong(address: str, token: str) -> pd.DataFrame:
    url = f"{ONEMAP_BASE}/common/elastic/search"
    headers = {"Authorization": token, "User-Agent": USER_AGENT}
    params = {
        "searchVal": address,
        "returnGeom": "Y",
        "getAddrDetails": "Y",
        "pageNum": 1,
    }
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return pd.DataFrame(response.json()["results"])


def hdb_addresses(hdb_path = HDB_TRANSFORMED_PATH) -> list[str]:
    df = pd.read_parquet(str(hdb_path), columns=["block", "street_name"])
    addr = (df["block"].astype("string").str.strip() + " "
            + df["street_name"].astype("string").str.strip())
    return sorted(a for a in addr.dropna().unique() if a.strip())


def _geocode_one(address: str, token: str) -> dict:
    try:
        res = get_latlong(address, token)
    except requests.RequestException:
        return {"address": address}
    if res.empty:
        return {"address": address}
    top = res.iloc[0]
    return {
        "address": address,
        "searchval": top.get("SEARCHVAL"),
        "blk_no": top.get("BLK_NO"),
        "road_name": top.get("ROAD_NAME"),
        "building": top.get("BUILDING"),
        "full_address": top.get("ADDRESS"),
        "postal": top.get("POSTAL"),
        "x": top.get("X"),
        "y": top.get("Y"),
        "latitude": top.get("LATITUDE"),
        "longitude": top.get("LONGITUDE"),
    }


def geocode_addresses(
    token: str,
    addresses: list[str],
    out_path = GEOCODES_PARQUET,
    flush_every: int = 500,
) -> pd.DataFrame:
    is_gcs = str(out_path).startswith("gs://")
    if not is_gcs:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    existing = None
    if is_gcs:
        try:
            existing = pd.read_parquet(str(out_path))
            logger.info(f"Loaded {len(existing)} existing geocodes from GCS cache.")
        except Exception:
            logger.info("No existing geocodes found in GCS cache. Starting fresh.")
    else:
        if Path(out_path).exists():
            existing = pd.read_parquet(str(out_path))
            logger.info(f"Loaded {len(existing)} existing geocodes from local cache.")

    if existing is None or existing.empty:
        existing = pd.DataFrame(columns=GEOCODE_COLS)

    done = set(existing["address"]) if not existing.empty else set()

    pending = [a for a in addresses if a not in done]
    logger.info(f"Geocoding {len(pending)} new addresses ({len(done)} cached)")

    records = []
    for i, address in enumerate(pending, 1):
        records.append(_geocode_one(address, token))
        if i % flush_every == 0:
            existing = _merge_geocodes(existing, records)
            existing.to_parquet(str(out_path), index=False)
            records = []
            logger.info(f"  flushed {i}/{len(pending)}")

    result = _merge_geocodes(existing, records)
    result.to_parquet(str(out_path), index=False)
    return result


def _merge_geocodes(existing: pd.DataFrame, new_records: list[dict]) -> pd.DataFrame:
    existing = existing.reindex(columns=GEOCODE_COLS)
    if new_records:
        new = pd.DataFrame(new_records).reindex(columns=GEOCODE_COLS)
        combined = pd.concat([existing, new], ignore_index=True)
    else:
        combined = existing
    return combined.drop_duplicates(subset="address", keep="last").reset_index(drop=True)


def run_etl() -> dict:
    token = get_token()
    geocodes = geocode_addresses(token, hdb_addresses(), out_path=GEOCODES_PARQUET)
    logger.info(f"Geocodes table: {len(geocodes)} addresses")

    return {
        "geocodes": len(geocodes),
        "path": str(GEOCODES_PARQUET),
    }


if __name__ == "__main__":
    run_etl()
