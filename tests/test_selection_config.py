from __future__ import annotations

import json

import pytest

from ds_tool.gui.selection_config import (
    SELECTION_VERSION,
    build_selection_payload,
    parse_selection_payload,
)


def test_build_payload_shape() -> None:
    payload = build_selection_payload(["Account", "CompSuite__Change_Control__c"], ["Admin"])
    assert payload == {
        "version": SELECTION_VERSION,
        "objects": ["Account", "CompSuite__Change_Control__c"],
        "profiles_permission_sets": ["Admin"],
    }


def test_round_trip_through_json() -> None:
    objects = ["Account", "Opportunity"]
    profiles = ["System Administrator", "DotCompliance_PermSet"]
    blob = json.dumps(build_selection_payload(objects, profiles))
    got_objs, got_profs = parse_selection_payload(json.loads(blob))
    assert got_objs == objects
    assert got_profs == profiles


def test_parse_tolerates_legacy_profiles_key() -> None:
    data = {"objects": ["Account"], "profiles": ["Admin"]}
    objs, profs = parse_selection_payload(data)
    assert objs == ["Account"]
    assert profs == ["Admin"]


def test_parse_handles_missing_keys() -> None:
    assert parse_selection_payload({}) == ([], [])
    assert parse_selection_payload({"objects": None, "profiles_permission_sets": None}) == ([], [])


def test_parse_coerces_to_str() -> None:
    objs, profs = parse_selection_payload({"objects": [1, 2], "profiles_permission_sets": [3]})
    assert objs == ["1", "2"]
    assert profs == ["3"]


def test_parse_rejects_non_object() -> None:
    with pytest.raises(ValueError):
        parse_selection_payload(["not", "a", "dict"])
