"""Single-pass Profile + PermissionSet fetcher.

This is the module that resolves the two biggest user pain points:
  - Performance: Profile/PermissionSet metadata is read ONCE per ds-tool run.
  - Multi-run requirement: a single fetch is filtered per-object via ProfileCache,
    so users no longer re-run for each (object, permission-set) combination.
"""

from __future__ import annotations

import asyncio
from typing import Any, Iterable

from ..client import SalesforceClient
from ..models import (
    FieldPermission,
    LayoutAssignmentEntry,
    ObjectPermission,
    ProfileSpec,
)

# Standard profile labels (UI names) → Metadata API fullName.
# Mirrors `standardProfileMap` in Ctrl_CMP_Configuration_Report.cls (~line 35).
# readMetadata('Profile', [...]) expects the fullName; passing the label silently
# returns an empty result, which is what manifested as the empty permissions table.
STANDARD_PROFILE_LABEL_TO_FULLNAME: dict[str, str] = {
    "System Administrator": "Admin",
    "Standard User": "Standard",
    "Standard Platform User": "StandardAul",
    "Read Only": "ReadOnly",
    "Solution Manager": "SolutionManager",
    "Marketing User": "MarketingProfile",
    "Contract Manager": "ContractManager",
    "Chatter Free User": "Chatter Free User",
    "Chatter External User": "Chatter External User",
    "Chatter Moderator User": "ChatterModerator",
    "Customer Community User": "Customer Community User",
    "Customer Community Login User": "Customer Community Login User",
    "Customer Community Plus User": "Customer Community Plus User",
    "Customer Community Plus Login User": "Customer Community Plus Login User",
    "Partner Community User": "Partner Community User",
    "Partner Community Login User": "Partner Community Login User",
    "High Volume Customer Portal User": "HighVolumePortal",
    "Authenticated Website": "Authenticated Website",
    "Cross Org Data Proxy User": "CrossOrgDataProxy",
    "Force.com - Free User": "Force.com - Free User",
    "Force.com - App Subscription User": "Force.com - App Subscription User",
    "Identity User": "Identity User",
    "Work.com Only User": "Work.com Only User",
    "Analytics Cloud Integration User": "Analytics Cloud Integration User",
    "Analytics Cloud Security User": "Analytics Cloud Security User",
    "Minimum Access - Salesforce": "MinimumAccess",
}

# Reverse mapping: Metadata API fullName → friendly UI label.
# Used in _normalize to set ProfileSpec.label when the raw metadata does not
# include a label field (standard profiles often lack one).
STANDARD_PROFILE_FULLNAME_TO_LABEL: dict[str, str] = {
    v: k for k, v in STANDARD_PROFILE_LABEL_TO_FULLNAME.items()
}


def _resolve_profile_fullname(name: str) -> str:
    """Translate a user-supplied profile name to the Metadata API fullName."""
    return STANDARD_PROFILE_LABEL_TO_FULLNAME.get(name, name)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return False


def _normalize(raw: dict[str, Any], kind: str) -> ProfileSpec:
    full_name = raw.get("fullName") or raw.get("FullName") or ""
    # Prefer any label supplied by the API; for standard profiles the Metadata
    # API omits the label field entirely, so fall back to our reverse mapping
    # (e.g. "Admin" → "System Administrator") and then to full_name itself.
    raw_label = raw.get("label") or raw.get("Label")
    label = raw_label or STANDARD_PROFILE_FULLNAME_TO_LABEL.get(full_name, full_name)

    obj_perms = [
        ObjectPermission(
            obj=op.get("object", ""),
            create=_bool(op.get("allowCreate")),
            read=_bool(op.get("allowRead")),
            edit=_bool(op.get("allowEdit")),
            delete=_bool(op.get("allowDelete")),
            view_all=_bool(op.get("viewAllRecords")),
            modify_all=_bool(op.get("modifyAllRecords")),
        )
        for op in _as_list(raw.get("objectPermissions"))
        if op.get("object")
    ]

    field_perms = [
        FieldPermission(
            field=fp.get("field", ""),
            readable=_bool(fp.get("readable")),
            editable=_bool(fp.get("editable")),
        )
        for fp in _as_list(raw.get("fieldPermissions"))
        if fp.get("field")
    ]

    record_type_vis: dict[str, bool] = {}
    for rt in _as_list(raw.get("recordTypeVisibilities")):
        rt_name = rt.get("recordType")
        if rt_name:
            record_type_vis[rt_name] = _bool(rt.get("visible"))

    layout_assignments: list[LayoutAssignmentEntry] = [
        LayoutAssignmentEntry(
            layout=la.get("layout", ""),
            record_type=la.get("recordType") or None,
        )
        for la in _as_list(raw.get("layoutAssignments"))
        if la.get("layout")
    ]

    return ProfileSpec(
        full_name=full_name,
        label=label,
        kind=kind,
        user_license=raw.get("userLicense"),
        object_permissions=obj_perms,
        field_permissions=field_perms,
        record_type_visibilities=record_type_vis,
        layout_assignments=layout_assignments,
    )


