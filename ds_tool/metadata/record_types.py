"""Record type metadata: standard SOQL for basics, Metadata API for picklist values.

Standard REST SOQL is used here (not Tooling) because the Tooling API's
RecordType entity does NOT expose `DeveloperName` as a column — the query
silently errors out, and the empty result cascaded into an empty §2.1.1
because the follow-up Metadata read never gets a full-name list to request.

Per-record-type picklist value lists live in the Metadata API
`RecordType.picklistValues[]` payload, so we follow up with
`readMetadata("RecordType", ["Object.RT1", ...])` to enrich each spec.

Mirrors `Ctrl_CMP_Configuration_Report.cls:1540` (`recordTypeToPickListMap`).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from ..client import SalesforceClient
from ..models import RecordTypeSpec


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_picklist_values(raw: dict[str, Any]) -> dict[str, list[str]]:
    """Pull `picklistValues[]` from a readMetadata RecordType response into a dict.

    Salesforce returns picklist value `fullName` as URL-percent-encoded
    identifiers (spaces → "+", "(" → "%28", "," → "%2C", "." → "%2E", etc.) so
    they can serve as XML/SF identifier-safe tokens. We decode back to the
    human-readable label for the PDF — that's what the SF setup UI shows.
    """
    out: dict[str, list[str]] = {}
    for entry in _as_list(raw.get("picklistValues")):
        if not isinstance(entry, dict):
            continue
        picklist = entry.get("picklist")
        if not picklist:
            continue
        values: list[str] = []
        for v in _as_list(entry.get("values")):
            if not isinstance(v, dict):
                continue
            name = v.get("fullName")
            if name:
                values.append(unquote(name))
        if values:
            out[picklist] = values
    return out


async def fetch(client: SalesforceClient, object_api_name: str) -> list[RecordTypeSpec]:
    # `BusinessProcess.Name` traversal isn't allowed via the standard REST SOQL
    # API on RecordType — including it returns HTTP 400 and the whole fetch
    # silently fell through to []. We project the BusinessProcessId only; if a
    # future caller needs the BusinessProcess label, resolve it with a second
    # query keyed on BusinessProcessId.
    soql = (
        "SELECT DeveloperName, Name, IsActive, Description, BusinessProcessId "
        "FROM RecordType "
        f"WHERE SobjectType = '{object_api_name}'"
    )
    try:
        result = await client.query(soql)
    except Exception:
        return []

    specs: list[RecordTypeSpec] = []
    for r in result.get("records", []):
        specs.append(
            RecordTypeSpec(
                api_name=r["DeveloperName"],
                label=r.get("Name") or r["DeveloperName"],
                active=bool(r.get("IsActive", True)),
                description=r.get("Description"),
                business_process=r.get("BusinessProcessId"),
            )
        )

    if not specs:
        return specs

    full_names = [f"{object_api_name}.{s.api_name}" for s in specs]
    try:
        raw_records = await client.read_metadata("RecordType", full_names)
    except Exception:
        # Picklist enrichment is best-effort; fall through with the bare specs.
        return specs

    by_devname: dict[str, dict[str, list[str]]] = {}
    for raw in raw_records:
        full_name = raw.get("fullName") or ""
        # "Object.RecordType" → "RecordType"
        devname = full_name.split(".", 1)[-1] if "." in full_name else full_name
        if not devname:
            continue
        by_devname[devname] = _parse_picklist_values(raw)

    enriched: list[RecordTypeSpec] = []
    for spec in specs:
        picklists = by_devname.get(spec.api_name)
        if picklists:
            enriched.append(spec.model_copy(update={"picklist_values": picklists}))
        else:
            enriched.append(spec)
    return enriched
