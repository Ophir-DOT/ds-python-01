from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import validation


def test_fetch_filters_listing_to_object_prefix() -> None:
    client = MagicMock()
    client.list_metadata = AsyncMock(
        return_value=[
            {"fullName": "Account.Min_Annual_Revenue"},
            {"fullName": "Opportunity.Close_Date_Required"},
            {"fullName": "Account.Name_Not_Empty"},
        ]
    )
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account.Min_Annual_Revenue",
                "active": "true",
                "description": "Revenue check",
                "errorConditionFormula": "AnnualRevenue < 0",
                "errorMessage": "Revenue cannot be negative",
            },
            {
                "fullName": "Account.Name_Not_Empty",
                "active": "false",
                "errorConditionFormula": "ISBLANK(Name)",
                "errorMessage": "Name is required",
            },
        ]
    )
    specs = asyncio.run(validation.fetch(client, "Account"))
    # Only the Account.* rules should have been requested via read_metadata
    requested = client.read_metadata.call_args.args[1]
    assert requested == ["Account.Min_Annual_Revenue", "Account.Name_Not_Empty"]

    assert [s.api_name for s in specs] == ["Min_Annual_Revenue", "Name_Not_Empty"]
    assert specs[0].active is True
    assert specs[0].error_condition == "AnnualRevenue < 0"
    assert specs[1].active is False


def test_fetch_defaults_active_to_true_when_field_absent() -> None:
    client = MagicMock()
    client.list_metadata = AsyncMock(return_value=[{"fullName": "Account.Rule"}])
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account.Rule",
                "errorConditionFormula": "FALSE",
                "errorMessage": "x",
            }
        ]
    )
    specs = asyncio.run(validation.fetch(client, "Account"))
    assert specs[0].active is True


def test_fetch_returns_empty_when_no_object_rules_listed() -> None:
    client = MagicMock()
    client.list_metadata = AsyncMock(
        return_value=[{"fullName": "Opportunity.OnlyOpp"}]
    )
    client.read_metadata = AsyncMock()
    specs = asyncio.run(validation.fetch(client, "Account"))
    assert specs == []
    client.read_metadata.assert_not_called()


def test_error_location_defaults_to_top_of_page_when_field_absent() -> None:
    """error_location is 'Top of Page' when errorDisplayField is absent or blank."""
    client = MagicMock()
    client.list_metadata = AsyncMock(
        return_value=[
            {"fullName": "Account.NoField"},
            {"fullName": "Account.BlankField"},
        ]
    )
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account.NoField",
                "errorConditionFormula": "TRUE",
                "errorMessage": "err",
                # errorDisplayField key entirely absent
            },
            {
                "fullName": "Account.BlankField",
                "errorConditionFormula": "TRUE",
                "errorMessage": "err",
                "errorDisplayField": "",  # present but empty
            },
        ]
    )
    specs = asyncio.run(validation.fetch(client, "Account"))
    assert specs[0].error_location == "Top of Page"
    assert specs[1].error_location == "Top of Page"


def test_error_location_equals_field_when_error_display_field_present() -> None:
    """error_location reflects the errorDisplayField value when it is non-blank."""
    client = MagicMock()
    client.list_metadata = AsyncMock(
        return_value=[{"fullName": "Account.FieldLevel"}]
    )
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account.FieldLevel",
                "errorConditionFormula": "TRUE",
                "errorMessage": "err",
                "errorDisplayField": "AnnualRevenue__c",
            }
        ]
    )
    specs = asyncio.run(validation.fetch(client, "Account"))
    assert specs[0].error_location == "AnnualRevenue__c"
