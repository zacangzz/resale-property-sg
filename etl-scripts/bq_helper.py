import logging
import os
from pathlib import Path
from google.cloud import bigquery
from google.oauth2 import service_account


def get_logger(name: str) -> logging.Logger:
    """Creates a configured logger that outputs both to console and a local 'logs/etl.log' file."""
    repo_root = Path(__file__).parent.parent
    log_dir = repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers if the logger is retrieved multiple times
    if not logger.handlers:
        # File handler (utf-8 to support any special characters)
        file_handler = logging.FileHandler(log_dir / "etl.log", encoding="utf-8")
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Stream handler (console output)
        stream_handler = logging.StreamHandler()
        stream_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        stream_handler.setFormatter(stream_formatter)
        logger.addHandler(stream_handler)

    return logger


logger = get_logger("bq_helper")


def get_bq_client(repo_root: Path) -> bigquery.Client:
    """Initializes and returns a Google BigQuery client.

    Uses GOOGLE_APPLICATION_CREDENTIALS service account credentials if specified
    in the environment variables (resolving relative paths relative to repo_root),
    otherwise defaults to standard client discovery.
    """
    project_id = os.getenv("GCP_PROJECT", "resale-property-sg")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if creds_path:
        creds_file = Path(creds_path)
        if not creds_file.is_absolute():
            creds_file = repo_root / creds_file

        if creds_file.exists():
            logger.info(f"Initializing BigQuery client with credentials: {creds_file}")
            credentials = service_account.Credentials.from_service_account_file(
                str(creds_file)
            )
            return bigquery.Client(credentials=credentials, project=project_id)
        else:
            logger.warning(f"Credentials file {creds_file} not found. Falling back to default auth.")

    logger.info(f"Initializing BigQuery client for project: {project_id} using default auth.")
    return bigquery.Client(project=project_id)


def load_parquet_to_bq(
    client: bigquery.Client,
    file_path: Path,
    dataset_id: str,
    table_name: str,
    location: str = "US",
) -> int:
    """Loads a local Parquet file into a BigQuery table, creating the dataset if needed.

    Returns the number of rows loaded.
    """
    if not file_path.exists():
        err_msg = f"Parquet file not found at: {file_path}"
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)

    # Construct the full dataset reference and create it if it doesn't exist
    dataset_ref = bigquery.Dataset(f"{client.project}.{dataset_id}")
    dataset_ref.location = location

    logger.info(f"Ensuring dataset '{dataset_id}' exists in location '{location}'...")
    try:
        client.create_dataset(dataset_ref, exists_ok=True)
    except Exception as e:
        logger.exception(f"Failed to ensure dataset '{dataset_id}' exists: {e}")
        raise

    # Configure the load job to truncate/overwrite existing data
    table_ref = dataset_ref.table(table_name)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    logger.info(f"Loading '{file_path.name}' into '{client.project}.{dataset_id}.{table_name}'...")
    try:
        with open(file_path, "rb") as source_file:
            job = client.load_table_from_file(
                source_file,
                table_ref,
                job_config=job_config,
            )
        # Wait for the load job to complete
        job.result()
        logger.info("BigQuery load job completed successfully.")
    except Exception as e:
        logger.exception(f"Failed to load parquet file to BigQuery: {e}")
        raise

    # Fetch and return the total row count in the loaded table
    try:
        table = client.get_table(table_ref)
        logger.info(f"Successfully verified table in BigQuery. Total rows: {table.num_rows}")
        return table.num_rows
    except Exception as e:
        logger.exception(f"Failed to fetch loaded table metadata: {e}")
        raise

