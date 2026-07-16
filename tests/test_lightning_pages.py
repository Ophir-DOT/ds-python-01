from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import lightning_pages


def test_fetch_picks_app_and_profile_overrides_for_object() -> None:
    client = MagicMock()
    client.list_metadata = AsyncMock(
        return_value=[{"fullName": "Sales_App"}, {"fullName": "Service_App"}]
    )
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Sales_App",
                "actionOverrides": [
                    {
                        "actionName": "View",
                        "type": "Flexipage",
                        "pageOrSobjectType": "Account",
                        "formFactor": "Large",
                        "content": "Sales_Account_Record_Page",
                    },
                    {
                        # wrong action — must be ignored
                        "actionName": "Edit",
                        "type": "Flexipage",
                        "pageOrSobjectType": "Account",
                        "content": "Edit_Page",
                    },
                    {
                        # wrong object — must be ignored
                        "actionName": "View",
                        "type": "Flexipage",
                        "pageOrSobjectType": "Opportunity",
                        "content": "Opp_Page",
                    },
                    {
                        # wrong type (standard layout, not FlexiPage) — must be ignored
                        "actionName": "View",
                        "type": "Standard",
                        "pageOrSobjectType": "Account",
                        "content": None,
                    },
                ],
                "profileActionOverrides": [
                    {
                        "actionName": "View",
                        "type": "Flexipage",
                        "pageOrSobjectType": "Account",
                        "formFactor": "Large",
                        "profile": "System Administrator",
                        "recordType": "Account.Customer",
                        "content": "Admin_Account_Page",
                    }
                ],
            },
            {
                "fullName": "Service_App",
                # No relevant overrides for Account — entire app should be skipped.
                "actionOverrides": [
                    {
                        "actionName": "View",
                        "type": "Flexipage",
                        "pageOrSobjectType": "Case",
                        "content": "Case_Page",
                    }
                ],
            },
        ]
    )
    assignments = asyncio.run(lightning_pages.fetch(client, "Account"))
    assert len(assignments) == 2

    default = assignments[0]
    assert default.app == "Sales_App"
    assert default.profile is None
    assert default.record_type is None
    assert default.flexipage == "Sales_Account_Record_Page"

    per_profile = assignments[1]
    assert per_profile.profile == "System Administrator"
    # "Object.RT" should be trimmed to just "RT" for display.
    assert per_profile.record_type == "Customer"
    assert per_profile.flexipage == "Admin_Account_Page"


def test_fetch_returns_empty_on_listing_failure() -> None:
    client = MagicMock()
    client.list_metadata = AsyncMock(side_effect=RuntimeError("SOAP fault"))
    assert asyncio.run(lightning_pages.fetch(client, "Account")) == []
