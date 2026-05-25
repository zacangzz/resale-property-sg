# Resale Property SG

This project downloads and transforms Singapore HDB resale transaction data from
data.gov.sg.

## ETL Overview

The ETL pipeline is implemented in [etl.py](etl.py). It performs three main
steps:

1. Download the source CSV from data.gov.sg.
2. Transform the raw resale transaction records into analysis-friendly columns.
3. Save both the raw and transformed datasets as parquet files under `data/`.

## Source Dataset

`etl.py` uses the data.gov.sg public dataset API:

- Dataset ID: `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`
- API base URL: `https://api-open.data.gov.sg/v1/public/api/datasets`

The download process starts an API download job, polls until a download URL is
available, then reads the CSV into a pandas DataFrame.

## Transformation Steps

The `transform_data()` function applies the following transformations.

### 1. Standardise Column Names

All input column names are normalised by:

- trimming leading and trailing whitespace
- converting names to lowercase
- replacing spaces with underscores

For example, `Flat Type` becomes `flat_type`.

### 2. Convert Numeric Columns

The following columns are converted to `int64`:

- `floor_area_sqm`
- `lease_commence_date`
- `resale_price`

Invalid or missing numeric values are coerced to `NaN`, filled with `0`, then
converted to integers.

### 3. Convert Text Columns

The following columns are converted to pandas `string` dtype:

- `town`
- `flat_type`
- `block`
- `street_name`
- `storey_range`
- `flat_model`

After conversion, `flat_model` is uppercased for consistent categorisation.

### 4. Parse Transaction Month

The `month` column is parsed using the `%Y-%m` format and stored as a new
datetime column:

- `date`

Two additional date parts are then derived:

- `year`: calendar year from `date`
- `mth`: calendar month from `date`

### 5. Derive Floor Area in Square Feet

Floor area is converted from square metres to square feet using:

```text
floor_area_sqft = floor_area_sqm * 10.764
```

The result is stored in:

- `floor_area_sqft`

### 6. Derive Unit Price Metrics

Two price-per-area metrics are calculated:

```text
priceper_sqm = resale_price / floor_area_sqm
priceper_sqft = resale_price / floor_area_sqft
```

These columns make it easier to compare resale prices across flats of different
sizes.

### 7. Convert Remaining Lease to Decimal Years

The `remaining_lease` text field is parsed for years and optional months.

Examples:

- `60 years` becomes `60.0`
- `60 years 6 months` becomes `60.5`

The derived value is stored in:

- `remaining_lease_years`

If years or months cannot be parsed, they are treated as `0`.

### 8. Sort Rows

The transformed dataset is sorted by `date` and the index is reset.

## Output Files

Running the ETL writes two parquet files:

- `data/hdb_downloaded.parquet`: raw downloaded data
- `data/hdbresale_transactions_transformed.parquet`: transformed data
