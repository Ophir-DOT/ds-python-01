from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import field_sets


def _run(coro):
    return asyncio.run(coro)


def test_fetch_parses_field_sets() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account",
                "fieldSets": [
                    {
                        "fullName": "Contact_Fields",
                        "label": "Contact Fields",
                        "description": "Fields for contact view",
                        "displayedFields": [
                            {"field": "Name"},
                            {"field": "Email"},
                            {"field": "Phone"},
                        ],
                    },
                    {
                        "fullName": "Summary_Fields",
                        "label": "Summary Fields",
                        "description": None,
                        "displayedFields": {"field": "Industry"},
                    },
                ],
            }
        ]
    )
    specs = _run(field_sets.fetch(client, "Account"))
    assert len(specs) == 2

    first = specs[0]
    assert first.api_name == "Contact_Fields"
    assert first.label == "Contact Fields"
    assert first.description == "Fields for contact view"
    assert first.fields == ["Name", "Email", "Phone"]

    second = specs[1]
    assert second.api_name == "Summary_Fields"
    assert second.label == "Summary Fields"
    assert second.description is None
    # single dict should be normalised to a list
    assert second.fields == ["Industry"]


def test_fetch_skips_entries_without_full_name() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account",
                "fieldSets": [
                    {"fullName": "", "label": "Bad", "displayedFields": []},
                    {"fullName": "Good_FS", "label": "Good", "displayedFields": []},
                ],
            }
        ]
    )
    specs = _run(field_sets.fetch(client, "Account"))
    assert len(specs) == 1
    assert specs[0].api_name == "Good_FS"


def test_fetch_handles_no_field_sets_key() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[{"fullName": "Account"}]
    )
    specs = _run(field_sets.fetch(client, "Account"))
    assert specs == []


def test_fetch_handles_empty_displayed_fields() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account",
                "fieldSets": [
                    {
                        "fullName": "Empty_FS",
                        "label": "Empty",
                        "displayedFields": [],
                    }
                ],
            }
        ]
    )
    specs = _run(field_sets.fetch(client, "Account"))
    assert len(specs) == 1
    assert specs[0].fields == []


def test_fetch_returns_empty_on_metadata_error() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(side_effect=RuntimeError("SOAP fault"))
    assert _run(field_sets.fetch(client, "Account")) == []
