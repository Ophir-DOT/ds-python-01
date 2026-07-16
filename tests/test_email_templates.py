from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import email_templates
from ds_tool.metadata.email_templates import _developer_name


def test_developer_name_strips_folder_prefix() -> None:
    assert _developer_name("Sales_Folder/Win_Notification") == "Win_Notification"
    assert _developer_name("unfiled$public/Bare_Name") == "Bare_Name"
    assert _developer_name("NoSlash") == "NoSlash"


def test_fetch_referenced_returns_empty_for_empty_input() -> None:
    client = MagicMock()
    assert asyncio.run(email_templates.fetch_referenced(client, [])) == []


def test_fetch_referenced_preserves_input_order_and_dedupes() -> None:
    client = MagicMock()
    client.query_all = AsyncMock(
        return_value=[
            {
                "DeveloperName": "Win_Notification",
                "Name": "Win Notification",
                "FolderName": "Sales",
                "TemplateType": "text",
                "Subject": "You won!",
                "BrandTemplateId": None,
                "FolderId": None,
                "HtmlValue": None,
                "Body": None,
            },
            {
                "DeveloperName": "Team_Update",
                "Name": "Team Update",
                "FolderName": "Public",
                "TemplateType": "html",
                "Subject": "FYI",
                "BrandTemplateId": None,
                "FolderId": None,
                "HtmlValue": None,
                "Body": None,
            },
        ]
    )
    refs = [
        "Sales_Folder/Win_Notification",
        "unfiled$public/Team_Update",
        "Sales_Folder/Win_Notification",  # dupe; should not produce a second row
    ]
    specs = asyncio.run(email_templates.fetch_referenced(client, refs))
    assert [s.developer_name for s in specs] == ["Win_Notification", "Team_Update"]
    assert specs[0].label == "Win Notification"
    assert specs[0].folder == "Sales"
    assert specs[1].template_type == "html"


def test_fetch_referenced_drops_unresolved_names() -> None:
    client = MagicMock()
    client.query_all = AsyncMock(return_value=[])  # query returns nothing
    specs = asyncio.run(
        email_templates.fetch_referenced(client, ["folder/Missing"])
    )
    assert specs == []


def test_fetch_referenced_populates_extended_fields() -> None:
    """letterhead_id, folder_id, body, body_plain are mapped from SOQL columns."""
    client = MagicMock()
    client.query_all = AsyncMock(
        return_value=[
            {
                "DeveloperName": "Rich_Template",
                "Name": "Rich Template",
                "FolderName": "Marketing",
                "TemplateType": "html",
                "Subject": "Hello",
                "BrandTemplateId": "0LHxx000000BRAND",
                "FolderId": "00lxx000000FOLDER",
                "HtmlValue": "<p>Hello world</p>",
                "Body": "Hello world",
            }
        ]
    )
    specs = asyncio.run(
        email_templates.fetch_referenced(client, ["Marketing/Rich_Template"])
    )
    assert len(specs) == 1
    s = specs[0]
    assert s.letterhead_id == "0LHxx000000BRAND"
    assert s.folder_id == "00lxx000000FOLDER"
    assert s.body == "<p>Hello world</p>"
    assert s.body_plain == "Hello world"
    # email_layout_id is always None (not available via standard SOQL)
    assert s.email_layout_id is None


def test_fetch_referenced_extended_fields_default_to_none_when_absent() -> None:
    """Missing/None SOQL values for extended fields produce None on the spec."""
    client = MagicMock()
    client.query_all = AsyncMock(
        return_value=[
            {
                "DeveloperName": "Plain_Template",
                "Name": "Plain Template",
                "FolderName": "General",
                "TemplateType": "text",
                "Subject": "Hi",
                # New columns absent from the dict entirely
            }
        ]
    )
    specs = asyncio.run(
        email_templates.fetch_referenced(client, ["General/Plain_Template"])
    )
    assert len(specs) == 1
    s = specs[0]
    assert s.letterhead_id is None
    assert s.email_layout_id is None
    assert s.folder_id is None
    assert s.body is None
    assert s.body_plain is None


def test_fetch_referenced_extended_fields_empty_string_coerced_to_none() -> None:
    """Empty-string values for extended fields are coerced to None."""
    client = MagicMock()
    client.query_all = AsyncMock(
        return_value=[
            {
                "DeveloperName": "Empty_Template",
                "Name": "Empty Template",
                "FolderName": "General",
                "TemplateType": "text",
                "Subject": "Hi",
                "BrandTemplateId": "",
                "FolderId": "",
                "HtmlValue": "",
                "Body": "",
            }
        ]
    )
    specs = asyncio.run(
        email_templates.fetch_referenced(client, ["General/Empty_Template"])
    )
    assert len(specs) == 1
    s = specs[0]
    assert s.letterhead_id is None
    assert s.folder_id is None
    assert s.body is None
    assert s.body_plain is None
