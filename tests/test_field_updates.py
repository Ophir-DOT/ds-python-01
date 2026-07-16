from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import field_updates


def _run(coro):
    return asyncio.run(coro)


def test_fetch_parses_workflow_field_updates() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account",
                "fieldUpdates": [
                    {
                        "fullName": "Account.Set_Status_Active",
                        "name": "Set Status Active",
                        "description": "Sets status to Active on close",
                        "field": "Status__c",
                        "operation": "Literal",
                        "literalValue": "Active",
                        "notifyAssignee": "false",
                        "reevaluateOnChange": "true",
                    },
                    {
                        "fullName": "Account.Clear_Description",
                        "name": "Clear Description",
                        "description": None,
                        "field": "Description",
                        "operation": "Null",
                        "formula": None,
                        "literalValue": None,
                        "notifyAssignee": True,
                        "reevaluateOnChange": False,
                    },
                ],
            }
        ]
    )
    specs = _run(field_updates.fetch(client, "Account"))
    assert len(specs) == 2

    first = specs[0]
    assert first.api_name == "Account.Set_Status_Active"
    assert first.name == "Set Status Active"
    assert first.description == "Sets status to Active on close"
    assert first.field == "Status__c"
    assert first.operation == "Literal"
    assert first.value == "Active"
    assert first.notify_assignee is False
    assert first.reevaluate_workflow_rules is True

    second = specs[1]
    assert second.api_name == "Account.Clear_Description"
    assert second.value is None
    assert second.notify_assignee is True
    assert second.reevaluate_workflow_rules is False


def test_fetch_uses_formula_when_literal_value_absent() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Opportunity",
                "fieldUpdates": [
                    {
                        "fullName": "Opportunity.Compute_Score",
                        "name": "Compute Score",
                        "field": "Score__c",
                        "operation": "Formula",
                        "formula": "Amount * 0.1",
                        "literalValue": None,
                        "notifyAssignee": None,
                        "reevaluateOnChange": None,
                    }
                ],
            }
        ]
    )
    specs = _run(field_updates.fetch(client, "Opportunity"))
    assert len(specs) == 1
    assert specs[0].value == "Amount * 0.1"
    assert specs[0].notify_assignee is None
    assert specs[0].reevaluate_workflow_rules is None


def test_fetch_handles_single_field_update_not_in_list() -> None:
    """The SOAP API may return a single dict instead of a list when there is only one item."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Lead",
                "fieldUpdates": {
                    "fullName": "Lead.Single_Update",
                    "name": "Single Update",
                    "field": "LeadSource",
                    "operation": "Literal",
                    "literalValue": "Web",
                    "notifyAssignee": "true",
                    "reevaluateOnChange": "false",
                },
            }
        ]
    )
    specs = _run(field_updates.fetch(client, "Lead"))
    assert len(specs) == 1
    assert specs[0].api_name == "Lead.Single_Update"
    assert specs[0].notify_assignee is True


def test_fetch_skips_entries_without_full_name() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Contact",
                "fieldUpdates": [
                    {"fullName": "", "name": "Bad entry", "field": "Title"},
                    {"fullName": "Contact.Good_Update", "name": "Good", "field": "Title"},
                ],
            }
        ]
    )
    specs = _run(field_updates.fetch(client, "Contact"))
    assert len(specs) == 1
    assert specs[0].api_name == "Contact.Good_Update"


def test_fetch_returns_empty_on_metadata_error() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(side_effect=RuntimeError("SOAP fault"))
    assert _run(field_updates.fetch(client, "Account")) == []


def test_fetch_returns_empty_when_no_field_updates() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[{"fullName": "Account"}]  # no fieldUpdates key
    )
    specs = _run(field_updates.fetch(client, "Account"))
    assert specs == []
