from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import compact_layouts


def _run(coro):
    return asyncio.run(coro)


def test_fetch_parses_compact_layouts() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account",
                "compactLayouts": [
                    {
                        "fullName": "Compact_Layout_1",
                        "label": "Primary Compact Layout",
                        "fields": ["Name", "Phone", "Website"],
                    },
                    {
                        "fullName": "Compact_Layout_2",
                        "label": "Secondary Compact Layout",
                        "fields": "Email",  # single value (not a list)
                    },
                ],
            }
        ]
    )
    specs = _run(compact_layouts.fetch(client, "Account"))
    assert len(specs) == 2

    first = specs[0]
    assert first.api_name == "Compact_Layout_1"
    assert first.label == "Primary Compact Layout"
    assert first.fields == ["Name", "Phone", "Website"]

    second = specs[1]
    assert second.api_name == "Compact_Layout_2"
    assert second.label == "Secondary Compact Layout"
    assert second.fields == ["Email"]


def test_fetch_skips_entries_without_full_name() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account",
                "compactLayouts": [
                    {"label": "No Name Layout", "fields": ["Name"]},
                    {"fullName": "", "label": "Empty Name", "fields": ["Phone"]},
                    {"fullName": "Valid_Layout", "label": "Valid", "fields": ["Name"]},
                ],
            }
        ]
    )
    specs = _run(compact_layouts.fetch(client, "Account"))
    assert len(specs) == 1
    assert specs[0].api_name == "Valid_Layout"


def test_fetch_handles_missing_compact_layouts_key() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[{"fullName": "Account"}]  # no compactLayouts key
    )
    specs = _run(compact_layouts.fetch(client, "Account"))
    assert specs == []


def test_fetch_handles_null_compact_layouts() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[{"fullName": "Account", "compactLayouts": None}]
    )
    specs = _run(compact_layouts.fetch(client, "Account"))
    assert specs == []


def test_fetch_returns_empty_on_metadata_error() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(side_effect=RuntimeError("SOAP fault"))
    assert _run(compact_layouts.fetch(client, "Account")) == []


def test_fetch_single_compact_layout_not_in_list() -> None:
    """A single compactLayouts entry may arrive as a dict rather than a list."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Contact",
                "compactLayouts": {
                    "fullName": "Only_Layout",
                    "label": "Only Layout",
                    "fields": ["FirstName", "LastName"],
                },
            }
        ]
    )
    specs = _run(compact_layouts.fetch(client, "Contact"))
    assert len(specs) == 1
    assert specs[0].api_name == "Only_Layout"
    assert specs[0].fields == ["FirstName", "LastName"]
