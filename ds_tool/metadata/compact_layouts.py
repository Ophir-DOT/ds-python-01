"""Compact layouts embedded in CustomObject metadata.

`readMetadata("CustomObject", [<object>])` returns the object definition;
the `compactLayouts[]` child holds CompactLayout definitions. Each entry has
{fullName, label, fields[]}.

Reference: `Ctrl_CMP_Configuration_Report.cls:330-340,1510-1535`.
"""

from __future__ import annotations

from typing import Any

from ..client import SalesforceClient
from ..models import CompactLayoutSpec


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


async def fetch(client: SalesforceClient, object_api_name: str) -> list[CompactLayoutSpec]:
    try:
        records = await client.read_metadata("CustomObject", [object_api_name])
    except Exception:
        return []

    specs: list[CompactLayoutSpec] = []
    for raw in records:
        for layout in _as_list(raw.get("compactLayouts")):
            if not isinstance(layout, dict):
                continue
            full_name = layout.get("fullName") or ""
            if not full_name:
                continue
            fields = [f for f in _as_list(layout.get("fields")) if isinstance(f, str) and f]
            specs.append(
                CompactLayoutSpec(
                    api_name=full_name,
                    label=layout.get("label"),
                    fields=fields,
                )
            )
    return specs
