import unittest


from orchestration.definitions import defs


class OrchestrationDefinitionsTest(unittest.TestCase):
    def test_dagster_definitions_only_register_local_etl_assets(self) -> None:
        asset_keys = {key.to_user_string() for key in defs.resolve_asset_graph().get_all_asset_keys()}

        self.assertEqual(asset_keys, {"hdb_raw", "mapping_raw"})

    def test_dagster_job_is_local_resale_pipeline(self) -> None:
        self.assertEqual(defs.resolve_job_def("resale_pipeline").name, "resale_pipeline")


if __name__ == "__main__":
    unittest.main()
