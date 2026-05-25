from pathlib import Path
import duckdb
import pandas as pd
import plotly.express as px

TRANSFORMED_PATH = Path(__file__).parent / "data" / "hdbresale_transactions_transformed.parquet"


def load_transactions(path: Path = TRANSFORMED_PATH) -> pd.DataFrame:
    return pd.read_parquet(path)


def count_4room_by_town_lease(r: pd.DataFrame) -> pd.DataFrame:
    query = """
    SELECT town, lease_commence_date, COUNT(*) AS count
    FROM r
    WHERE flat_type IN ('4 ROOM')
      AND lease_commence_date > 1967 AND floor_area_sqm < 90
    GROUP BY town, lease_commence_date
    ORDER BY lease_commence_date
    """
    return duckdb.query(query).df()


def distinct_4room_towns(r: pd.DataFrame) -> pd.DataFrame:
    query = """
    SELECT DISTINCT town
    FROM r
    WHERE flat_type IN ('4 ROOM')
      AND lease_commence_date > 1967 AND floor_area_sqm < 90
    ORDER BY town
    """
    return duckdb.query(query).df()


def agg_4room_monthly(r: pd.DataFrame, years: list[int] | None = None) -> pd.DataFrame:
    if years is None:
        years = [2024, 2025]
    flat = ["4 ROOM"]
    base_query = " flat_type in @flat & year in @years "
    return (
        r.query(f"{base_query} & lease_commence_date > 1977", engine="python")
        .groupby(["month"])
        .agg(
            _count=("flat_model", "size"),
            _mean_resaleprice=("resale_price", "mean"),
            _min_resaleprice=("resale_price", "min"),
            _max_resaleprice=("resale_price", "max"),
            _minprice_sqft=("priceper_sqft", "min"),
            _meanprice_sqft=("priceper_sqft", "mean"),
            _medianprice_sqft=("priceper_sqft", "median"),
            _maxprice_sqft=("priceper_sqft", "max"),
            _minsqft=("floor_area_sqft", "min"),
            _maxsqft=("floor_area_sqft", "max"),
        )
        .sort_values(by="_mean_resaleprice")
    )


def plot_resale_range(g: pd.DataFrame):
    fig = px.bar(
        g,
        y=["_min_resaleprice", "_max_resaleprice"],
        text_auto=True,
        title="mean resale price: hdb resale from 2024 to date",
    )
    fig.update_layout(barmode="group")
    return fig


if __name__ == "__main__":
    r = load_transactions()
    print(count_4room_by_town_lease(r))
    print(distinct_4room_towns(r))
    g = agg_4room_monthly(r)
    print(g)
    plot_resale_range(g).show()
