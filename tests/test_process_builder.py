from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import process_builder


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


def test_parse_criteria_empty_flow() -> None:
    assert process_builder._parse_criteria({}) is None


def test_parse_criteria_single_rule() -> None:
    raw = {
        "decisions": [
            {
                "rules": [
                    {
                        "label": "Check Status",
                        "connector": {"targetReference": "myRule_1"},
                        "conditions": [
                            {
                                "leftValueReference": "myVariable_current.Status__c",
                                "operator": "EqualTo",
                                "rightValue": {"stringValue": "Active"},
                            }
                        ],
                        "conditionLogic": "and",
                    }
                ]
            }
        ]
    }
    result = process_builder._parse_criteria(raw)
    assert result is not None
    assert "Check Status" in result
    assert "Status__c EqualTo String Active" in result
    assert "All of the conditions are met (AND)" in result


def test_parse_actions_empty_flow() -> None:
    assert process_builder._parse_actions({}) == []


def test_parse_actions_single_call() -> None:
    raw = {
        "actionCalls": [
            {"actionType": "emailAlert", "label": "Notify Owner"},
        ]
    }
    actions = process_builder._parse_actions(raw)
    assert len(actions) == 1
    assert "emailAlert" in actions[0]
    assert "Notify Owner" in actions[0]


# ---------------------------------------------------------------------------
# fetch() integration-style tests (mocked client)
# ---------------------------------------------------------------------------


def _object_type_meta(full_name, object_api_name, extra=None):
    """A Flow metadata payload that declares its ObjectType (how PB → object is matched)."""
    meta = {
        "fullName": full_name,
        "processMetadataValues": [
            {"name": "ObjectType", "value": {"stringValue": object_api_name}}
        ],
    }
    if extra:
        meta.update(extra)
    return meta


def _make_client(view_records, metadata_records=None):
    """fetch() calls client.query once (FlowDefinitionView) then read_metadata."""
    client = MagicMock()
    client.query = AsyncMock(return_value={"records": view_records})
    client.read_metadata = AsyncMock(return_value=metadata_records or [])
    return client


def test_fetch_parses_process_builder_spec() -> None:
    view_records = [
        {
            "ApiName": "Account_PB",
            "Label": "Account Process",
            "ProcessType": "Workflow",
            "IsActive": True,
            "Description": "Test PB",
        }
    ]
    metadata_records = [
        {
            "fullName": "Account_PB",
            "processMetadataValues": [
                {"name": "ObjectType", "value": {"stringValue": "Account"}}
            ],
            "decisions": [
                {
                    "rules": [
                        {
                            "label": "Is New",
                            "connector": {"targetReference": "myRule_1"},
                            "conditions": [
                                {
                                    "leftValueReference": "myVariable_current.Name",
                                    "operator": "NotEqualTo",
                                    "rightValue": {"stringValue": ""},
                                }
                            ],
                            "conditionLogic": "and",
                        }
                    ]
                }
            ],
            "actionCalls": [
                {"actionType": "emailAlert", "label": "Send Welcome"},
            ],
        }
    ]
    client = _make_client(view_records, metadata_records)
    specs = _run(process_builder.fetch(client, "Account"))

    assert len(specs) == 1
    pb = specs[0]
    assert pb.api_name == "Account_PB"
    assert pb.label == "Account Process"
    assert pb.status == "Active"
    assert pb.description == "Test PB"
    assert pb.trigger_object == "Account"
    assert pb.criteria is not None
    assert "Is New" in pb.criteria
    assert len(pb.actions) == 1
    assert "emailAlert" in pb.actions[0]
    assert "Send Welcome" in pb.actions[0]


def test_fetch_inactive_status() -> None:
    view_records = [
        {
            "ApiName": "Acct_Old_PB",
            "Label": "Old PB",
            "ProcessType": "InvocableProcess",
            "IsActive": False,
            "Description": None,
        }
    ]
    client = _make_client(view_records, [_object_type_meta("Acct_Old_PB", "Account")])
    specs = _run(process_builder.fetch(client, "Account"))
    assert len(specs) == 1
    assert specs[0].status == "Inactive"


def test_fetch_returns_empty_when_no_records() -> None:
    client = _make_client([])
    specs = _run(process_builder.fetch(client, "Account"))
    assert specs == []


def test_fetch_skips_builders_on_other_objects() -> None:
    # A Workflow PB exists, but its metadata ObjectType is a different object.
    view_records = [
        {"ApiName": "Other_PB", "Label": "Other", "ProcessType": "Workflow", "IsActive": True}
    ]
    client = _make_client(view_records, [_object_type_meta("Other_PB", "Contact")])
    specs = _run(process_builder.fetch(client, "Account"))
    assert specs == []


def test_fetch_returns_empty_on_query_error() -> None:
    client = MagicMock()
    client.query = AsyncMock(side_effect=RuntimeError("network error"))
    specs = _run(process_builder.fetch(client, "Account"))
    assert specs == []


