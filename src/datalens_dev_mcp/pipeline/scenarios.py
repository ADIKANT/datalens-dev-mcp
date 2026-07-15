from __future__ import annotations

SCENARIOS = {
    "new_dashboard": "Create a new dashboard from requirements and data evidence.",
    "redesign_existing": "Hydrate current state, preserve baselines, redesign governed widgets.",
    "enhance_existing": "Add or repair widgets/selectors against a fresh readback baseline.",
    "wizard_to_js": "Classify Wizard widgets, keep maps native, convert supported non-map widgets to JS routes.",
}


def normalize_scenario(value: str | None) -> str:
    scenario = (value or "new_dashboard").strip()
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {sorted(SCENARIOS)}")
    return scenario
