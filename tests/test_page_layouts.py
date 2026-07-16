from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import page_layouts


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helper data
# ---------------------------------------------------------------------------

_LAYOUT_FULL_NAME = "Account-Account Layout"

_LAYOUT_RAW = {
    "fullName": _LAYOUT_FULL_NAME,
    "layoutSections": [
        {
            "label": "Account Information",
            "layoutColumns": [
                {
                    "layoutItems": [
                        {"field": "Name", "behavior": "Required", "emptySpace": False},
                        {"field": "Phone", "behavior": "Edit", "emptySpace": False},
                    ]
                },
                {
                    "layoutItems": [
                        {"emptySpace": True},
                        {"field": "Website", "behavior": "Edit", "emptySpace": False},
                    ]
                },
            ],
        },
        {
            "label": "Address",
            "layoutColumns": [
                {
                    "layoutItems": [
                        {"field": "BillingCity", "behavior": "Edit", "emptySpace": False},
                    ]
                }
            ],
        },
    ],
    "platformActionList": {
        "platformActionListItems": [
            {"actionName": "Edit", "subtype": None},
            {"actionName": "Delete", "subtype": None},
        ]
    },
    "customButtons": ["Send_Email"],
    "relatedLists": [
        {
            "relatedList": "Contacts",
            "fields": ["Name", "Email"],
            "customButtons": ["New"],
        },
        {
            "relatedList": "Opportunities",
            "fields": ["Name", "Amount", "CloseDate"],
            "customButtons": [],
        },
    ],
}


def _make_client(list_metadata_return=None, read_metadata_return=None):
    client = MagicMock()
    client.list_metadata = AsyncMock(
        return_value=list_metadata_return
        if list_metadata_return is not None
        else [{"fullName": _LAYOUT_FULL_NAME}]
    )
    client.read_metadata = AsyncMock(
        return_value=read_metadata_return
        if read_metadata_return is not None
        else [_LAYOUT_RAW]
    )
    return client


# ---------------------------------------------------------------------------
# Tests: section / field parsing
# ---------------------------------------------------------------------------


def test_fetch_returns_one_layout() -> None:
    client = _make_client()
    specs = _run(page_layouts.fetch(client, "Account"))
    assert len(specs) == 1
    assert specs[0].api_name == _LAYOUT_FULL_NAME


def test_fetch_parses_sections() -> None:
    client = _make_client()
    specs = _run(page_layouts.fetch(client, "Account"))
    layout = specs[0]
    assert len(layout.sections) == 2
    assert layout.sections[0].label == "Account Information"
    assert layout.sections[1].label == "Address"


def test_fetch_parses_fields_with_positions() -> None:
    client = _make_client()
    specs = _run(page_layouts.fetch(client, "Account"))
    section = specs[0].sections[0]
    # Left column: Name at row 1, Phone at row 2
    left_fields = [f for f in section.fields if f.position and f.position.endswith("L")]
    assert any(f.label == "Name" and f.position == "1L" for f in left_fields)
    assert any(f.label == "Phone" and f.position == "2L" for f in left_fields)


def test_fetch_skips_empty_spaces_but_increments_row() -> None:
    """emptySpace=True items must be skipped; the row counter still advances."""
    client = _make_client()
    specs = _run(page_layouts.fetch(client, "Account"))
    section = specs[0].sections[0]
    # Right column: first item is emptySpace (row 1 skipped), Website is row 2
    right_fields = [f for f in section.fields if f.position and f.position.endswith("R")]
    assert len(right_fields) == 1
    assert right_fields[0].label == "Website"
    assert right_fields[0].position == "2R"


def test_fetch_parses_field_behavior() -> None:
    client = _make_client()
    specs = _run(page_layouts.fetch(client, "Account"))
    section = specs[0].sections[0]
    name_field = next(f for f in section.fields if f.label == "Name")
    assert name_field.behavior == "Required"
    phone_field = next(f for f in section.fields if f.label == "Phone")
    assert phone_field.behavior == "Edit"


def test_fetch_parses_columns_count() -> None:
    client = _make_client()
    specs = _run(page_layouts.fetch(client, "Account"))
    assert specs[0].sections[0].columns == 2
    assert specs[0].sections[1].columns == 1


