import json

import pytest

from datalens_dev_mcp.authoring.profiles import get_authoring_defaults
from datalens_dev_mcp.authoring.recipes import compile_recipe


def test_explicit_user_wizard_default_is_not_silently_discarded_for_kpi(tmp_path):
    path = tmp_path / "authoring.json"
    path.write_text(json.dumps({"families": {"kpi_sparkline": {"technology": "wizard"}}}))
    with pytest.raises(ValueError, match="does not support technology"):
        compile_recipe("kpi_sparkline", {"metric": {}, "date": {}, "comparison": {}, "prepared_data": {}},
                       user_config_path=path)


def test_generic_wizard_preference_does_not_override_explicit_recipe_family(tmp_path):
    result = compile_recipe("kpi_sparkline", {"metric": {}, "date": {}, "comparison": {}, "prepared_data": {}},
                            user_config_path=tmp_path / "absent.json")
    assert result["draft"]["technology"] == "advanced_chart"


def test_technology_origin_tracks_actual_overrides(tmp_path):
    path = tmp_path / "authoring.json"
    path.write_text(json.dumps({"defaults": {"technology": "wizard"}}))
    defaults = get_authoring_defaults(user_config_path=path, explicit={"spacing": 20})
    assert defaults["technology_source"] == "user"
