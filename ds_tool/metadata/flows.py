"""Flow definitions via the regular Query API, filtered to the object.

`FlowDefinitionView` is a standard read-only entity (NOT a Tooling object), so it
must be queried through the normal query endpoint — querying it via the Tooling
API returns nothing. Record-triggered / autolaunched flows are linked to their
object through `TriggerObjectOrEventId`, which is the object's EntityDefinition
DurableId. This mirrors the legacy `DataAPIController.getFlows`
(`SELECT ... FROM FlowDefinitionView WHERE TriggerObjectOrEventId = '<durableId>'`).
"""

from __future__ import annotations

from ..client import SalesforceClient
from ..models import FlowSpec


async def object_durable_id(client: SalesforceClient, object_api_name: str) -> str | None:
    """EntityDefinition DurableId for an object — used to filter FlowDefinitionView.

    FlowDefinitionView.TriggerObjectOrEventId references EntityDefinition, whose
    DurableId (e.g. ``01I...`` for custom objects) is what flows are keyed on.
    """
    soql = (
        "SELECT DurableId FROM EntityDefinition "
        f"WHERE QualifiedApiName = '{object_api_name}'"
    )
    try:
        result = await client.query(soql)
    except Exception:
        return None
    records = result.get("records") or []
    return records[0].get("DurableId") if records else None


async def fetch(client: SalesforceClient, object_api_name: str) -> list[FlowSpec]:
    durable_id = await object_durable_id(client, object_api_name)
    if not durable_id:
        return []
    soql = (
        "SELECT ApiName, Label, ProcessType, IsActive, Description, ManageableState "
        "FROM FlowDefinitionView "
        f"WHERE TriggerObjectOrEventId = '{durable_id}'"
    )
    try:
        result = await client.query(soql)
    except Exception:
        return []
    specs: list[FlowSpec] = []
    for r in result.get("records", []):
        api_name = r.get("ApiName") or ""
        specs.append(
            FlowSpec(
                api_name=api_name,
                label=r.get("Label") or api_name,
                process_type=r.get("ProcessType"),
                status="Active" if r.get("IsActive") else "Inactive",
                description=r.get("Description"),
                package_state=_map_manageable_state(r.get("ManageableState")),
            )
        )
    return specs


_MANAGEABLE_STATE_MAP: dict[str, str] = {
    "unmanaged": "Unmanaged",
    "installed": "Managed - Installed",
    "installedEditable": "Managed - Installed (Editable)",
    "released": "Managed - Released",
    "deprecated": "Managed - Deprecated",
    "deprecatedEditable": "Managed - Deprecated (Editable)",
    "deleted": "Managed - Deleted",
}


def _map_manageable_state(raw: str | None) -> str | None:
    """Map the ManageableState API value to a human-readable label."""
    if raw is None:
        return None
    return _MANAGEABLE_STATE_MAP.get(raw, raw)
