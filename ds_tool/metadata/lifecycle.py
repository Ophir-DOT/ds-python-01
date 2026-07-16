"""Life Cycle (legacy section 4) — CompSuite state transitions and approvals.

Mirrors `Ctrl_CMP_Configuration_Report.cls:2635-3022` and the SOQL queries in
`DataAPIController.cls:382-491`. Unlike most ds-tool collectors, this section's
data is NOT metadata — it lives in first-class custom objects from the CompSuite
managed package (`CompSuite__State__c`, `CompSuite__State_Transition__c`,
`CompSuite__Transition_Action__c`, `CompSuite__Approval_Process_Init__c`).

Sections 4.1 (general) and 4.3 (permissions) and 4.4 (auto-populate dates) all
project off the same Transition Action record set — fetched once per object.
Section 4.2 (approval process init) is a sibling SOQL.

The Apex tool unconditionally assumes CompSuite is installed; we don't. If the
first probing query fails with INVALID_TYPE / 404, we return an empty
`LifeCycleSpec(compsuite_installed=False)` so the template renders a graceful
"not applicable" placeholder rather than crashing the whole report.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from ..cache import ProfileCache
from ..client import SalesforceClient
from ..models import (
    LifeCycleApprovalProcessInit,
    LifeCycleAutoPopulateDate,
    LifeCyclePermission,
    LifeCycleSpec,
    LifeCycleTransition,
)

# Apex skips rows where the state-transition name is exactly this sentinel —
# it's the parent "umbrella" path that doesn't represent an actual transition.
# See Ctrl_CMP_Configuration_Report.cls:2654.
_LIFE_CYCLE_PATH_SENTINEL = "Life Cycle Path"


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _split_csv(value: str | None, delim: str = ",") -> list[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(delim) if p.strip()]


def _safe_get(d: Any, *path: str) -> Any:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


async def fetch(
    client: SalesforceClient,
    object_api_name: str,
    cache: ProfileCache,
) -> LifeCycleSpec:
    """Build a LifeCycleSpec for one sObject from CompSuite SOQL queries.

    Org-wide reference data (state IDs, group IDs, profile/permset IDs) is
    fetched once via the shared ProfileCache; subsequent objects reuse it.
    """
    # CompSuite presence check — cheap zero-row probe. INVALID_TYPE comes back
    # as a 400 from Salesforce; a wrong endpoint would be 404. Either means
    # the package isn't installed in this org.
    if not cache.has_aux("__compsuite_probe_done"):
        try:
            await client.query("SELECT Id FROM CompSuite__Transition_Action__c LIMIT 0")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404):
                cache.set_aux("__compsuite_probe_done", {"installed": "false"})
                return LifeCycleSpec(compsuite_installed=False)
            raise
        cache.set_aux("__compsuite_probe_done", {"installed": "true"})
    elif cache.aux_lookup("__compsuite_probe_done", "installed") == "false":
        return LifeCycleSpec(compsuite_installed=False)

    # Org-wide ID→Name maps (states + groups). Both are independent of the
    # object being collected, so this runs once per ds-tool invocation.
    await _populate_aux_maps(client, cache)

    # Per-object record sets — concurrent.
    object_literal = object_api_name.replace("'", "\\'")
    ta_soql = (
        "SELECT Id, "
        "CompSuite__Button_Style__c, CompSuite__Change_Fields__c, "
        "CompSuite__Date_Fields__c, CompSuite__Dependency_on_related_forms__c, "
        "CompSuite__Is_Need_E_Signature__c, CompSuite__Lock_Fields__c, "
        "CompSuite__Mandatory_Fields__c, CompSuite__PermissionSet_Permissions__c, "
        "CompSuite__Profile_Permissions__c, CompSuite__Skip_Approval_Process__c, "
        "CompSuite__State_Transition__r.Name, "
        "CompSuite__State_Transition__r.CompSuite__Index__c, "
        "CompSuite__State_Transition__r.CompSuite__Record_Type__c, "
        "CompSuite__State_Transition__r.CompSuite__Xact__c, "
        "CompSuite__State_Transition__r.CompSuite__Source__r.Name, "
        "CompSuite__State_Transition__r.CompSuite__Destination__r.Name "
        "FROM CompSuite__Transition_Action__c "
        "WHERE CompSuite__State_Transition__r.CompSuite__isDeleted__c = false "
        f"AND CompSuite__State_Transition__r.CompSuite__Object_Name__c = '{object_literal}' "
        "ORDER BY CompSuite__State_Transition__r.CompSuite__Record_Type__c, "
        "CompSuite__State_Transition__r.CompSuite__Index__c"
    )
    api_soql = (
        "SELECT Id, Name, CompSuite__Skip_Start_Action__c, "
        "CompSuite__Rejected_State__c, CompSuite__Manageable_States__c, "
        "CompSuite__Has_Last_Approval__c, CompSuite__Multiple_Users__c, "
        "CompSuite__Groups__c, CompSuite__Reject_Lock_Fields__c, "
        "CompSuite__Rejection_Email_Template__c, "
        "CompSuite__State_Transition__r.Name, "
        "CompSuite__State_Transition__r.CompSuite__Index__c, "
        "CompSuite__State_Transition__r.CompSuite__Record_Type__c "
        "FROM CompSuite__Approval_Process_Init__c "
        f"WHERE CompSuite__State_Transition__r.CompSuite__Object_Name__c = '{object_literal}' "
        "ORDER BY CompSuite__State_Transition__r.CompSuite__Record_Type__c, "
        "CompSuite__State_Transition__r.CompSuite__Index__c"
    )

    transition_records, approval_records = await asyncio.gather(
        client.query_all(ta_soql),
        client.query_all(api_soql),
    )

    # Lazy: only build the Profile/PermissionSet Id→Name map when we actually
    # have permissions to resolve. populate_profile_cache (the readMetadata path)
    # doesn't carry IDs, so we do a separate SOQL for the lookup.
    if not cache.has_id_map and transition_records:
        await _populate_profile_id_map(client, cache)

    # Email templates: scoped to the IDs actually referenced from approval inits,
    # not the whole org (which could be thousands).
    referenced_email_ids = {
        r.get("CompSuite__Rejection_Email_Template__c")
        for r in approval_records
        if r.get("CompSuite__Rejection_Email_Template__c")
    }
    referenced_email_ids.discard(None)
    if referenced_email_ids and not cache.has_aux("email_templates"):
        await _populate_email_templates(client, cache, referenced_email_ids)

    transitions, permissions, auto_dates, related_names = _project_transitions(
        transition_records, cache
    )
    approval_processes = _project_approval_inits(approval_records, cache)

    return LifeCycleSpec(
        compsuite_installed=True,
        transitions=transitions,
        approval_processes=approval_processes,
        permissions=permissions,
        auto_populate_dates=auto_dates,
        related_profile_names=related_names,
    )


def _project_transitions(
    records: list[dict[str, Any]], cache: ProfileCache
) -> tuple[
    list[LifeCycleTransition],
    list[LifeCyclePermission],
    list[LifeCycleAutoPopulateDate],
    list[str],
]:
    transitions: list[LifeCycleTransition] = []
    permissions: list[LifeCyclePermission] = []
    auto_dates: list[LifeCycleAutoPopulateDate] = []
    related_names: list[str] = []
    related_names_seen: set[str] = set()

    for r in records:
        st = r.get("CompSuite__State_Transition__r") or {}
        st_name = st.get("Name") or ""
        if st_name == _LIFE_CYCLE_PATH_SENTINEL:
            continue
        record_type = st.get("CompSuite__Record_Type__c") or None
        index = _to_int(st.get("CompSuite__Index__c"))
        source = _safe_get(st, "CompSuite__Source__r", "Name") or ""
        destination = _safe_get(st, "CompSuite__Destination__r", "Name") or ""

        # 4.1 — Lock fields can carry the special tokens "LockRecord" and
        # "LockAttachments" mixed in with field names. Apex strips
        # ",LockAttachments" and exposes that as a separate Yes/No column.
        # See Ctrl_CMP_Configuration_Report.cls:2679-2687.
        lock_raw = r.get("CompSuite__Lock_Fields__c") or ""
        lock_attachments = "LockAttachments" in lock_raw
        lock_clean = lock_raw.replace(",LockAttachments", "").rstrip(",")
        lock_clean = lock_clean or None

        mandatory_fields = _split_csv(r.get("CompSuite__Mandatory_Fields__c"))
        change_fields = _split_csv(r.get("CompSuite__Change_Fields__c"))

        dep_raw = r.get("CompSuite__Dependency_on_related_forms__c") or ""
        if dep_raw:
            dep = "Promote" if "Promote" in dep_raw else "Restrict"
        else:
            dep = None

        xact_raw = st.get("CompSuite__Xact__c")
        xact_val: bool | None = None
        if xact_raw not in (None, ""):
            xact_val = "true" in str(xact_raw).lower()

        transitions.append(
            LifeCycleTransition(
                transition_action_id=r["Id"],
                record_type=record_type,
                index=index,
                transition_label=st_name,
                source_state=source,
                destination_state=destination,
                button_style=r.get("CompSuite__Button_Style__c"),
                needs_e_signature=_to_bool(r.get("CompSuite__Is_Need_E_Signature__c")),
                lock_fields=lock_clean,
                lock_attachments=lock_attachments,
                mandatory_fields=mandatory_fields,
                skip_approval=_to_bool(r.get("CompSuite__Skip_Approval_Process__c")),
                change_fields=change_fields,
                dependency_on_related_forms=dep,
                xact=xact_val,
            )
        )

        # 4.3 — resolve profile + permset IDs to display names. Apex splits both
        # CSV fields on comma; see Ctrl_CMP_Configuration_Report.cls:2891,2897.
        profile_ids = _split_csv(r.get("CompSuite__Profile_Permissions__c"))
        permset_ids = _split_csv(r.get("CompSuite__PermissionSet_Permissions__c"))
        names_for_row = cache.resolve_ids(profile_ids + permset_ids)
        for n in names_for_row:
            if n not in related_names_seen:
                related_names_seen.add(n)
                related_names.append(n)
        permissions.append(
            LifeCyclePermission(
                transition_action_id=r["Id"],
                record_type=record_type,
                index=index,
                transition_label=st_name,
                profile_or_permset_names=names_for_row,
            )
        )

        # 4.4 — Date_Fields is a JSON list of {fieldName, avoidOverride}.
        # See Ctrl_CMP_Configuration_Report.cls:2981.
        dates_raw = r.get("CompSuite__Date_Fields__c")
        if dates_raw:
            fields_for_row = _parse_date_fields(dates_raw)
            if fields_for_row:
                auto_dates.append(
                    LifeCycleAutoPopulateDate(
                        transition_action_id=r["Id"],
                        record_type=record_type,
                        index=index,
                        transition_label=st_name,
                        source_state=source,
                        destination_state=destination,
                        fields=fields_for_row,
                    )
                )

    return transitions, permissions, auto_dates, related_names


def _parse_date_fields(raw: str) -> list[tuple[str, bool]]:
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    out: list[tuple[str, bool]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        field_name = item.get("fieldName")
        if not isinstance(field_name, str) or not field_name:
            continue
        avoid = bool(item.get("avoidOverride"))
        out.append((field_name, avoid))
    return out


def _project_approval_inits(
    records: list[dict[str, Any]], cache: ProfileCache
) -> list[LifeCycleApprovalProcessInit]:
    out: list[LifeCycleApprovalProcessInit] = []
    for r in records:
        st = r.get("CompSuite__State_Transition__r") or {}
        st_name = st.get("Name") or ""
        if st_name == _LIFE_CYCLE_PATH_SENTINEL:
            continue
        record_type = st.get("CompSuite__Record_Type__c") or None
        index = _to_int(st.get("CompSuite__Index__c"))

        rs_id = r.get("CompSuite__Rejected_State__c")
        rejected_state = cache.aux_lookup("states", rs_id) if rs_id else None
        if rs_id and not rejected_state:
            # Fall back to the raw Id so a missing map entry doesn't drop data.
            rejected_state = rs_id

        manageable: list[str] = []
        ms = r.get("CompSuite__Manageable_States__c")
        if ms:
            for sid in _split_csv(ms):
                resolved = cache.aux_lookup("states", sid)
                manageable.append(resolved or sid)

        approver_filters: str | None = None
        groups = r.get("CompSuite__Groups__c")
        if groups:
            # Apex splits on ';' here, not ',' — DataAPIController & Ctrl_CMP at line 2837.
            names: list[str] = []
            for gid in _split_csv(groups, ";"):
                names.append(cache.aux_lookup("groups", gid) or gid)
            approver_filters = ", ".join(names) or None

        rej_template_id = r.get("CompSuite__Rejection_Email_Template__c")
        rejection_template: str | None = None
        if rej_template_id:
            rejection_template = (
                cache.aux_lookup("email_templates", rej_template_id) or rej_template_id
            )

        reject_lock = r.get("CompSuite__Reject_Lock_Fields__c")
        if reject_lock:
            reject_lock = reject_lock.rstrip(",")

        out.append(
            LifeCycleApprovalProcessInit(
                transition_action_id=r["Id"],
                record_type=record_type,
                index=index,
                transition_label=st_name,
                name=r.get("Name") or "",
                skip_start_action=_to_bool(r.get("CompSuite__Skip_Start_Action__c")),
                rejected_state=rejected_state,
                manageable_states=manageable,
                has_last_approval=_to_bool(r.get("CompSuite__Has_Last_Approval__c")),
                minimum_approvers=_to_int(r.get("CompSuite__Multiple_Users__c")),
                reject_lock_fields=reject_lock,
                approver_filters=approver_filters,
                rejection_email_template=rejection_template,
            )
        )
    return out


async def _populate_aux_maps(client: SalesforceClient, cache: ProfileCache) -> None:
    tasks: list = []
    if not cache.has_aux("states"):
        tasks.append(_load_states(client, cache))
    if not cache.has_aux("groups"):
        tasks.append(_load_groups(client, cache))
    if tasks:
        await asyncio.gather(*tasks)


async def _load_states(client: SalesforceClient, cache: ProfileCache) -> None:
    records = await client.query_all("SELECT Id, Name FROM CompSuite__State__c")
    cache.set_aux(
        "states", {r["Id"]: r.get("Name") for r in records if r.get("Id") and r.get("Name")}
    )


async def _load_groups(client: SalesforceClient, cache: ProfileCache) -> None:
    # Mirrors DataAPIController.cls:398 — Type='Regular' filters out the auto-
    # generated role/territory groups; we want shareable public groups only.
    records = await client.query_all(
        "SELECT Id, Name, DeveloperName FROM Group "
        "WHERE Type = 'Regular' ORDER BY DeveloperName LIMIT 1000"
    )
    cache.set_aux(
        "groups",
        {
            r["Id"]: (r.get("DeveloperName") or r.get("Name"))
            for r in records
            if r.get("Id")
        },
    )


async def _populate_email_templates(
    client: SalesforceClient, cache: ProfileCache, ids: set
) -> None:
    quoted = ",".join(f"'{i}'" for i in ids if i)
    if not quoted:
        return
    records = await client.query_all(
        f"SELECT Id, Name FROM EmailTemplate WHERE Id IN ({quoted})"
    )
    cache.set_aux(
        "email_templates",
        {r["Id"]: r.get("Name") for r in records if r.get("Id") and r.get("Name")},
    )


async def _populate_profile_id_map(client: SalesforceClient, cache: ProfileCache) -> None:
    """Build a Profile + PermissionSet Id→Name map for 4.3 row resolution.

    populate_profile_cache (the readMetadata path used by profiles.py) only
    keys on name, not Id. The Transition Action records reference profiles and
    permsets by Id in CSV columns, so we do a one-time SOQL lookup here that
    spans both record types.
    """
    profile_records, permset_records = await asyncio.gather(
        client.query_all("SELECT Id, Name FROM Profile"),
        client.query_all(
            "SELECT Id, Name FROM PermissionSet WHERE IsOwnedByProfile = false"
        ),
    )
    merged: dict[str, str] = {}
    for r in profile_records:
        if r.get("Id") and r.get("Name"):
            merged[r["Id"]] = r["Name"]
    for r in permset_records:
        if r.get("Id") and r.get("Name"):
            merged[r["Id"]] = r["Name"]
    cache.set_id_to_name(merged)
