"""Workflow Field Updates via the Workflow Metadata API.

`readMetadata("Workflow", [<object>])` returns the workflow container for that
object; the `fieldUpdates[]` child holds the WorkflowFieldUpdate definitions.

This mirrors ds_tool/metadata/email_alerts.py which reads the same Workflow
container's `alerts[]` child.

Reference: §5.3 Field Update Details (WI-10).
"""

from __future__ import annotations

from typing import Any

from ..client import SalesforceClient
from ..models import FieldUpdateSpec


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _bool_field(value: Any) -> bool | None:
    """Coerce a SOAP API boolean-ish value to Python bool, or None if absent."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


async def fetch(client: SalesforceClient, object_api_name: str) -> list[FieldUpdateSpec]:
    try:
        records = await client.read_metadata("Workflow", [object_api_name])
    except Exception:
        return []

    specs: list[FieldUpdateSpec] = []
    for raw in records:
        for fu in _as_list(raw.get("fieldUpdates")):
            if not isinstance(fu, dict):
                continue
            full_name = fu.get("fullName") or ""
            if not full_name:
                continue

            # Determine the value: literalValue takes precedence; fall back to formula.
            value: str | None = fu.get("literalValue") or fu.get("formula") or None

            specs.append(
                FieldUpdateSpec(
                    api_name=full_name,
                    name=fu.get("name"),
                    description=fu.get("description"),
                    field=fu.get("field"),
                    operation=fu.get("operation"),
                    value=value,
                    notify_assignee=_bool_field(fu.get("notifyAssignee")),
                    reevaluate_workflow_rules=_bool_field(fu.get("reevaluateOnChange")),
                )
            )
    return specs
