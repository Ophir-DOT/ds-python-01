from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import search_layouts


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helper: names of all six expected layout types in canonical order
# ---------------------------------------------------------------------------

ALL_LAYOUT_TYPES = [
    "Default Layout",
    "List View",
    "Lookup Dialog",
    "Lookup Phone Dialogs",
    "Search Filter Fields",
    "Tab",
]


# ---------------------------------------------------------------------------
# Always-emit: all six rows present even with an empty/missing payload
# ---------------------------------------------------------------------------


def test_parse_empty_dict_returns_all_six_rows() -> None:
    """An empty searchLayouts dict still produces all six layout-type rows."""
    specs = search_layouts._parse_search_layouts({})
    layout_types = [s.layout_type for s in specs]
    assert layout_types == ALL_LAYOUT_TYPES


def test_parse_empty_dict_all_rows_have_empty_columns_and_buttons() -> None:
    specs = search_layouts._parse_search_layouts({})
    for sl in specs:
        assert sl.columns == [], f"{sl.layout_type} should have empty columns"
        assert sl.buttons == [], f"{sl.layout_type} should have empty buttons"


def test_search_filter_fields_row_present_when_key_absent() -> None:
    """'Search Filter Fields' row is always emitted even when searchFilterFields is absent."""
    raw = {"searchResultsAdditionalFields": ["Name"]}
    specs = search_layouts._parse_search_layouts(raw)
    layout_types = [s.layout_type for s in specs]
    assert "Search Filter Fields" in layout_types
    sf = next(s for s in specs if s.layout_type == "Search Filter Fields")
    assert sf.columns == []
    assert sf.buttons == []


def test_tab_row_present_when_key_absent() -> None:
    """'Tab' row is always emitted even when tabOrderButtons is absent."""
    raw = {"searchResultsAdditionalFields": ["Name"]}
    specs = search_layouts._parse_search_layouts(raw)
    layout_types = [s.layout_type for s in specs]
    assert "Tab" in layout_types
    tab = next(s for s in specs if s.layout_type == "Tab")
    assert tab.columns == []
    assert tab.buttons == []


def test_lookup_dialog_row_present_when_key_absent() -> None:
    """'Lookup Dialog' row is always emitted even when lookupDialogsAdditionalFields is absent."""
    raw = {"tabOrderButtons": ["Submit"]}
    specs = search_layouts._parse_search_layouts(raw)
    layout_types = [s.layout_type for s in specs]
    assert "Lookup Dialog" in layout_types
    ld = next(s for s in specs if s.layout_type == "Lookup Dialog")
    assert ld.columns == []


def test_lookup_phone_dialogs_row_present_when_key_absent() -> None:
    """'Lookup Phone Dialogs' row is always emitted even when the key is absent."""
    raw = {"searchResultsAdditionalFields": ["Name"]}
    specs = search_layouts._parse_search_layouts(raw)
    layout_types = [s.layout_type for s in specs]
    assert "Lookup Phone Dialogs" in layout_types
    lpd = next(s for s in specs if s.layout_type == "Lookup Phone Dialogs")
    assert lpd.columns == []
    assert lpd.buttons == []


def test_default_layout_row_present_when_key_absent() -> None:
    """'Default Layout' row is always emitted even when searchResultsAdditionalFields is absent."""
    raw = {"tabOrderButtons": ["Submit"]}
    specs = search_layouts._parse_search_layouts(raw)
    layout_types = [s.layout_type for s in specs]
    assert "Default Layout" in layout_types
    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns == []


def test_list_view_row_present_when_all_keys_absent() -> None:
    """'List View' row is always emitted even when listView keys are absent."""
    raw = {"searchFilterFields": ["Name"]}
    specs = search_layouts._parse_search_layouts(raw)
    layout_types = [s.layout_type for s in specs]
    assert "List View" in layout_types
    lv = next(s for s in specs if s.layout_type == "List View")
    assert lv.columns == []
    assert lv.buttons == []


# ---------------------------------------------------------------------------
# Canonical row order is always the same
# ---------------------------------------------------------------------------


def test_parse_canonical_row_order() -> None:
    """Rows are always returned in canonical order regardless of which keys are present."""
    raw = {
        "tabOrderButtons": ["Submit"],
        "searchFilterFields": ["Name"],
        "listViewButtons": ["New"],
    }
    specs = search_layouts._parse_search_layouts(raw)
    assert [s.layout_type for s in specs] == ALL_LAYOUT_TYPES


