from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ds_tool.metadata.profiles import (
    STANDARD_PROFILE_FULLNAME_TO_LABEL,
    _normalize,
    fetch_all,
)


def test_normalize_profile_with_object_and_field_perms() -> None:
    raw = {
        "fullName": "Admin",
        "label": "System Administrator",
        "userLicense": "Salesforce",
        "objectPermissions": [
            {
                "object": "Account",
                "allowCreate": True,
                "allowRead": True,
                "allowEdit": True,
                "allowDelete": "true",
                "viewAllRecords": False,
                "modifyAllRecords": False,
            }
        ],
        "fieldPermissions": [
            {"field": "Account.Name", "readable": True, "editable": True},
            {"field": "Account.Industry", "readable": True, "editable": False},
        ],
        "recordTypeVisibilities": [
            {"recordType": "Account.Customer", "visible": True}
        ],
        "layoutAssignments": [
            {"layout": "Account-Account Layout"},
            {"layout": "Account-Customer Layout", "recordType": "Account.Customer"},
        ],
    }
    spec = _normalize(raw, "Profile")
    assert spec.full_name == "Admin"
    assert spec.kind == "Profile"
    assert len(spec.object_permissions) == 1
    op = spec.object_permissions[0]
    assert op.create and op.read and op.edit and op.delete
    assert not op.view_all and not op.modify_all
    assert len(spec.field_permissions) == 2
    assert spec.record_type_visibilities == {"Account.Customer": True}
    assert len(spec.layout_assignments) == 2
    assert spec.layout_assignments[0].layout == "Account-Account Layout"
    assert spec.layout_assignments[0].record_type is None
    assert spec.layout_assignments[1].record_type == "Account.Customer"


def test_normalize_tolerates_singular_or_missing_lists() -> None:
    # Metadata API often returns a single object instead of a list when there's
    # exactly one entry. _normalize must handle both shapes.
    raw_single = {
        "fullName": "ReadOnly",
        "objectPermissions": {
            "object": "Account",
            "allowRead": "true",
        },
        "fieldPermissions": None,
        "layoutAssignments": {"layout": "Account-Read Only Layout"},
    }
    spec = _normalize(raw_single, "PermissionSet")
    assert len(spec.object_permissions) == 1
    assert spec.object_permissions[0].read is True
    assert spec.field_permissions == []
    assert len(spec.layout_assignments) == 1
    assert spec.layout_assignments[0].layout == "Account-Read Only Layout"


# ---------------------------------------------------------------------------
# Label-mapping tests (WI-NEW-B / WI-16)
# ---------------------------------------------------------------------------

def test_fullname_to_label_mapping_admin() -> None:
    """Admin fullName must map to 'System Administrator' UI label."""
    assert STANDARD_PROFILE_FULLNAME_TO_LABEL["Admin"] == "System Administrator"


def test_fullname_to_label_mapping_standard() -> None:
    """Standard fullName must map to 'Standard User' UI label."""
    assert STANDARD_PROFILE_FULLNAME_TO_LABEL["Standard"] == "Standard User"


def test_normalize_sets_label_from_raw_when_present() -> None:
    """If the raw metadata includes a label field, _normalize uses it as-is."""
    raw = {
        "fullName": "Admin",
        "label": "System Administrator",
    }
    spec = _normalize(raw, "Profile")
    assert spec.label == "System Administrator"


def test_normalize_applies_fullname_to_label_mapping_when_no_raw_label() -> None:
    """When raw metadata has no label (typical for standard profiles from the
    Metadata API), _normalize must derive the label from the reverse mapping."""
    raw = {"fullName": "Admin"}
    spec = _normalize(raw, "Profile")
    assert spec.label == "System Administrator", (
        "fullName='Admin' must resolve to label='System Administrator'"
    )


def test_normalize_standard_fullname_to_label() -> None:
    """fullName='Standard' (no label in raw) → label='Standard User'."""
    raw = {"fullName": "Standard"}
    spec = _normalize(raw, "Profile")
    assert spec.label == "Standard User"


def test_normalize_custom_profile_keeps_its_own_label() -> None:
    """Custom profiles supply their own label; _normalize must not override it."""
    raw = {
        "fullName": "Training_Coordinator",
        "label": "Training Coordinator",
    }
    spec = _normalize(raw, "Profile")
    assert spec.label == "Training Coordinator"


def test_normalize_custom_profile_falls_back_to_full_name_when_no_label() -> None:
    """A custom profile with no label in raw metadata falls back to full_name."""
    raw = {"fullName": "My_Custom_Profile"}
    spec = _normalize(raw, "Profile")
    assert spec.label == "My_Custom_Profile"


# ---------------------------------------------------------------------------
# fetch_all integration tests (mocked client)
# ---------------------------------------------------------------------------

def _make_client(
    *,
    profile_query_records: list[dict],
    profile_metadata: list[dict],
    permset_query_records: list[dict] | None = None,
    permset_metadata: list[dict] | None = None,
) -> MagicMock:
    """Build a minimal mock SalesforceClient for fetch_all tests."""
    client = MagicMock()

    async def _query(soql: str) -> dict:
        # Return profiles or permsets depending on which SOQL is issued.
        if "PermissionSet" in soql:
            return {"records": permset_query_records or []}
        return {"records": profile_query_records}

    client.query = AsyncMock(side_effect=_query)

    async def _read_metadata(kind: str, names: list[str]) -> list[dict]:
        if kind == "Profile":
            # Return only the profile dicts whose fullName is in the requested names.
            return [p for p in profile_metadata if p.get("fullName") in names]
        return [p for p in (permset_metadata or []) if p.get("fullName") in names]

    client.read_metadata = AsyncMock(side_effect=_read_metadata)
    return client


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


