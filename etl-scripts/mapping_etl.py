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

# Validate GCS utilization
is_gcs = isinstance(DATA_DIR, str) and DATA_DIR.startswith("gs://")
logger.info(f"Active DATA_DIR: {DATA_DIR} (GCS: {is_gcs})")

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
    response = requests.post(url, headers=headers, json=params, timeout=30)
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
    response = requests.get(url, headers=headers, params=params, timeout=30)
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
    flush_every: int = 100, # Flush more frequently to save progress incrementally
) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import gc

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

    if not pending:
        logger.info("No new addresses to geocode.")
        return existing

    # Parallel execution with ThreadPoolExecutor (safe max_workers to respect rate limits)
    max_workers = 5

    for chunk_start in range(0, len(pending), flush_every):
        chunk = pending[chunk_start:chunk_start + flush_every]
        logger.info(f"Processing chunk {chunk_start // flush_every + 1}: geocoding {len(chunk)} addresses...")

        records = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_addr = {executor.submit(_geocode_one, addr, token): addr for addr in chunk}
            for future in as_completed(future_to_addr):
                addr = future_to_addr[future]
                try:
                    res = future.result()
                    records.append(res)
                except Exception as e:
                    logger.error(f"Error geocoding {addr}: {e}")
                    records.append({"address": addr})

        # Merge chunk records with existing and immediately flush to GCS
        existing = _merge_geocodes(existing, records)
        existing.to_parquet(str(out_path), index=False)
        logger.info(f"  Flushed progress up to address {chunk_start + len(chunk)}/{len(pending)} to GCS.")

        # Clean up chunk records memory
        del records
        gc.collect()

    return existing


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