# ---------------------------------------------------------------------------
# Column / button values are populated correctly when keys are present
# ---------------------------------------------------------------------------


def test_parse_default_layout_columns() -> None:
    raw = {"searchResultsAdditionalFields": ["Name", "CreatedDate"]}
    specs = search_layouts._parse_search_layouts(raw)
    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns == ["Name", "CreatedDate"]
    assert dl.buttons == []


def test_parse_list_view_with_buttons_and_columns() -> None:
    raw = {
        "listViewAdditionalFields": ["Name", "Status__c"],
        "listViewButtons": ["New", "Delete"],
    }
    specs = search_layouts._parse_search_layouts(raw)
    lv = next(s for s in specs if s.layout_type == "List View")
    assert lv.columns == ["Name", "Status__c"]
    assert lv.buttons == ["New", "Delete"]


def test_parse_list_view_buttons_only() -> None:
    raw = {"listViewButtons": ["New"]}
    specs = search_layouts._parse_search_layouts(raw)
    lv = next(s for s in specs if s.layout_type == "List View")
    assert lv.buttons == ["New"]
    assert lv.columns == []


def test_parse_lookup_dialog_columns() -> None:
    raw = {"lookupDialogsAdditionalFields": ["Name", "AccountNumber"]}
    specs = search_layouts._parse_search_layouts(raw)
    ld = next(s for s in specs if s.layout_type == "Lookup Dialog")
    assert ld.columns == ["Name", "AccountNumber"]
    assert ld.buttons == []


def test_parse_search_filter_fields_columns() -> None:
    """searchFilterFields populate the 'Search Filter Fields' entry."""
    raw = {"searchFilterFields": ["Name", "Status__c"]}
    specs = search_layouts._parse_search_layouts(raw)
    sf = next(s for s in specs if s.layout_type == "Search Filter Fields")
    assert sf.columns == ["Name", "Status__c"]
    assert sf.buttons == []


def test_parse_tab_buttons() -> None:
    """tabOrderButtons populate the 'Tab' entry with no columns."""
    raw = {"tabOrderButtons": ["Submit"]}
    specs = search_layouts._parse_search_layouts(raw)
    tab = next(s for s in specs if s.layout_type == "Tab")
    assert tab.columns == []
    assert tab.buttons == ["Submit"]


def test_parse_search_filter_fields_and_tab_are_separate_rows() -> None:
    """searchFilterFields → 'Search Filter Fields'; tabOrderButtons → 'Tab'; distinct rows."""
    raw = {
        "searchFilterFields": ["Name"],
        "tabOrderButtons": ["Submit"],
    }
    specs = search_layouts._parse_search_layouts(raw)
    layout_types = [s.layout_type for s in specs]
    assert "Search Filter Fields" in layout_types
    assert "Tab" in layout_types
    sf = next(s for s in specs if s.layout_type == "Search Filter Fields")
    assert sf.columns == ["Name"]
    tab = next(s for s in specs if s.layout_type == "Tab")
    assert tab.buttons == ["Submit"]
    assert tab.columns == []


def test_parse_all_layout_types_all_populated() -> None:
    """All six rows populated when every key is present."""
    raw = {
        "searchResultsAdditionalFields": ["Name"],
        "listViewAdditionalFields": ["Name", "Owner"],
        "listViewButtons": ["New"],
        "lookupDialogsAdditionalFields": ["Name"],
        "lookupPhoneDialogsAdditionalFields": ["Name", "Phone"],
        "searchFilterFields": ["Name"],
        "tabOrderButtons": ["Submit"],
    }
    specs = search_layouts._parse_search_layouts(raw)
    assert [s.layout_type for s in specs] == ALL_LAYOUT_TYPES

    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns == ["Name"]

    lv = next(s for s in specs if s.layout_type == "List View")
    assert lv.columns == ["Name", "Owner"]
    assert lv.buttons == ["New"]

    ld = next(s for s in specs if s.layout_type == "Lookup Dialog")
    assert ld.columns == ["Name"]

    lpd = next(s for s in specs if s.layout_type == "Lookup Phone Dialogs")
    assert lpd.columns == ["Name", "Phone"]
    assert lpd.buttons == []

    sf = next(s for s in specs if s.layout_type == "Search Filter Fields")
    assert sf.columns == ["Name"]

    tab = next(s for s in specs if s.layout_type == "Tab")
    assert tab.buttons == ["Submit"]
    assert tab.columns == []


