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


@asset
def hdb_raw(context: AssetExecutionContext) -> None:
    import hdb_resale_etl

    df = hdb_resale_etl.run_etl()
    context.add_output_metadata({"rows": len(df), "path": str(hdb_resale_etl.TRANSFORMED_PATH)})


@asset(deps=[hdb_raw])
def mapping_raw(context: AssetExecutionContext) -> None:
    import mapping_etl

    summary = mapping_etl.run_etl()
    context.add_output_metadata(summary)


pipeline_job = define_asset_job("resale_pipeline", selection="*")

daily_schedule = ScheduleDefinition(
    job=pipeline_job,
    cron_schedule="0 2 * * *",
    default_status=DefaultScheduleStatus.STOPPED,
)

defs = Definitions(
    assets=[hdb_raw, mapping_raw],
    jobs=[pipeline_job],
    schedules=[daily_schedule],
)