# ---------------------------------------------------------------------------
# Tests: buttons
# ---------------------------------------------------------------------------


def test_fetch_parses_standard_buttons() -> None:
    # Standard buttons = the default set minus excludeButtons; the default
    # fixture has no excludeButtons, so all defaults are present.
    client = _make_client()
    specs = _run(page_layouts.fetch(client, "Account"))
    assert "Edit" in specs[0].standard_buttons
    assert "Delete" in specs[0].standard_buttons


def test_fetch_parses_custom_buttons() -> None:
    client = _make_client()
    specs = _run(page_layouts.fetch(client, "Account"))
    assert specs[0].custom_buttons == ["Send_Email"]


# ---------------------------------------------------------------------------
# Tests: standard buttons (default set minus excludeButtons) + mobile actions
# (the entire platformActionList). Mirrors Ctrl_CMP_Configuration_Report.cls:1266.
# ---------------------------------------------------------------------------

_ALL_STANDARD = [
    "Edit", "Submit", "Clone", "Delete",
    "Change Owner", "Change Record Type", "Printable View",
]


def test_standard_buttons_default_set_when_no_excludes() -> None:
    raw = {"fullName": "Account-Layout", "customButtons": []}
    client = _make_client(read_metadata_return=[raw])
    specs = _run(page_layouts.fetch(client, "Account"))
    assert specs[0].standard_buttons == _ALL_STANDARD


def test_standard_buttons_minus_exclude_buttons() -> None:
    # excludeButtons lists the standard buttons to HIDE (internal API names).
    raw = {
        "fullName": "Account-Layout",
        "excludeButtons": ["Delete", "ChangeOwnerOne", "PrintableView"],
        "customButtons": [],
    }
    client = _make_client(read_metadata_return=[raw])
    sb = _run(page_layouts.fetch(client, "Account"))[0].standard_buttons
    assert "Edit" in sb and "Clone" in sb and "Submit" in sb
    assert "Delete" not in sb
    assert "Change Owner" not in sb       # ChangeOwnerOne excluded
    assert "Printable View" not in sb     # PrintableView excluded


def test_standard_buttons_exclude_single_string() -> None:
    raw = {"fullName": "Account-Layout", "excludeButtons": "Edit", "customButtons": []}
    client = _make_client(read_metadata_return=[raw])
    sb = _run(page_layouts.fetch(client, "Account"))[0].standard_buttons
    assert "Edit" not in sb
    assert "Clone" in sb


def test_mobile_actions_are_entire_platform_action_list() -> None:
    raw = {
        "fullName": "Account-Layout",
        "platformActionList": [
            {"actionListContext": "Record", "platformActionListItems": [
                {"actionName": "NewTask"}, {"actionName": "SendEmail"}]},
            {"actionListContext": "Salesforce1", "platformActionListItems": [
                {"actionName": "MobileEdit"}]},
        ],
        "customButtons": [],
    }
    client = _make_client(read_metadata_return=[raw])
    ma = _run(page_layouts.fetch(client, "Account"))[0].mobile_actions
    assert ma == ["NewTask", "SendEmail", "MobileEdit"]


def test_mobile_actions_single_dict_platform_action_list() -> None:
    raw = {
        "fullName": "Account-Layout",
        "platformActionList": {"platformActionListItems": [
            {"actionName": "NewTask"}, {"actionName": "LogACall"}]},
        "customButtons": [],
    }
    client = _make_client(read_metadata_return=[raw])
    assert _run(page_layouts.fetch(client, "Account"))[0].mobile_actions == ["NewTask", "LogACall"]


def test_mobile_actions_empty_when_no_platform_action_list() -> None:
    raw = {"fullName": "Account-Layout", "customButtons": []}
    client = _make_client(read_metadata_return=[raw])
    assert _run(page_layouts.fetch(client, "Account"))[0].mobile_actions == []


def test_custom_buttons_top_level() -> None:
    raw = {"fullName": "Account-Layout", "customButtons": ["My_Custom_Btn"]}
    client = _make_client(read_metadata_return=[raw])
    assert _run(page_layouts.fetch(client, "Account"))[0].custom_buttons == ["My_Custom_Btn"]