def test_parse_list_view_custom_buttons_merged() -> None:
    """customButtons are merged into List View buttons without duplicates."""
    raw = {
        "listViewButtons": ["New", "Delete"],
        "customButtons": ["Printable_View", "Delete"],  # Delete is a dupe
    }
    specs = search_layouts._parse_search_layouts(raw)
    lv = next(s for s in specs if s.layout_type == "List View")
    assert lv.buttons == ["New", "Delete", "Printable_View"]


def test_parse_list_view_custom_buttons_only() -> None:
    """customButtons alone (no listViewButtons) populate List View buttons."""
    raw = {"customButtons": ["Assign_Label"]}
    specs = search_layouts._parse_search_layouts(raw)
    lv = next(s for s in specs if s.layout_type == "List View")
    assert lv.buttons == ["Assign_Label"]
    assert lv.columns == []


def test_parse_single_string_value_treated_as_list() -> None:
    """Metadata API can return a bare string instead of a list when there is
    only one value — _as_list must handle that gracefully."""
    raw = {"searchResultsAdditionalFields": "Name"}  # single string, not a list
    specs = search_layouts._parse_search_layouts(raw)
    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns == ["Name"]


# ---------------------------------------------------------------------------
# Lookup Phone Dialogs
# ---------------------------------------------------------------------------


def test_parse_lookup_phone_dialogs_columns() -> None:
    """lookupPhoneDialogsAdditionalFields produces a 'Lookup Phone Dialogs' entry."""
    raw = {"lookupPhoneDialogsAdditionalFields": ["Name", "Phone"]}
    specs = search_layouts._parse_search_layouts(raw)
    lpd = next(s for s in specs if s.layout_type == "Lookup Phone Dialogs")
    assert lpd.columns == ["Name", "Phone"]
    assert lpd.buttons == []


def test_parse_lookup_phone_dialogs_single_string() -> None:
    """A bare string (single field) from the Metadata API is handled gracefully."""
    raw = {"lookupPhoneDialogsAdditionalFields": "Phone"}
    specs = search_layouts._parse_search_layouts(raw)
    lpd = next(s for s in specs if s.layout_type == "Lookup Phone Dialogs")
    assert lpd.columns == ["Phone"]


def test_parse_lookup_phone_dialogs_absent_row_still_emitted() -> None:
    """When lookupPhoneDialogsAdditionalFields is absent the row is still emitted (empty)."""
    raw = {"lookupDialogsAdditionalFields": ["Name"]}
    specs = search_layouts._parse_search_layouts(raw)
    layout_types = [s.layout_type for s in specs]
    assert "Lookup Phone Dialogs" in layout_types
    lpd = next(s for s in specs if s.layout_type == "Lookup Phone Dialogs")
    assert lpd.columns == []


# ---------------------------------------------------------------------------
# Default Layout — implicit Name column prepend (WI-07)
# ---------------------------------------------------------------------------


def test_default_layout_name_prepended_when_object_api_name_given() -> None:
    """When object_api_name is supplied the Name field is prepended to Default Layout
    columns, because Salesforce omits the implicit Name column from the API payload."""
    raw = {"searchResultsAdditionalFields": ["CreatedDate", "Status__c"]}
    specs = search_layouts._parse_search_layouts(raw, object_api_name="MyObject__c")
    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns[0] == "Name"
    assert dl.columns == ["Name", "CreatedDate", "Status__c"]


def test_default_layout_no_name_prepend_without_object_api_name() -> None:
    """Without object_api_name the columns are returned as-is (backward compat)."""
    raw = {"searchResultsAdditionalFields": ["CreatedDate", "Status__c"]}
    specs = search_layouts._parse_search_layouts(raw)
    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns == ["CreatedDate", "Status__c"]


def test_default_layout_name_not_duplicated_when_already_present() -> None:
    """If 'Name' already appears in searchResultsAdditionalFields it is not added again."""
    raw = {"searchResultsAdditionalFields": ["Name", "CreatedDate"]}
    specs = search_layouts._parse_search_layouts(raw, object_api_name="Account")
    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns == ["Name", "CreatedDate"]
    assert dl.columns.count("Name") == 1


def test_default_layout_name_prepended_for_empty_additional_fields() -> None:
    """With object_api_name and no additional fields, we still get ['Name']."""
    raw = {"searchResultsAdditionalFields": []}
    specs = search_layouts._parse_search_layouts(raw, object_api_name="Account")
    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns == ["Name"]