async def fetch_all(
    client: SalesforceClient,
    *,
    profile_names: Iterable[str] | None,
    permission_set_names: Iterable[str] | None,
) -> tuple[list[ProfileSpec], list[str]]:
    """Fetch the requested Profiles and PermissionSets in one concurrent pass.

    If a name list is None, fall back to enumerating every Profile/PermissionSet
    in the org that has at least one assigned user — mirroring the Apex tool's
    default selection logic (`getProfilesMetaData`, lines 4460-4490).

    Returns (specs, missing_names) so the caller can warn about requested
    names that produced no metadata (typos, label-vs-fullName mismatches, etc.).

    NOTE — System Administrator (Metadata API fullName "Admin"):
    The System Administrator profile is unconditionally included even in auto-detect
    mode.  Its profile metadata from readMetadata may contain empty objectPermissions
    / fieldPermissions because Salesforce grants access implicitly to admins rather
    than via explicit FLS entries.  We still surface the row so auditors can see
    that the profile exists in the system; every permission cell will simply render
    blank (no checkmark) rather than being fabricated.
    """
    raw_profile_names = list(profile_names) if profile_names else None
    raw_permset_names = list(permission_set_names) if permission_set_names else None

    if raw_profile_names is not None:
        # Caller supplied explicit names — translate any standard labels to their
        # Metadata API fullNames (e.g. "System Administrator" → "Admin").
        profile_list: list[str] = [_resolve_profile_fullname(n) for n in raw_profile_names]
    else:
        # Auto-detect: query profiles that have at least one active assigned user.
        # _profiles_with_users returns UI *labels* (e.g. "System Administrator"),
        # so we must translate them through _resolve_profile_fullname before
        # passing to readMetadata — otherwise the API silently returns empty
        # results for standard profiles and they are dropped from the output.
        detected_labels = await _profiles_with_users(client)
        profile_list = [_resolve_profile_fullname(n) for n in detected_labels]

    # System Administrator ("Admin") must always appear in every permissions audit.
    # It is the canonical full-access profile and its absence from the table is
    # more misleading than surfacing it with empty FLS rows.
    _ADMIN_FULLNAME = "Admin"
    if _ADMIN_FULLNAME not in profile_list:
        profile_list = [_ADMIN_FULLNAME] + profile_list

    permset_list = (
        raw_permset_names
        if raw_permset_names is not None
        else await _permsets_with_users(client)
    )

    profiles_task = client.read_metadata("Profile", profile_list) if profile_list else _noop()
    permsets_task = (
        client.read_metadata("PermissionSet", permset_list) if permset_list else _noop()
    )
    raw_profiles, raw_permsets = await asyncio.gather(profiles_task, permsets_task)

    specs: list[ProfileSpec] = []
    found_profile_names: set[str] = set()
    found_permset_names: set[str] = set()

    for r in raw_profiles:
        spec = _normalize(r, "Profile")
        if spec.full_name:  # drop empty results (unmatched names come back blank)
            specs.append(spec)
            found_profile_names.add(spec.full_name)
    for r in raw_permsets:
        spec = _normalize(r, "PermissionSet")
        if spec.full_name:
            specs.append(spec)
            found_permset_names.add(spec.full_name)

    # PermissionSetGroup salvage pass: aggregated PermissionSets that back a
    # PermissionSetGroup (Type='Group') are hidden from the Metadata API entirely
    # — readMetadata returns xsi:nil for them. But their ObjectPermissions and
    # FieldPermissions rows are queryable via plain SOQL, so we can rebuild a
    # ProfileSpec from those for any name the Metadata API gave up on.
    if raw_permset_names is not None:
        initially_missing = [n for n in raw_permset_names if n not in found_permset_names]
        if initially_missing:
            group_specs = await _fetch_permission_set_groups_via_soql(
                client, initially_missing
            )
            for spec in group_specs:
                specs.append(spec)
                found_permset_names.add(spec.full_name)

    missing: list[str] = []
    if raw_profile_names is not None:
        for original in raw_profile_names:
            resolved = _resolve_profile_fullname(original)
            if resolved not in found_profile_names:
                missing.append(f"profile:{original}")
    if raw_permset_names is not None:
        for original in raw_permset_names:
            if original not in found_permset_names:
                missing.append(f"permission_set:{original}")

    return specs, missing


async def _noop() -> list[dict[str, Any]]:
    return []


