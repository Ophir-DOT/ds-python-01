"""Page layout content (sections, fields, buttons, related lists) via Metadata API.

For each layout belonging to `object_api_name`, calls:
  1. ``list_metadata("Layout")`` to discover full names of the form
     ``<Object>-<Layout Name>``.
  2. ``read_metadata("Layout", full_names)`` to fetch the full schema.

Populates §5.10 of the design spec (WI-11).

Reference: ``Ctrl_CMP_Configuration_Report.cls:1209``.
"""

from __future__ import annotations

from typing import Any

from ..client import SalesforceClient
from ..models import LayoutFieldSpec, LayoutSectionSpec, PageLayoutSpec, RelatedListSpec


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# Standard record-detail buttons a layout shows by default, in display order.
# The Layout metadata does NOT list these; instead it lists the ones to HIDE in
# `excludeButtons`. So the visible standard buttons = this set MINUS excludeButtons.
# (internal API name → friendly label.) Mirrors Ctrl_CMP_Configuration_Report.cls:1266.
_STANDARD_LAYOUT_BUTTONS: tuple[tuple[str, str], ...] = (
    ("Edit", "Edit"),
    ("Submit", "Submit"),
    ("Clone", "Clone"),
    ("Delete", "Delete"),
    ("ChangeOwnerOne", "Change Owner"),
    ("ChangeRecordType", "Change Record Type"),
    ("PrintableView", "Printable View"),
)


def _standard_buttons(raw: dict[str, Any]) -> list[str]:
    """Visible standard buttons = the default set minus the layout's excludeButtons."""
    excluded = {b for b in _as_list(raw.get("excludeButtons")) if isinstance(b, str)}
    return [label for internal, label in _STANDARD_LAYOUT_BUTTONS if internal not in excluded]


def _mobile_lightning_actions(raw: dict[str, Any]) -> list[str]:
    """All actions from platformActionList — the Salesforce Mobile & Lightning Experience
    Actions panel. (Every platformActionListItem is an action, regardless of context.)
    """
    actions: list[str] = []
    for plist in _as_list(raw.get("platformActionList")):
        if not isinstance(plist, dict):
            continue
        for item in _as_list(plist.get("platformActionListItems")):
            if not isinstance(item, dict):
                continue
            action = item.get("actionName") or item.get("subtype") or ""
            if action and action not in actions:
                actions.append(action)
    return actions


def _column_letter(col_index: int) -> str:
    """Return 'L' for column 0, 'R' for column 1, then 'C', 'D', …"""
    letters = ["L", "R", "C", "D", "E"]
    if col_index < len(letters):
        return letters[col_index]
    return str(col_index + 1)


def _parse_sections(raw_sections: list[Any]) -> list[LayoutSectionSpec]:
    sections: list[LayoutSectionSpec] = []
    for section in raw_sections:
        if not isinstance(section, dict):
            continue
        label: str | None = section.get("label")
        columns_raw = _as_list(section.get("layoutColumns"))
        num_cols = len(columns_raw) if columns_raw else None
        fields: list[LayoutFieldSpec] = []
        for col_index, col in enumerate(columns_raw):
            if not isinstance(col, dict):
                continue
            items = _as_list(col.get("layoutItems"))
            row_num = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Skip blank spacers
                if item.get("emptySpace"):
                    row_num += 1
                    continue
                field_name: str | None = item.get("field")
                if not field_name:
                    row_num += 1
                    continue
                col_letter = _column_letter(col_index)
                position = f"{row_num + 1}{col_letter}"
                behavior: str | None = item.get("behavior")
                fields.append(
                    LayoutFieldSpec(
                        label=field_name,
                        position=position,
                        behavior=behavior,
                    )
                )
                row_num += 1
        sections.append(
            LayoutSectionSpec(
                label=label,
                columns=num_cols,
                fields=fields,
            )
        )
    return sections


def _parse_related_lists(raw_related_lists: list[Any]) -> list[RelatedListSpec]:
    result: list[RelatedListSpec] = []
    for rl in raw_related_lists:
        if not isinstance(rl, dict):
            continue
        name: str | None = rl.get("relatedList")
        if not name:
            continue
        # fields[] is a list of field API-name strings
        fields = [f for f in _as_list(rl.get("fields")) if isinstance(f, str)]
        # buttons[] may be a list of strings; customButtons is another key
        buttons = [b for b in _as_list(rl.get("customButtons")) if isinstance(b, str)]
        result.append(RelatedListSpec(name=name, fields=fields, buttons=buttons))
    return result


def _parse_layout(raw: dict[str, Any]) -> PageLayoutSpec | None:
    full_name: str | None = raw.get("fullName")
    if not full_name:
        return None

    sections = _parse_sections(_as_list(raw.get("layoutSections")))

    # Standard buttons: the default record-detail button set minus `excludeButtons`
    # (the Layout metadata lists what to HIDE, not what to show).
    standard_buttons = _standard_buttons(raw)

    # Custom buttons: top-level list of strings (web links / quick actions on the button bar).
    custom_buttons = [b for b in _as_list(raw.get("customButtons")) if isinstance(b, str)]

    # Mobile & Lightning Experience actions: the whole platformActionList.
    mobile_actions = _mobile_lightning_actions(raw)

    related_lists = _parse_related_lists(_as_list(raw.get("relatedLists")))

    return PageLayoutSpec(
        api_name=full_name,
        sections=sections,
        standard_buttons=standard_buttons,
        custom_buttons=custom_buttons,
        mobile_actions=mobile_actions,
        related_lists=related_lists,
    )


async def fetch(client: SalesforceClient, object_api_name: str) -> list[PageLayoutSpec]:
    """Return all page layouts for *object_api_name*, or [] on any error."""
    # Discover layout full names that belong to this object.
    prefix = f"{object_api_name}-"
    try:
        all_layouts = await client.list_metadata("Layout")
    except Exception:
        return []

    full_names = [
        entry["fullName"]
        for entry in all_layouts
        if isinstance(entry, dict) and entry.get("fullName", "").startswith(prefix)
    ]
    if not full_names:
        return []

    try:
        records = await client.read_metadata("Layout", full_names)
    except Exception:
        return []

    specs: list[PageLayoutSpec] = []
    for raw in records:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_layout(raw)
        if parsed is not None:
            specs.append(parsed)
    return specs
