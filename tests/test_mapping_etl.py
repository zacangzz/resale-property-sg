import importlib.util
import sys
from pathlib import Path

import pandas as pd


def load_mapping_etl():
    module_path = Path(__file__).resolve().parents[1] / "etl-scripts" / "mapping_etl.py"
    spec = importlib.util.spec_from_file_location("mapping_etl", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["mapping_etl"] = module
    spec.loader.exec_module(module)
    return module


def test_hdb_addresses_returns_sorted_unique_block_street_values(tmp_path):
    mapping_etl = load_mapping_etl()
    hdb_path = tmp_path / "hdb.parquet"
    pd.DataFrame(
        {
            "block": ["406", " 1 ", "406", "10"],
            "street_name": [
                "ANG MO KIO AVE 10",
                "BEACH RD ",
                "ANG MO KIO AVE 10",
                "TOH GUAN RD",
            ],
        }
    ).to_parquet(hdb_path, index=False)

    assert mapping_etl.hdb_addresses(hdb_path) == [
        "1 BEACH RD",
        "10 TOH GUAN RD",
        "406 ANG MO KIO AVE 10",
    ]


def test_merge_geocodes_keeps_one_row_per_address_and_prefers_newer_records():
    mapping_etl = load_mapping_etl()
    existing = pd.DataFrame(
        [
            {"address": "406 ANG MO KIO AVE 10", "postal": "560406"},
            {"address": "1 BEACH RD", "postal": "190001"},
        ]
    ).reindex(columns=mapping_etl.GEOCODE_COLS)

    merged = mapping_etl._merge_geocodes(
        existing,
        [
            {"address": "406 ANG MO KIO AVE 10", "postal": "560999"},
            {"address": "10 TOH GUAN RD", "postal": "600010"},
        ],
    )

    assert merged["address"].tolist() == [
        "1 BEACH RD",
        "406 ANG MO KIO AVE 10",
        "10 TOH GUAN RD",
    ]
    assert (
        merged.loc[merged["address"] == "406 ANG MO KIO AVE 10", "postal"].item()
        == "560999"
    )


def test_merge_geocodes_deduplicates_existing_cache_when_no_new_records():
    mapping_etl = load_mapping_etl()
    existing = pd.DataFrame(
        [
            {"address": "406 ANG MO KIO AVE 10", "postal": "560406"},
            {"address": "406 ANG MO KIO AVE 10", "postal": "560999"},
        ]
    ).reindex(columns=mapping_etl.GEOCODE_COLS)

    merged = mapping_etl._merge_geocodes(existing, [])

    assert merged["address"].tolist() == ["406 ANG MO KIO AVE 10"]
    assert merged["postal"].tolist() == ["560999"]


def test_geocode_addresses_creates_parent_directory_before_flush(tmp_path, monkeypatch):
    mapping_etl = load_mapping_etl()
    out_path = tmp_path / "nested" / "onemap_address_geocodes.parquet"

    def fake_geocode_one(address, token):
        return {"address": address, "postal": f"postal-{address}"}

    monkeypatch.setattr(mapping_etl, "_geocode_one", fake_geocode_one)

    result = mapping_etl.geocode_addresses(
        "token",
        ["1 BEACH RD", "406 ANG MO KIO AVE 10"],
        out_path=out_path,
        flush_every=1,
    )

    assert out_path.exists()
    assert result["address"].tolist() == ["1 BEACH RD", "406 ANG MO KIO AVE 10"]


def test_run_etl_only_writes_geocode_table_and_returns_geocode_metadata(monkeypatch, tmp_path):
    mapping_etl = load_mapping_etl()
    out_path = tmp_path / "onemap_address_geocodes.parquet"
    geocodes = pd.DataFrame(
        [{"address": "406 ANG MO KIO AVE 10", "postal": "560406"}]
    ).reindex(columns=mapping_etl.GEOCODE_COLS)

    monkeypatch.setattr(mapping_etl, "GEOCODES_PARQUET", out_path)
    monkeypatch.setattr(mapping_etl, "get_token", lambda: "token")
    monkeypatch.setattr(mapping_etl, "hdb_addresses", lambda: ["406 ANG MO KIO AVE 10"])
    monkeypatch.setattr(
        mapping_etl,
        "geocode_addresses",
        lambda token, addresses, out_path=out_path: geocodes,
    )

    for name in (
        "fetch_planning_areas",
        "fetch_planning_area_names",
        "to_feature_collection",
        "to_polygons_frame",
        "load",
    ):
        assert not hasattr(mapping_etl, name)

    assert mapping_etl.run_etl() == {
        "geocodes": 1,
        "path": str(out_path),
    }
