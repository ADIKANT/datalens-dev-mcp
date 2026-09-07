import json
import subprocess

import pytest

from datalens_dev_mcp.authoring.dataset_source import kpi_dataset_source


def bindings():
    return {"dataset_id": "synthetic", "date": {"field_guid": "date"},
            "metric": {"field_guid": "current"}, "comparison": {"field_guid": "previous"},
            "fields": [{"guid": g, "title": g} for g in ("date", "current", "previous")]}


def test_kpi_latest_is_chronological_and_preserves_missing_values():
    source = kpi_dataset_source({**bindings(), "value_mode": "last"})
    rows = [{"date": "2026-02-02", "current": None, "previous": 3},
            {"date": "2026-02-01", "current": 2, "previous": 1}]
    script = "const require=()=>({getDatasetRows:()=>" + json.dumps(rows) + "});\n"
    script += source["prepare_js"] + "\nconsole.log(JSON.stringify(module.exports));"
    result = json.loads(subprocess.check_output(["node", "-e", script], text=True))
    assert result["value"] is None
    assert result["previous"] == 3
    assert result["points"][0] == {"date": "2026-02-01", "value": 2}


def test_kpi_never_infers_sum_for_nonadditive_metric():
    with pytest.raises(ValueError, match="explicit value_mode"):
        kpi_dataset_source(bindings())
    with pytest.raises(ValueError, match="additive"):
        kpi_dataset_source({**bindings(), "value_mode": "sum"})
