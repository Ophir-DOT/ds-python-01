from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import email_alerts


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_recipient_label_combines_type_and_recipient() -> None:
    from ds_tool.metadata.email_alerts import _recipient_label

    assert _recipient_label({"type": "user", "recipient": "john"}) == "user: john"
    assert _recipient_label({"type": "role"}) == "role"
    assert _recipient_label({"recipient": "owner"}) == "owner"
    assert _recipient_label({}) == ""


def test_fetch_parses_workflow_alerts() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account",
                "alerts": [
                    {
                        "fullName": "Notify_Owner",
                        "description": "Notify on win",
                        "senderType": "CurrentUser",
                        "senderAddress": None,
                        "template": "Sales_Folder/Win_Notification",
                        "recipients": [
                            {"type": "user", "recipient": "owner"},
                            {"type": "role", "recipient": "Sales Manager"},
                        ],
                    },
                    {
                        "fullName": "Notify_Team",
                        "template": "unfiled$public/Team_Update",
                        "recipients": {"type": "user", "recipient": "tester"},
                    },
                ],
            }
        ]
    )
    specs = _run(email_alerts.fetch(client, "Account"))
    assert len(specs) == 2
    first = specs[0]
    assert first.api_name == "Notify_Owner"
    assert first.template == "Sales_Folder/Win_Notification"
    assert first.recipients == ["user: owner", "role: Sales Manager"]
    second = specs[1]
    assert second.recipients == ["user: tester"]


def test_fetch_parses_protected_field() -> None:
    """protected is mapped from the WorkflowAlert `protected` boolean field."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account",
                "alerts": [
                    {
                        "fullName": "Protected_Alert",
                        "template": "folder/T",
                        "protected": True,
                    },
                    {
                        "fullName": "Unprotected_Alert",
                        "template": "folder/T",
                        "protected": False,
                    },
                    {
                        "fullName": "No_Protected_Field",
                        "template": "folder/T",
                        # `protected` key absent — should become None
                    },
                    {
                        "fullName": "String_True_Alert",
                        "template": "folder/T",
                        # SOAP API sometimes returns strings instead of booleans
                        "protected": "true",
                    },
                    {
                        "fullName": "String_False_Alert",
                        "template": "folder/T",
                        "protected": "false",
                    },
                ],
            }
        ]
    )
    specs = _run(email_alerts.fetch(client, "Account"))
    assert len(specs) == 5

    assert specs[0].protected is True
    assert specs[1].protected is False
    assert specs[2].protected is None
    assert specs[3].protected is True   # "true" string coerced to bool
    assert specs[4].protected is False  # "false" string coerced to bool


def test_fetch_last_checkbox_always_none() -> None:
    """last_checkbox is not exposed by the Workflow metadata API; always None."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account",
                "alerts": [
                    {"fullName": "Some_Alert", "template": "folder/T"},
                ],
            }
        ]
    )
    specs = _run(email_alerts.fetch(client, "Account"))
    assert len(specs) == 1
    assert specs[0].last_checkbox is None


def test_referenced_template_names_dedupes_preserving_order() -> None:
    from ds_tool.models import EmailAlertSpec

    alerts = [
        EmailAlertSpec(api_name="A", template="folder/A"),
        EmailAlertSpec(api_name="B", template=None),
        EmailAlertSpec(api_name="C", template="folder/A"),  # duplicate
        EmailAlertSpec(api_name="D", template="folder/B"),
    ]
    assert email_alerts.referenced_template_names(alerts) == ["folder/A", "folder/B"]


def test_fetch_returns_empty_on_metadata_error() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(side_effect=RuntimeError("SOAP fault"))
    assert _run(email_alerts.fetch(client, "Account")) == []