def test_fetch_skips_when_object_unknown_on_metadata_failure() -> None:
    """If metadata can't be read, the object can't be confirmed → builder is skipped."""
    view_records = [
        {"ApiName": "Acct_PB", "Label": "Account PB", "ProcessType": "Workflow", "IsActive": True}
    ]
    client = MagicMock()
    client.query = AsyncMock(return_value={"records": view_records})
    client.read_metadata = AsyncMock(side_effect=RuntimeError("metadata unavailable"))
    specs = _run(process_builder.fetch(client, "Account"))
    assert specs == []


# ---------------------------------------------------------------------------
# _parse_actions – new action-source tests
# ---------------------------------------------------------------------------


def test_parse_actions_record_updates() -> None:
    """recordUpdates nodes must surface as 'Update Records: <label>'."""
    raw = {
        "recordUpdates": [
            {"label": "Set Status Active", "object": "Account"},
        ]
    }
    actions = process_builder._parse_actions(raw)
    assert len(actions) == 1
    assert "Update Records" in actions[0]
    assert "Set Status Active" in actions[0]


def test_parse_actions_record_creates() -> None:
    raw = {
        "recordCreates": [
            {"label": "Create Follow-up Task"},
        ]
    }
    actions = process_builder._parse_actions(raw)
    assert len(actions) == 1
    assert "Create Records" in actions[0]
    assert "Create Follow-up Task" in actions[0]


def test_parse_actions_record_deletes() -> None:
    raw = {
        "recordDeletes": [
            {"label": "Delete Old Records"},
        ]
    }
    actions = process_builder._parse_actions(raw)
    assert len(actions) == 1
    assert "Delete Records" in actions[0]
    assert "Delete Old Records" in actions[0]


def test_parse_actions_record_update_falls_back_to_object() -> None:
    """When a recordUpdates node has no label, fall back to the object field."""
    raw = {
        "recordUpdates": [
            {"object": "Contact"},
        ]
    }
    actions = process_builder._parse_actions(raw)
    assert len(actions) == 1
    assert "Update Records" in actions[0]
    assert "Contact" in actions[0]


def test_parse_actions_multiple_sources() -> None:
    """All sources are collected and returned together."""
    raw = {
        "actionCalls": [
            {"actionType": "emailAlert", "label": "Notify Owner"},
        ],
        "recordUpdates": [
            {"label": "Stamp Timestamp"},
        ],
        "recordCreates": [
            {"label": "Create Task"},
        ],
    }
    actions = process_builder._parse_actions(raw)
    assert len(actions) == 3
    labels = " | ".join(actions)
    assert "emailAlert" in labels
    assert "Notify Owner" in labels
    assert "Update Records" in labels
    assert "Stamp Timestamp" in labels
    assert "Create Records" in labels
    assert "Create Task" in labels


def test_parse_actions_scheduled_paths() -> None:
    """actionCalls nested inside decisions → scheduledPaths are surfaced."""
    raw = {
        "decisions": [
            {
                "scheduledPaths": [
                    {
                        "actionCalls": [
                            {"actionType": "chatterPost", "label": "Post After 3 Days"},
                        ]
                    }
                ]
            }
        ]
    }
    actions = process_builder._parse_actions(raw)
    assert len(actions) == 1
    assert "chatterPost" in actions[0]
    assert "Post After 3 Days" in actions[0]


def test_parse_actions_empty_gives_empty_list() -> None:
    """A payload with no action nodes at all must return an empty list."""
    raw: dict = {}
    assert process_builder._parse_actions(raw) == []


# ---------------------------------------------------------------------------
# fetch() – record-DML action surfaces through fetch()
# ---------------------------------------------------------------------------


def test_fetch_actions_from_record_updates() -> None:
    """End-to-end: a PB with only recordUpdates (no actionCalls) still has actions."""
    view_records = [
        {
            "ApiName": "Account_Update_PB",
            "Label": "Account Update PB",
            "ProcessType": "Workflow",
            "IsActive": True,
            "Description": None,
        }
    ]
    metadata_records = [
        {
            "fullName": "Account_Update_PB",
            "processMetadataValues": [
                {"name": "ObjectType", "value": {"stringValue": "Account"}}
            ],
            "recordUpdates": [
                {"label": "Set Rating High"},
                {"label": "Clear Old Field"},
            ],
        }
    ]
    client = _make_client(view_records, metadata_records)
    specs = _run(process_builder.fetch(client, "Account"))

    assert len(specs) == 1
    pb = specs[0]
    assert len(pb.actions) == 2
    action_text = " | ".join(pb.actions)
    assert "Update Records" in action_text
    assert "Set Rating High" in action_text
    assert "Clear Old Field" in action_text


def test_fetch_multiple_process_builders() -> None:
    view_records = [
        {
            "ApiName": "PB_One",
            "Label": "First PB",
            "ProcessType": "Workflow",
            "IsActive": True,
            "Description": None,
        },
        {
            "ApiName": "PB_Two",
            "Label": "Second PB",
            "ProcessType": "InvocableProcess",
            "IsActive": False,
            "Description": "Legacy",
        },
    ]
    metadata = [
        _object_type_meta("PB_One", "Opportunity"),
        _object_type_meta("PB_Two", "Opportunity"),
    ]
    client = _make_client(view_records, metadata)
    specs = _run(process_builder.fetch(client, "Opportunity"))
    assert len(specs) == 2
    api_names = {s.api_name for s in specs}
    assert api_names == {"PB_One", "PB_Two"}
