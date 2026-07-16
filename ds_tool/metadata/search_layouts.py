"""Search layouts via the CustomObject Metadata API.

`readMetadata("CustomObject", [<object>])` returns the full CustomObject
definition; the `searchLayouts` child holds field lists for the standard
layout types (Default Layout / search results, List View, Lookup Dialog,
Lookup Phone Dialogs, Search Filter Fields, Tab).

Reference: `Ctrl_CMP_Configuration_Report.cls:3525-3597`.
"""

from __future__ import annotations

from typing import Any

from ..client import SalesforceClient
from ..models import SearchLayoutSpec


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_search_layouts(
    raw_layouts: dict[str, Any],
    object_api_name: str = "",
) -> list[SearchLayoutSpec]:
    """Turn the `searchLayouts` dict from a CustomObject record into typed specs.

    Salesforce CustomObject.searchLayouts keys and their meaning:
      searchResultsAdditionalFields     → "Default Layout" columns
      listViewAdditionalFields          → "List View" columns
      listViewButtons                   → "List View" buttons (standard SF buttons)
      customButtons                     → "List View" buttons (custom buttons, merged)
      lookupDialogsAdditionalFields     → "Lookup Dialog" columns
      lookupPhoneDialogsAdditionalFields→ "Lookup Phone Dialogs" columns
      searchFilterFields                → "Search Filter Fields" columns (filter-panel fields)
      tabOrderButtons                   → "Tab" buttons

    Note on Default Layout: Salesforce stores only the *additional* columns in
    `searchResultsAdditionalFields`; the object's Name field is always the
    implicit first column and is therefore absent from the API payload.  When
    `object_api_name` is provided we prepend "Name" (the universal standard
    label for the Name field) so the rendered row faithfully reflects what
    users see in Setup → Search Layouts → Default Layout.

    All six layout-type rows are ALWAYS emitted (with empty column/button lists
    when the key is absent or empty), matching the classic Search Layouts table
    in Salesforce Setup which lists all row types regardless of configuration.
    """
    # --- Default Layout (search-results columns) ---
    _default_raw = raw_layouts.get("searchResultsAdditionalFields")
    default_columns = [f for f in _as_list(_default_raw) if f]
    # The Name field is the implicit first column of the Default Layout;
    # Salesforce omits it from searchResultsAdditionalFields entirely.
    # Prepend "Name" when we know which object this layout belongs to, and
    # only when the key was explicitly present in the payload (even if empty),
    # and only if "Name" is not already listed (guarding against future API changes).
    if object_api_name and _default_raw is not None and "Name" not in default_columns:
        default_columns = ["Name"] + default_columns

    # --- List View (columns + Classic buttons from listViewButtons / customButtons) ---
    list_view_buttons = [
        b for b in _as_list(raw_layouts.get("listViewButtons")) if b
    ]
    # customButtons may carry additional Classic button names; merge without duplicates.
    for b in _as_list(raw_layouts.get("customButtons")):
        if b and b not in list_view_buttons:
            list_view_buttons.append(b)
    list_view_columns = [
        f for f in _as_list(raw_layouts.get("listViewAdditionalFields")) if f
    ]

    # --- Lookup Dialog ---
    lookup_columns = [
        f for f in _as_list(raw_layouts.get("lookupDialogsAdditionalFields")) if f
    ]

    # --- Lookup Phone Dialogs (phone-field lookup, classic telephony integration) ---
    lookup_phone_columns = [
        f for f in _as_list(raw_layouts.get("lookupPhoneDialogsAdditionalFields")) if f
    ]

    # --- Search Filter Fields (fields shown in the search-filter panel) ---
    search_filter_columns = [
        f for f in _as_list(raw_layouts.get("searchFilterFields")) if f
    ]

    # --- Tab (tab-order buttons only; no column list in the metadata) ---
    tab_buttons = [
        b for b in _as_list(raw_layouts.get("tabOrderButtons")) if b
    ]

    # Always emit all six rows so the §5.8 table shows a complete set of layout
    # types regardless of which keys are present in the API payload.  An absent
    # key simply produces an empty column / button list for that row.
    return [
        SearchLayoutSpec(layout_type="Default Layout", columns=default_columns),
        SearchLayoutSpec(layout_type="List View", columns=list_view_columns, buttons=list_view_buttons),
        SearchLayoutSpec(layout_type="Lookup Dialog", columns=lookup_columns),
        SearchLayoutSpec(layout_type="Lookup Phone Dialogs", columns=lookup_phone_columns),
        SearchLayoutSpec(layout_type="Search Filter Fields", columns=search_filter_columns),
        SearchLayoutSpec(layout_type="Tab", buttons=tab_buttons),
    ]


async def fetch(client: SalesforceClient, object_api_name: str) -> list[SearchLayoutSpec]:
    try:
        records = await client.read_metadata("CustomObject", [object_api_name])
    except Exception:
        return []

    specs: list[SearchLayoutSpec] = []
    for raw in records:
        if not isinstance(raw, dict):
            continue
        raw_layouts = raw.get("searchLayouts")
        if not isinstance(raw_layouts, dict):
            continue
        specs.extend(_parse_search_layouts(raw_layouts, object_api_name=object_api_name))

    return specs