def test_default_layout_empty_when_key_absent_and_no_object_api_name() -> None:
    """Without object_api_name and no key, Default Layout row has empty columns."""
    specs = search_layouts._parse_search_layouts({})
    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns == []


# ---------------------------------------------------------------------------
# Integration-style tests for the async fetch() function
# ---------------------------------------------------------------------------


def test_fetch_parses_custom_object_search_layouts() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Account",
                "searchLayouts": {
                    "searchResultsAdditionalFields": ["Name", "Phone"],
                    "listViewAdditionalFields": ["Name"],
                    "listViewButtons": ["New", "Delete"],
                    "lookupDialogsAdditionalFields": ["Name", "Site"],
                    "searchFilterFields": ["Name", "Status__c"],
                    "tabOrderButtons": ["Submit"],
                },
            }
        ]
    )
    specs = _run(search_layouts.fetch(client, "Account"))

    assert len(specs) == 6
    layout_types = [s.layout_type for s in specs]
    assert layout_types == ALL_LAYOUT_TYPES

    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns == ["Name", "Phone"]
    assert dl.buttons == []

    lv = next(s for s in specs if s.layout_type == "List View")
    assert lv.columns == ["Name"]
    assert lv.buttons == ["New", "Delete"]

    ld = next(s for s in specs if s.layout_type == "Lookup Dialog")
    assert ld.columns == ["Name", "Site"]

    sf = next(s for s in specs if s.layout_type == "Search Filter Fields")
    assert sf.columns == ["Name", "Status__c"]
    assert sf.buttons == []

    tab = next(s for s in specs if s.layout_type == "Tab")
    assert tab.columns == []
    assert tab.buttons == ["Submit"]


def test_fetch_returns_empty_when_no_search_layouts_key() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[{"fullName": "Account"}]  # no searchLayouts key
    )
    specs = _run(search_layouts.fetch(client, "Account"))
    assert specs == []


def test_fetch_returns_empty_on_metadata_error() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(side_effect=RuntimeError("SOAP fault"))
    assert _run(search_layouts.fetch(client, "Account")) == []


def test_fetch_returns_empty_on_empty_records() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(return_value=[])
    assert _run(search_layouts.fetch(client, "Account")) == []


def test_fetch_skips_non_dict_records() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(return_value=[None, "unexpected"])
    assert _run(search_layouts.fetch(client, "Account")) == []


def test_fetch_all_six_rows_when_only_some_keys_present() -> None:
    """fetch() always returns 6 rows even when only some keys appear in the payload."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Case",
                "searchLayouts": {
                    "searchResultsAdditionalFields": ["CaseNumber"],
                    # listViewAdditionalFields absent
                    # lookupDialogsAdditionalFields absent
                    # lookupPhoneDialogsAdditionalFields absent
                    # searchFilterFields absent
                    # tabOrderButtons absent
                },
            }
        ]
    )
    specs = _run(search_layouts.fetch(client, "Case"))
    assert len(specs) == 6
    layout_types = [s.layout_type for s in specs]
    assert layout_types == ALL_LAYOUT_TYPES

    sf = next(s for s in specs if s.layout_type == "Search Filter Fields")
    assert sf.columns == []
    tab = next(s for s in specs if s.layout_type == "Tab")
    assert tab.buttons == []
    assert tab.columns == []


def test_fetch_default_layout_prepends_name() -> None:
    """fetch() passes object_api_name into the parser so Default Layout gets Name first."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Change_Control__c",
                "searchLayouts": {
                    "searchResultsAdditionalFields": ["CreatedDate", "Owner"],
                },
            }
        ]
    )
    specs = _run(search_layouts.fetch(client, "Change_Control__c"))
    dl = next(s for s in specs if s.layout_type == "Default Layout")
    assert dl.columns[0] == "Name"
    assert dl.columns == ["Name", "CreatedDate", "Owner"]


def test_fetch_includes_lookup_phone_dialogs() -> None:
    """fetch() surfaces Lookup Phone Dialogs from the CustomObject payload."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Contact",
                "searchLayouts": {
                    "lookupPhoneDialogsAdditionalFields": ["Name", "Phone", "MobilePhone"],
                },
            }
        ]
    )
    specs = _run(search_layouts.fetch(client, "Contact"))
    lpd = next(s for s in specs if s.layout_type == "Lookup Phone Dialogs")
    assert lpd.columns == ["Name", "Phone", "MobilePhone"]
    assert lpd.buttons == []
    # All six rows must still be present
    assert len(specs) == 6
    assert [s.layout_type for s in specs] == ALL_LAYOUT_TYPES
