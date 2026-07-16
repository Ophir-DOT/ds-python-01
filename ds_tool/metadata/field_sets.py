"""Field sets defined on a CustomObject via the Metadata API.

`readMetadata("CustomObject", [<object>])` returns the object container;
the `fieldSets[]` child holds FieldSet definitions. Each field set has
fullName, label, description and displayedFields[] (each has `field`).

Reference: `Ctrl_CMP_Configuration_Report.cls` — grep "FieldSet".
"""

from __future__ import annotations

from typing import Any

from ..client import SalesforceClient
from ..models import FieldSetSpec


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


async def fetch(client: SalesforceClient, object_api_name: str) -> list[FieldSetSpec]:
    try:
        records = await client.read_metadata("CustomObject", [object_api_name])
    except Exception:
        return []

    specs: list[FieldSetSpec] = []
    for raw in records:
        for fs in _as_list(raw.get("fieldSets")):
            if not isinstance(fs, dict):
                continue
            full_name = fs.get("fullName") or ""
            if not full_name:
                continue
            fields = [
                entry["field"]
                for entry in _as_list(fs.get("displayedFields"))
                if isinstance(entry, dict) and entry.get("field")
            ]
            specs.append(
                FieldSetSpec(
                    api_name=full_name,
                    label=fs.get("label"),
                    description=fs.get("description"),
                    fields=fields,
                )
            )
    return specs
