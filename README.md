# Resale Property SG

Local ETL and orchestration for Singapore HDB resale transaction data.

The project downloads HDB resale records from data.gov.sg, transforms them into
analysis-friendly parquet files, then geocodes unique HDB block/street addresses
with OneMap. Dagster is used only to orchestrate these local scripts.

## Project Layout

```text
resale-property-sg/
  etl-scripts/
    hdb_resale_etl.py   # HDB resale download and transformation
    mapping_etl.py      # OneMap address geocoding
  orchestration/
    definitions.py      # Dagster assets, job, and schedule
  data/
    *.parquet           # Local generated datasets
  tests/
```

## Setup

This project uses `uv`.

```bash
uv sync
```

For OneMap geocoding, create a local `.env` file with:

```bash
ONEMAPSG_EMAIL=your-email
ONEMAPSG_PW=your-password
```

The HDB resale ETL does not require credentials.

## ETL Scripts

### HDB Resale ETL

Implemented in [`etl-scripts/hdb_resale_etl.py`](etl-scripts/hdb_resale_etl.py).

It downloads the public data.gov.sg HDB resale dataset, standardises columns,
parses transaction dates, converts numeric/text fields, derives floor-area and
price-per-area metrics, parses remaining lease years, and writes:

- `data/hdb_downloaded.parquet`
- `data/hdbresale_transactions_transformed.parquet`

Run it directly with:

```bash
uv run python etl-scripts/hdb_resale_etl.py
```

Source dataset:

- Dataset ID: `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`
- API base URL: `https://api-open.data.gov.sg/v1/public/api/datasets`

### Mapping ETL

Implemented in [`etl-scripts/mapping_etl.py`](etl-scripts/mapping_etl.py).

It reads `data/hdbresale_transactions_transformed.parquet`, builds the unique
block/street address list, geocodes missing addresses through OneMap, reuses any
existing geocode cache, and writes:

- `data/onemap_address_geocodes.parquet`

Run it directly after the HDB ETL:

```bash
uv run python etl-scripts/mapping_etl.py
```

## Dagster Orchestration

Dagster definitions live in
[`orchestration/definitions.py`](orchestration/definitions.py).

Registered assets:

- `hdb_raw`: runs `hdb_resale_etl.run_etl()`
- `mapping_raw`: runs `mapping_etl.run_etl()` after `hdb_raw`

The `mapping_raw` asset explicitly depends on `hdb_raw`, because the mapping ETL
reads the transformed HDB parquet output.

Run the local Dagster UI with:

```bash
uv run dagster dev -m orchestration.definitions
```

The configured job is `resale_pipeline`. The optional daily schedule is stopped
by default.

## Tests

Run the full test suite with:

```bash
uv run pytest
```

Run the focused Dagster definition tests with:

```bash
uv run python -m unittest tests/test_orchestration_definitions.py -v
```

