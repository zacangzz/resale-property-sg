import os
import sys
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    Definitions,
    DefaultScheduleStatus,
    ScheduleDefinition,
    asset,
    define_asset_job,
)
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent
ETL_SCRIPTS = REPO_ROOT / "etl-scripts"

load_dotenv(REPO_ROOT / ".env")

if str(ETL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ETL_SCRIPTS))

# Initialize orchestration logger
from bq_helper import get_logger
logger = get_logger("orchestration")


@asset
def hdb_raw(context: AssetExecutionContext) -> None:
    import hdb_resale_etl

    logger.info("Executing hdb_raw asset (HDB Resale ETL download & transform)...")
    df = hdb_resale_etl.run_etl()
    context.add_output_metadata({"rows": len(df), "path": str(hdb_resale_etl.TRANSFORMED_PATH)})
    logger.info(f"Finished hdb_raw asset successfully. Transformed rows: {len(df)}")


@asset(deps=[hdb_raw])
def mapping_raw(context: AssetExecutionContext) -> None:
    import mapping_etl

    logger.info("Executing mapping_raw asset (OneMap geocoding)...")
    summary = mapping_etl.run_etl()
    context.add_output_metadata(summary)
    logger.info(f"Finished mapping_raw asset successfully. Summary: {summary}")


@asset(deps=[hdb_raw])
def hdb_bq_load(context: AssetExecutionContext) -> None:
    import hdb_resale_etl
    from bq_helper import get_bq_client, load_parquet_to_bq

    logger.info("Executing hdb_bq_load asset (Loading HDB to BigQuery)...")
    client = get_bq_client(REPO_ROOT)
    num_rows = load_parquet_to_bq(
        client=client,
        file_path=hdb_resale_etl.TRANSFORMED_PATH,
        dataset_id="resale_datasets",
        table_name="resale_hdb",
        location=os.getenv("BQ_LOCATION", "US"),
    )
    context.add_output_metadata({
        "dataset": "resale_datasets",
        "table": "resale_hdb",
        "rows_loaded": num_rows,
    })
    logger.info("Finished hdb_bq_load asset successfully.")


@asset(deps=[mapping_raw])
def mapping_bq_load(context: AssetExecutionContext) -> None:
    import mapping_etl
    from bq_helper import get_bq_client, load_parquet_to_bq

    logger.info("Executing mapping_bq_load asset (Loading OneMap coordinates to BigQuery)...")
    client = get_bq_client(REPO_ROOT)
    num_rows = load_parquet_to_bq(
        client=client,
        file_path=mapping_etl.GEOCODES_PARQUET,
        dataset_id="resale_datasets",
        table_name="onemap_coord",
        location=os.getenv("BQ_LOCATION", "US"),
    )
    context.add_output_metadata({
        "dataset": "resale_datasets",
        "table": "onemap_coord",
        "rows_loaded": num_rows,
    })
    logger.info("Finished mapping_bq_load asset successfully.")


pipeline_job = define_asset_job("resale_pipeline", selection="*")

daily_schedule = ScheduleDefinition(
    job=pipeline_job,
    cron_schedule="0 2 * * *",
    default_status=DefaultScheduleStatus.STOPPED,
)

defs = Definitions(
    assets=[hdb_raw, mapping_raw, hdb_bq_load, mapping_bq_load],
    jobs=[pipeline_job],
    schedules=[daily_schedule],
)
