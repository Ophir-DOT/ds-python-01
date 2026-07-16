"""Apex triggers for one object via the Tooling API.

ApexTrigger's `TableEnumOrId` is set to the object's API name for custom and
standard objects alike (despite the column type being string/Id), so we can
filter directly. The `Usage*` booleans collapse to a friendlier "before insert",
"after update", … list for the rendered PDF.

Reference: `DataAPIController.cls:555` (`getTriggers`).
"""

from __future__ import annotations

from ..client import SalesforceClient
from ..models import ApexTriggerSpec

_USAGE_FIELDS: tuple[tuple[str, str], ...] = (
    ("UsageBeforeInsert", "before insert"),
    ("UsageBeforeUpdate", "before update"),
    ("UsageBeforeDelete", "before delete"),
    ("UsageAfterInsert", "after insert"),
    ("UsageAfterUpdate", "after update"),
    ("UsageAfterDelete", "after delete"),
    ("UsageAfterUndelete", "after undelete"),
)


def _events(record: dict) -> list[str]:
    return [label for column, label in _USAGE_FIELDS if record.get(column)]


def _classification(record: dict) -> str:
    """Return "Package" when the trigger belongs to a managed package, else "Custom"."""
    return "Package" if record.get("NamespacePrefix") else "Custom"


# Managed-package Apex bodies are not readable; the Tooling API returns the
# literal string "(hidden)" for Body and -1 for LengthWithoutComments.
_HIDDEN_BODY = "(hidden)"


def _code_length(record: dict) -> int | None:
    """Return LengthWithoutComments when known, falling back to len(Body).

    Managed packages report -1 (unreadable) — treated as unknown (None).
    """
    lwc = record.get("LengthWithoutComments")
    if lwc is not None:
        try:
            n = int(lwc)
            if n >= 0:
                return n
        except (TypeError, ValueError):
            pass
    body = record.get("Body")
    if isinstance(body, str) and body and body != _HIDDEN_BODY:
        return len(body)
    return None


def _source(record: dict) -> str | None:
    """The Apex body, or None when it is empty or a managed-package placeholder."""
    body = record.get("Body")
    if isinstance(body, str) and body and body != _HIDDEN_BODY:
        return body
    return None


async def fetch(client: SalesforceClient, object_api_name: str) -> list[ApexTriggerSpec]:
    columns = ", ".join(c for c, _ in _USAGE_FIELDS)
    soql = (
        f"SELECT Name, Status, ApiVersion, NamespacePrefix, "
        f"LengthWithoutComments, Body, {columns} "
        "FROM ApexTrigger "
        f"WHERE TableEnumOrId = '{object_api_name}' "
        "ORDER BY Name"
    )
    try:
        result = await client.tooling_query(soql)
    except Exception:
        return []

    specs: list[ApexTriggerSpec] = []
    for r in result.get("records", []):
        specs.append(
            ApexTriggerSpec(
                name=r.get("Name") or "",
                status=r.get("Status"),
                api_version=r.get("ApiVersion"),
                events=_events(r),
                classification=_classification(r),
                code_length=_code_length(r),
                source=_source(r),
            )
        )
    return specs