async def _profiles_with_users(client: SalesforceClient) -> list[str]:
    soql = (
        "SELECT Profile.Name FROM User "
        "WHERE IsActive = true AND Profile.Name != null "
        "GROUP BY Profile.Name HAVING COUNT(Id) > 0"
    )
    try:
        result = await client.query(soql)
    except Exception:
        # Aggregate queries with GROUP BY require a different endpoint variant
        # in older API versions; fall back to a plain DISTINCT pull.
        result = await client.query(
            "SELECT Name FROM Profile WHERE Id IN (SELECT ProfileId FROM User WHERE IsActive = true)"
        )
    names: list[str] = []
    for record in result.get("records", []):
        name = record.get("Name") or (record.get("Profile") or {}).get("Name")
        if name:
            names.append(name)
    return names


def _soql_quote(value: str) -> str:
    # SOQL string literal escaping: single quotes and backslashes.
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def _fetch_permission_set_groups_via_soql(
    client: SalesforceClient,
    names: list[str],
) -> list[ProfileSpec]:
    """Rebuild ProfileSpec for Type='Group' PermissionSets using SOQL.

    These aggregated permission sets back a PermissionSetGroup and are not
    visible to the Metadata API. Their object/field permissions ARE queryable
    via standard SOQL, so we reconstruct ProfileSpec from those tables.

    Names that don't exist or aren't Type='Group' are silently skipped (they'll
    flow through to the regular `missing` warning).

    Record-type visibilities and layout assignments are not reliably queryable
    via SOQL for PermissionSetGroup-aggregated permsets, so those stay empty.
    """
    if not names:
        return []

    quoted = ",".join(f"'{_soql_quote(n)}'" for n in names)
    ps_records = await client.query_all(
        f"SELECT Id, Name, Label, PermissionSetGroupId "
        f"FROM PermissionSet "
        f"WHERE Name IN ({quoted}) AND Type = 'Group'"
    )
    if not ps_records:
        return []

    id_to_info: dict[str, tuple[str, str]] = {
        r["Id"]: (r["Name"], r.get("Label") or r["Name"]) for r in ps_records
    }
    ids_in = ",".join(f"'{ps_id}'" for ps_id in id_to_info)

    obj_perm_records, field_perm_records = await asyncio.gather(
        client.query_all(
            f"SELECT ParentId, SobjectType, "
            f"PermissionsCreate, PermissionsRead, PermissionsEdit, PermissionsDelete, "
            f"PermissionsViewAllRecords, PermissionsModifyAllRecords "
            f"FROM ObjectPermissions WHERE ParentId IN ({ids_in})"
        ),
        client.query_all(
            f"SELECT ParentId, Field, PermissionsRead, PermissionsEdit "
            f"FROM FieldPermissions WHERE ParentId IN ({ids_in})"
        ),
    )

    obj_perms_by_parent: dict[str, list[ObjectPermission]] = {}
    for rec in obj_perm_records:
        parent = rec["ParentId"]
        obj_perms_by_parent.setdefault(parent, []).append(
            ObjectPermission(
                obj=rec["SobjectType"],
                create=_bool(rec.get("PermissionsCreate")),
                read=_bool(rec.get("PermissionsRead")),
                edit=_bool(rec.get("PermissionsEdit")),
                delete=_bool(rec.get("PermissionsDelete")),
                view_all=_bool(rec.get("PermissionsViewAllRecords")),
                modify_all=_bool(rec.get("PermissionsModifyAllRecords")),
            )
        )

    field_perms_by_parent: dict[str, list[FieldPermission]] = {}
    for rec in field_perm_records:
        parent = rec["ParentId"]
        field_perms_by_parent.setdefault(parent, []).append(
            FieldPermission(
                field=rec["Field"],
                readable=_bool(rec.get("PermissionsRead")),
                editable=_bool(rec.get("PermissionsEdit")),
            )
        )

    specs: list[ProfileSpec] = []
    for ps_id, (name, label) in id_to_info.items():
        specs.append(
            ProfileSpec(
                full_name=name,
                label=label,
                kind="PermissionSetGroup",
                user_license=None,
                object_permissions=obj_perms_by_parent.get(ps_id, []),
                field_permissions=field_perms_by_parent.get(ps_id, []),
                record_type_visibilities={},
                layout_assignments=[],
            )
        )
    return specs


async def _permsets_with_users(client: SalesforceClient) -> list[str]:
    soql = (
        "SELECT Name FROM PermissionSet "
        "WHERE IsOwnedByProfile = false AND Id IN "
        "(SELECT PermissionSetId FROM PermissionSetAssignment WHERE Assignee.IsActive = true)"
    )
    result = await client.query(soql)
    return [r["Name"] for r in result.get("records", []) if r.get("Name")]