# ---------------------------------------------------------------------------
# Tests: related lists
# ---------------------------------------------------------------------------


def test_fetch_parses_related_lists() -> None:
    client = _make_client()
    specs = _run(page_layouts.fetch(client, "Account"))
    rls = specs[0].related_lists
    assert len(rls) == 2
    contacts = next(rl for rl in rls if rl.name == "Contacts")
    assert contacts.fields == ["Name", "Email"]
    assert contacts.buttons == ["New"]


def test_fetch_related_list_empty_buttons() -> None:
    client = _make_client()
    specs = _run(page_layouts.fetch(client, "Account"))
    opps = next(rl for rl in specs[0].related_lists if rl.name == "Opportunities")
    assert opps.buttons == []
    assert opps.fields == ["Name", "Amount", "CloseDate"]


# ---------------------------------------------------------------------------
# Tests: filtering by object prefix
# ---------------------------------------------------------------------------


def test_fetch_filters_layouts_by_object_prefix() -> None:
    """list_metadata returns layouts for multiple objects; only Account's are used."""
    client = _make_client(
        list_metadata_return=[
            {"fullName": "Account-Account Layout"},
            {"fullName": "Contact-Contact Layout"},
            {"fullName": "Opportunity-Opportunity Layout"},
        ]
    )
    _run(page_layouts.fetch(client, "Account"))
    # read_metadata should only be called with the Account-prefixed name
    called_names = client.read_metadata.call_args[0][1]
    assert called_names == ["Account-Account Layout"]


def test_fetch_returns_empty_when_no_matching_layouts() -> None:
    client = _make_client(
        list_metadata_return=[
            {"fullName": "Contact-Contact Layout"},
        ]
    )
    result = _run(page_layouts.fetch(client, "Account"))
    assert result == []
    client.read_metadata.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


def test_fetch_returns_empty_on_list_metadata_error() -> None:
    client = MagicMock()
    client.list_metadata = AsyncMock(side_effect=RuntimeError("network error"))
    result = _run(page_layouts.fetch(client, "Account"))
    assert result == []


def test_fetch_returns_empty_on_read_metadata_error() -> None:
    client = MagicMock()
    client.list_metadata = AsyncMock(return_value=[{"fullName": "Account-Account Layout"}])
    client.read_metadata = AsyncMock(side_effect=RuntimeError("SOAP fault"))
    result = _run(page_layouts.fetch(client, "Account"))
    assert result == []


def test_fetch_skips_record_without_full_name() -> None:
    client = _make_client(read_metadata_return=[{"layoutSections": []}])
    result = _run(page_layouts.fetch(client, "Account"))
    assert result == []


def test_fetch_handles_non_dict_section_items() -> None:
    """Non-dict items in layoutSections list are skipped gracefully."""
    raw = {**_LAYOUT_RAW, "layoutSections": [None, "bad", _LAYOUT_RAW["layoutSections"][0]]}
    client = _make_client(read_metadata_return=[raw])
    specs = _run(page_layouts.fetch(client, "Account"))
    assert len(specs) == 1
    # Only the one valid section should be parsed
    assert len(specs[0].sections) == 1


# ---------------------------------------------------------------------------
# Tests: single-item dict coercion (Salesforce API returns single item as dict)
# ---------------------------------------------------------------------------


def test_fetch_handles_single_layout_section_as_dict() -> None:
    """When Salesforce returns a single layoutSection as a dict (not list), it still parses."""
    raw = {
        **_LAYOUT_RAW,
        "layoutSections": _LAYOUT_RAW["layoutSections"][0],  # dict, not list
    }
    client = _make_client(read_metadata_return=[raw])
    specs = _run(page_layouts.fetch(client, "Account"))
    assert len(specs[0].sections) == 1


def test_fetch_handles_single_related_list_as_dict() -> None:
    """Single relatedList returned as dict is coerced to a list."""
    raw = {
        **_LAYOUT_RAW,
        "relatedLists": _LAYOUT_RAW["relatedLists"][0],  # dict, not list
    }
    client = _make_client(read_metadata_return=[raw])
    specs = _run(page_layouts.fetch(client, "Account"))
    assert len(specs[0].related_lists) == 1
    assert specs[0].related_lists[0].name == "Contacts"