# -- Test 1: System Administrator is always present in auto-detect mode ------

def test_fetch_all_auto_detect_always_includes_system_admin() -> None:
    """In auto-detect mode (profile_names=None) System Administrator must appear
    even when the SOQL returns only OTHER profiles.

    The SOQL returns labels; _profiles_with_users may not return "System
    Administrator" at all in some orgs (e.g. no active admin user row), but
    the tool must still request the "Admin" metadata record unconditionally.
    """
    client = _make_client(
        # SOQL returns only one other profile — no System Administrator row.
        profile_query_records=[{"Profile": {"Name": "Training Coordinator"}}],
        profile_metadata=[
            {"fullName": "Admin", "label": "System Administrator"},
            {"fullName": "Training_Coordinator", "label": "Training Coordinator"},
        ],
    )

    specs, missing = _run(
        fetch_all(client, profile_names=None, permission_set_names=[])
    )

    full_names = [s.full_name for s in specs]
    assert "Admin" in full_names, (
        "System Administrator (fullName='Admin') must always be in the fetched set"
    )
    assert missing == []


# -- Test 2: Auto-detect translates standard profile labels before API call --

def test_fetch_all_auto_detect_translates_standard_profile_labels() -> None:
    """_profiles_with_users returns UI labels; fetch_all must convert them via
    _resolve_profile_fullname so readMetadata receives the correct API fullName.

    Without translation, readMetadata('Profile', ['System Administrator'])
    returns an empty result and the profile is silently dropped.
    """
    client = _make_client(
        # SOQL returns the label "System Administrator".
        profile_query_records=[{"Profile": {"Name": "System Administrator"}}],
        profile_metadata=[
            {
                "fullName": "Admin",
                "label": "System Administrator",
                "userLicense": "Salesforce",
                "objectPermissions": [
                    {
                        "object": "Account",
                        "allowCreate": True,
                        "allowRead": True,
                        "allowEdit": True,
                        "allowDelete": True,
                        "viewAllRecords": True,
                        "modifyAllRecords": True,
                    }
                ],
            }
        ],
    )

    specs, missing = _run(
        fetch_all(client, profile_names=None, permission_set_names=[])
    )

    admin_specs = [s for s in specs if s.full_name == "Admin"]
    assert len(admin_specs) == 1, (
        "System Administrator label must be translated to 'Admin' before readMetadata"
    )
    op = admin_specs[0].object_permissions[0]
    assert op.read and op.create and op.edit and op.delete and op.view_all and op.modify_all


# -- Test 3: Profile with active assignees but no object perms is still shown -

def test_fetch_all_includes_profile_with_assignees_but_no_object_perms() -> None:
    """A profile like Training_Coordinator may have active users but zero
    object-permission entries in its metadata.  fetch_all must not drop it —
    showing an all-blank row is the correct auditor experience.
    """
    client = _make_client(
        profile_query_records=[{"Profile": {"Name": "Training_Coordinator"}}],
        profile_metadata=[
            # Training_Coordinator returns a valid fullName but empty perms.
            {"fullName": "Training_Coordinator", "label": "Training Coordinator"},
            # Admin always gets injected.
            {"fullName": "Admin", "label": "System Administrator"},
        ],
    )

    specs, missing = _run(
        fetch_all(client, profile_names=None, permission_set_names=[])
    )

    full_names = [s.full_name for s in specs]
    assert "Training_Coordinator" in full_names, (
        "Profile with assignees but no object perms must not be dropped"
    )
    tc_spec = next(s for s in specs if s.full_name == "Training_Coordinator")
    assert tc_spec.object_permissions == [], "object_permissions should be empty, not fabricated"
    assert tc_spec.field_permissions == [], "field_permissions should be empty, not fabricated"


# -- Test 4: Explicit profile_names still translates standard labels ----------

def test_fetch_all_explicit_names_translates_standard_labels() -> None:
    """When profile_names is explicitly provided with a standard label like
    'System Administrator', it must still be translated to 'Admin'.
    """
    client = _make_client(
        profile_query_records=[],  # not used when profile_names is explicit
        profile_metadata=[
            {"fullName": "Admin", "label": "System Administrator"},
        ],
    )

    specs, missing = _run(
        fetch_all(
            client,
            profile_names=["System Administrator"],
            permission_set_names=[],
        )
    )

    full_names = [s.full_name for s in specs]
    assert "Admin" in full_names
    assert missing == []


# -- Test 5: System Admin already in explicit list — no duplicate -------------

def test_fetch_all_no_duplicate_admin_when_explicitly_requested() -> None:
    """If the caller explicitly passes 'System Administrator', the always-include
    logic must not produce a duplicate 'Admin' entry in the specs list.
    """
    client = _make_client(
        profile_query_records=[],
        profile_metadata=[
            {"fullName": "Admin", "label": "System Administrator"},
        ],
    )

    specs, missing = _run(
        fetch_all(
            client,
            profile_names=["System Administrator"],
            permission_set_names=[],
        )
    )

    admin_specs = [s for s in specs if s.full_name == "Admin"]
    assert len(admin_specs) == 1, "Admin must appear exactly once even when explicitly requested"
