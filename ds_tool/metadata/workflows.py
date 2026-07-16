"""Workflow rules via the Tooling API."""

from __future__ import annotations

from ..client import SalesforceClient
from ..models import WorkflowRuleSpec


async def fetch(client: SalesforceClient, object_api_name: str) -> list[WorkflowRuleSpec]:
    soql = (
        "SELECT Name, TableEnumOrId, Metadata "
        "FROM WorkflowRule "
        f"WHERE TableEnumOrId = '{object_api_name}'"
    )
    try:
        result = await client.tooling_query(soql)
    except Exception:
        return []
    specs: list[WorkflowRuleSpec] = []
    for r in result.get("records", []):
        metadata = r.get("Metadata") or {}
        criteria_items = metadata.get("criteriaItems") or []
        criteria = "; ".join(
            f"{c.get('field', '')} {c.get('operation', '')} {c.get('value', '')}"
            for c in criteria_items
        )
        specs.append(
            WorkflowRuleSpec(
                api_name=r["Name"],
                active=bool(metadata.get("active", True)),
                description=metadata.get("description"),
                trigger_type=metadata.get("triggerType"),
                criteria=criteria or metadata.get("formula"),
            )
        )
    return specs
