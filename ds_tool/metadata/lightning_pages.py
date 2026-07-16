"""Lightning Page (FlexiPage) assignments for one object.

Two sources are merged so the rendered §3.5 table covers every assignment
mechanism Salesforce supports:

1. **Tooling FlexiPage SOQL** — enumerates every FlexiPage whose
   `EntityDefinition.QualifiedApiName` matches the object. Catches pages
   that exist for the object but have no CustomApplication override (org
   default / object-level activation).

2. **CustomApplication metadata** — walks each app's `actionOverrides[]`
   and `profileActionOverrides[]`. Catches app/profile/RT-level
   activations where `pageOrSobjectType == <object>` and `content` points
   at a FlexiPage.

For FlexiPages that appear in (1) but with no matching override in (2),
we emit a single "(default)" row so the page still shows up in the report.

Reference: `Ctrl_CMP_Configuration_Report.cls:1635-1700`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..client import SalesforceClient
from ..models import LightningPageAssignment


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _is_object_view(entry: dict[str, Any], object_api_name: str) -> bool:
    """Match a (profile)actionOverride row that targets a FlexiPage view of the object.

    The Metadata API normally emits `type=Flexipage`, but on some orgs the
    `type` element is omitted when the override is a FlexiPage. We accept
    either spelling and also fall back to the "content is set" + "object
    matches" heuristic so we don't drop legitimate FlexiPage assignments.
    """
    if entry.get("actionName") != "View":
        return False
    if entry.get("pageOrSobjectType") != object_api_name:
        return False
    if not entry.get("content"):
        return False
    type_value = entry.get("type")
    if type_value and type_value.lower() != "flexipage":
        return False
    return True


async def _list_object_flexipages(
    client: SalesforceClient, object_api_name: str
) -> dict[str, str]:
    """Return {DeveloperName: MasterLabel} for every RecordPage on the object."""
    soql = (
        "SELECT DeveloperName, MasterLabel "
        "FROM FlexiPage "
        f"WHERE EntityDefinition.QualifiedApiName = '{object_api_name}' "
        "AND Type = 'RecordPage'"
    )
    try:
        result = await client.tooling_query(soql)
    except Exception:
        return {}
    return {
        r["DeveloperName"]: r.get("MasterLabel") or r["DeveloperName"]
        for r in result.get("records", [])
        if r.get("DeveloperName")
    }


async def _read_all_apps(client: SalesforceClient) -> list[dict[str, Any]]:
    try:
        listing = await client.list_metadata("CustomApplication")
    except Exception:
        return []
    app_names = [
        r["fullName"]
        for r in listing
        if isinstance(r.get("fullName"), str) and r["fullName"]
    ]
    if not app_names:
        return []
    try:
        return await client.read_metadata("CustomApplication", app_names)
    except Exception:
        return []


async def fetch(
    client: SalesforceClient, object_api_name: str
) -> list[LightningPageAssignment]:
    object_flexipages, apps = await asyncio.gather(
        _list_object_flexipages(client, object_api_name),
        _read_all_apps(client),
    )

    assignments: list[LightningPageAssignment] = []
    seen_flexipages: set[str] = set()

    for app in apps:
        app_name = app.get("fullName") or app.get("label") or ""

        for ao in _as_list(app.get("actionOverrides")):
            if not isinstance(ao, dict) or not _is_object_view(ao, object_api_name):
                continue
            seen_flexipages.add(ao["content"])
            assignments.append(
                LightningPageAssignment(
                    app=app_name,
                    profile=None,
                    record_type=None,
                    form_factor=ao.get("formFactor") or "Large",
                    flexipage=ao["content"],
                )
            )

        for pao in _as_list(app.get("profileActionOverrides")):
            if not isinstance(pao, dict) or not _is_object_view(pao, object_api_name):
                continue
            rt = pao.get("recordType") or ""
            if "." in rt:
                rt = rt.split(".", 1)[1]
            seen_flexipages.add(pao["content"])
            assignments.append(
                LightningPageAssignment(
                    app=app_name,
                    profile=pao.get("profile"),
                    record_type=rt or None,
                    form_factor=pao.get("formFactor") or "Large",
                    flexipage=pao["content"],
                )
            )

    # Any FlexiPage that exists for this object but has no CustomApplication
    # override gets a stand-in row so the page still appears in the report.
    for dev_name in object_flexipages:
        if dev_name in seen_flexipages:
            continue
        assignments.append(
            LightningPageAssignment(
                app="(default / no app override)",
                profile=None,
                record_type=None,
                form_factor="Large",
                flexipage=dev_name,
            )
        )

    return assignments
