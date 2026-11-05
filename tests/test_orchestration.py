"""The Dagster graph is runnable without the webserver."""

from dagster import materialize

from housing_radar.orchestration.definitions import contract_results, defs, tidy_tables


def test_asset_graph_lists_every_stage_and_materializes_the_contracts():
    names = sorted(asset.key.path[-1] for asset in defs.assets)
    assert names == ["contract_results", "dashboard_json", "dbt_marts", "tidy_tables"]
    result = materialize([tidy_tables, contract_results])
    assert result.success
