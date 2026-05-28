import os
import sys
from pathlib import Path
import dotenv

# Load environment variables
REPO_ROOT = Path(__file__).parent.parent
dotenv.load_dotenv(REPO_ROOT / ".env")

# Ensure etl-scripts is in the system path
sys.path.insert(0, str(REPO_ROOT / "etl-scripts"))
from bq_helper import get_bq_client, load_parquet_to_bq, get_logger

logger = get_logger("load_to_bq")


def main():
    logger.info("Starting standalone BigQuery load operation...")

    # Define paths to the local parquet files
    data_dir = REPO_ROOT / "data"
    hdb_parquet = data_dir / "hdbresale_transactions_transformed.parquet"
    mapping_parquet = data_dir / "onemap_address_geocodes.parquet"

    # Set up client and parameters
    client = get_bq_client(REPO_ROOT)
    dataset_id = "resale_datasets"
    location = os.getenv("BQ_LOCATION", "US")

    # 1. Load HDB Resale data
    if hdb_parquet.exists():
        try:
            logger.info(f"Found transformed HDB resale data at: {hdb_parquet}")
            load_parquet_to_bq(
                client=client,
                file_path=hdb_parquet,
                dataset_id=dataset_id,
                table_name="resale_hdb",
                location=location,
            )
        except Exception as e:
            logger.error(f"Failed to load HDB resale data: {e}")
    else:
        logger.warning(f"HDB resale parquet file not found at: {hdb_parquet}. Please run hdb_resale_etl.py first.")

    # 2. Load OneMap Coordinates
    if mapping_parquet.exists():
        try:
            logger.info(f"Found OneMap address geocodes at: {mapping_parquet}")
            load_parquet_to_bq(
                client=client,
                file_path=mapping_parquet,
                dataset_id=dataset_id,
                table_name="onemap_coord",
                location=location,
            )
        except Exception as e:
            logger.error(f"Failed to load OneMap coordinates: {e}")
    else:
        logger.warning(f"OneMap coordinates parquet file not found at: {mapping_parquet}. Please run mapping_etl.py first.")

    logger.info("Standalone load operation finished.")


if __name__ == "__main__":
    main()
