"""Object-level general info and history-tracked field detection."""

from __future__ import annotations

from typing import Any

from ..client import SalesforceClient
from ..models import ObjectGeneralInfo


async def fetch_general(client: SalesforceClient, object_api_name: str) -> ObjectGeneralInfo:
    version = client.creds.api_version
    payload: dict[str, Any] = await client.rest_get(
        f"/services/data/v{version}/sobjects/{object_api_name}"
    )
    obj = payload.get("objectDescribe", payload)
    describe = await client.describe(object_api_name)

    # Authoritative source for field-history tracking is the CustomObject metadata
    # ``enableHistory`` flag.  ``hasSubtypes`` indicates the object has record types /
    # subtypes and must NOT be used for history tracking.  Fall back to the describe
    # ``trackHistory`` flag only when the metadata call fails.
    history_tracking_enabled: bool = bool(describe.get("trackHistory"))
    try:
        custom_obj_records = await client.read_metadata("CustomObject", [object_api_name])
        if custom_obj_records:
            raw = custom_obj_records[0]
            enable_history = raw.get("enableHistory")
            if enable_history is not None:
                history_tracking_enabled = bool(enable_history)
    except Exception:
        pass  # tolerate; fall back to describe trackHistory already set above

    return ObjectGeneralInfo(
        api_name=obj.get("name") or object_api_name,
        label=obj.get("label") or object_api_name,
        plural_label=obj.get("labelPlural") or object_api_name,
        description=describe.get("description"),
        sharing_model=describe.get("sharingModel"),
        history_tracking_enabled=history_tracking_enabled,
        # G-1: "Extended History in Custom Settings" cannot be determined from standard
        # Salesforce metadata APIs.  The legacy tool (Ctrl_CMP_Configuration_Report.cls
        # ::isExtendedHistory) reads this flag from a *DotCompliance-specific* Custom
        # Setting record (CompSuite__EnvironmentSettings__c.Dot_Compliance_Extended_History)
        # via DataAPIController.getEnvironment_Settings().  That object is not part of the
        # standard describe/REST surface, so we cannot populate it here without a bespoke
        # SOQL query against a managed-package field that may not exist in every org.
        # Left None until a dedicated collector for DotCompliance custom settings is added.
        custom_settings_extended_history=None,
    )


async def fetch_history_tracked_fields(
    client: SalesforceClient, object_api_name: str
) -> set[str]:
    soql = (
        "SELECT DeveloperName FROM FieldDefinition "
        f"WHERE EntityDefinition.QualifiedApiName = '{object_api_name}' "
        "AND IsFieldHistoryTracked = true"
    )
    try:
        result = await client.tooling_query(soql)
    except Exception:
        return set()
    return {r["DeveloperName"] for r in result.get("records", []) if r.get("DeveloperName")}
