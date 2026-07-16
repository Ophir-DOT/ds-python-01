from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import tab_settings
from ds_tool.models import ProfileSpec


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile_spec(full_name: str, kind: str = "Profile") -> ProfileSpec:
    return ProfileSpec(full_name=full_name, label=full_name, kind=kind)


class _FakeCache:
    """Minimal stand-in for ds_tool.cache.ProfileCache."""

    def __init__(self, profiles: list[ProfileSpec]) -> None:
        self._profiles = profiles

    def all(self) -> list[ProfileSpec]:
        return list(self._profiles)


# ---------------------------------------------------------------------------
# _tab_names_for_object
# ---------------------------------------------------------------------------

def test_tab_names_custom_object() -> None:
    names = tab_settings._tab_names_for_object("MyObject__c")
    assert "MyObject__c" in names
    # Custom objects should NOT get a "standard-" variant
    assert not any(n.startswith("standard-") for n in names)


def test_tab_names_standard_object() -> None:
    names = tab_settings._tab_names_for_object("Account")
    assert "Account" in names
    assert "standard-Account" in names


def test_tab_names_namespaced_object_includes_bare_name() -> None:
    """Namespaced managed objects must match on both the full and bare tab name.

    Salesforce profile tabVisibilities entries may record the tab name as either
    "CompSuite__X__c" (full namespace) or "X__c" (bare local name). Both must
    be in the candidate set so neither encoding causes a false N/A result.
    """
    names = tab_settings._tab_names_for_object("CompSuite__X__c")
    assert "CompSuite__X__c" in names, "Full namespaced form must be a candidate"
    assert "X__c" in names, "Bare local name must also be a candidate"
    # Namespaced custom objects should NOT get a "standard-" variant
    assert not any(n.startswith("standard-") for n in names)


def test_tab_names_namespaced_object_real_name() -> None:
    """CompSuite__Dot_Compliance_QA__c is the motivating case for the namespace fix."""
    names = tab_settings._tab_names_for_object("CompSuite__Dot_Compliance_QA__c")
    assert "CompSuite__Dot_Compliance_QA__c" in names
    assert "Dot_Compliance_QA__c" in names


# ---------------------------------------------------------------------------
# fetch — happy path
# ---------------------------------------------------------------------------

def test_fetch_parses_tab_visibilities_for_profiles() -> None:
    cache = _FakeCache(
        [
            _make_profile_spec("Admin", "Profile"),
            _make_profile_spec("Standard", "Profile"),
        ]
    )
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            # Profiles response
            [
                {
                    "fullName": "Admin",
                    "tabVisibilities": [
                        {"tab": "Account", "visibility": "DefaultOn"},
                        {"tab": "standard-Account", "visibility": "DefaultOn"},
                    ],
                },
                {
                    "fullName": "Standard",
                    "tabVisibilities": [
                        {"tab": "standard-Account", "visibility": "DefaultOff"},
                    ],
                },
            ],
            # PermissionSets response (empty — no permsets in cache)
        ]
    )

    specs = _run(tab_settings.fetch(client, "Account", cache))

    assert len(specs) == 2
    # Standard-profile fullNames must be mapped to their friendly UI labels.
    admin_spec = next(s for s in specs if s.profile == "System Administrator")
    standard_spec = next(s for s in specs if s.profile == "Standard User")
    assert admin_spec.visibility == "DefaultOn"
    assert standard_spec.visibility == "DefaultOff"


def test_fetch_emits_na_when_no_tab_entry() -> None:
    """A profile with no matching tab entry gets visibility 'N/A'."""
    cache = _FakeCache([_make_profile_spec("ReadOnly", "Profile")])
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "ReadOnly",
                "tabVisibilities": [
                    {"tab": "Contact", "visibility": "Hidden"},
                ],
            }
        ]
    )

    specs = _run(tab_settings.fetch(client, "Account", cache))

    assert len(specs) == 1
    # "ReadOnly" is the Metadata API fullName for the "Read Only" standard profile.
    assert specs[0].profile == "Read Only"
    assert specs[0].visibility == "N/A"


def test_fetch_handles_permsets() -> None:
    cache = _FakeCache(
        [
            _make_profile_spec("SalesPermSet", "PermissionSet"),
        ]
    )
    client = MagicMock()
    # Only one read_metadata call is made (for PermissionSets); no profiles in cache.
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "SalesPermSet",
                "tabVisibilities": [
                    {"tab": "Opportunity", "visibility": "Visible"},
                ],
            }
        ]
    )

    specs = _run(tab_settings.fetch(client, "Opportunity", cache))

    assert len(specs) == 1
    assert specs[0].profile == "SalesPermSet"
    assert specs[0].visibility == "Visible"


def test_fetch_custom_object_tab_name() -> None:
    """Custom object tabs use the API name directly (no 'standard-' prefix)."""
    cache = _FakeCache([_make_profile_spec("Admin", "Profile")])
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Admin",
                "tabVisibilities": [
                    {"tab": "MyObject__c", "visibility": "DefaultOn"},
                ],
            }
        ]
    )

    specs = _run(tab_settings.fetch(client, "MyObject__c", cache))

    assert len(specs) == 1
    assert specs[0].visibility == "DefaultOn"


def test_fetch_namespaced_object_tab_recorded_as_bare_name() -> None:
    """Profile entry uses bare tab name; caller passes full namespaced object name.

    This is the §3.6 Dot_Compliance_QA bug: the object is
    CompSuite__Dot_Compliance_QA__c but the profile's tabVisibilities entry
    records the tab as the bare local name "Dot_Compliance_QA__c".  Before the
    fix, this produced visibility="N/A"; after the fix it must resolve to the
    actual visibility value from the metadata.
    """
    cache = _FakeCache([_make_profile_spec("Dot_Compliance_QA", "PermissionSet")])
    client = MagicMock()
    # Only one read_metadata call is made (PermissionSet; no profiles in cache).
    # The tab name in the metadata uses the bare local name without the namespace
    # prefix — this is the scenario that previously produced "N/A".
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Dot_Compliance_QA",
                "tabVisibilities": [
                    {"tab": "Dot_Compliance_QA__c", "visibility": "Visible"},
                ],
            }
        ]
    )

    specs = _run(tab_settings.fetch(client, "CompSuite__Dot_Compliance_QA__c", cache))

    assert len(specs) == 1
    assert specs[0].profile == "Dot_Compliance_QA"
    assert specs[0].visibility == "Visible", (
        "Expected 'Visible' but got N/A — namespace-strip in _tab_names_for_object "
        "did not add the bare tab name as a candidate"
    )


def test_fetch_namespaced_object_tab_recorded_as_full_namespaced_name() -> None:
    """Profile entry uses the full namespaced tab name; caller passes same full name.

    Ensures the existing exact-match path still works after the namespace fix.
    """
    cache = _FakeCache([_make_profile_spec("Admin", "Profile")])
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Admin",
                "tabVisibilities": [
                    {"tab": "CompSuite__X__c", "visibility": "Visible"},
                ],
            }
        ]
    )

    specs = _run(tab_settings.fetch(client, "CompSuite__X__c", cache))

    assert len(specs) == 1
    assert specs[0].visibility == "Visible"


def test_fetch_single_tab_visibility_not_in_list() -> None:
    """tabVisibilities may be a single dict rather than a list."""
    cache = _FakeCache([_make_profile_spec("Admin", "Profile")])
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Admin",
                "tabVisibilities": {"tab": "standard-Account", "visibility": "Hidden"},
            }
        ]
    )

    specs = _run(tab_settings.fetch(client, "Account", cache))

    assert len(specs) == 1
    assert specs[0].visibility == "Hidden"


# ---------------------------------------------------------------------------
# fetch — error resilience
# ---------------------------------------------------------------------------

def test_fetch_returns_empty_on_profile_metadata_error() -> None:
    cache = _FakeCache([_make_profile_spec("Admin", "Profile")])
    client = MagicMock()
    client.read_metadata = AsyncMock(side_effect=RuntimeError("SOAP fault"))

    result = _run(tab_settings.fetch(client, "Account", cache))

    assert result == []


def test_fetch_returns_empty_on_permset_metadata_error() -> None:
    cache = _FakeCache([_make_profile_spec("MySalesPermSet", "PermissionSet")])
    client = MagicMock()
    client.read_metadata = AsyncMock(side_effect=RuntimeError("network error"))

    result = _run(tab_settings.fetch(client, "Account", cache))

    assert result == []


def test_fetch_returns_empty_when_cache_is_empty() -> None:
    cache = _FakeCache([])
    client = MagicMock()
    client.read_metadata = AsyncMock(return_value=[])

    result = _run(tab_settings.fetch(client, "Account", cache))

    assert result == []


# ---------------------------------------------------------------------------
# BUG fixes: label mapping (WI-NEW-D) + permset tabSettings key (WI-02)
# ---------------------------------------------------------------------------

def test_fetch_admin_fullname_maps_to_system_administrator_label() -> None:
    """BUG WI-NEW-D: Admin fullName must appear as 'System Administrator' in the spec.

    §3.1/§3.2/§3.3 already show 'System Administrator'; §3.6 must be consistent.
    The Metadata API returns fullName='Admin' for the System Administrator profile.
    tab_settings.fetch() must translate this via STANDARD_PROFILE_FULLNAME_TO_LABEL.
    """
    cache = _FakeCache([_make_profile_spec("Admin", "Profile")])
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Admin",
                "tabVisibilities": [
                    {"tab": "standard-Account", "visibility": "DefaultOn"},
                ],
            }
        ]
    )

    specs = _run(tab_settings.fetch(client, "Account", cache))

    assert len(specs) == 1
    assert specs[0].profile == "System Administrator", (
        f"Expected 'System Administrator' but got '{specs[0].profile}'. "
        "Admin fullName must be mapped to its friendly UI label."
    )
    assert specs[0].visibility == "DefaultOn"


def test_fetch_permset_uses_tabsettings_key() -> None:
    """BUG WI-02: PermissionSets expose tab visibility under 'tabSettings', not 'tabVisibilities'.

    Salesforce Metadata API stores tab access in Profile.tabVisibilities[] but
    in PermissionSet.tabSettings[].  Before the fix the code only checked
    'tabVisibilities', so every permission-set row silently returned 'N/A'.
    After the fix, a 'tabSettings' entry with visibility='Visible' must resolve.
    """
    cache = _FakeCache([_make_profile_spec("Dot_Compliance_QA", "PermissionSet")])
    client = MagicMock()
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Dot_Compliance_QA",
                # PermissionSets use 'tabSettings', not 'tabVisibilities'
                "tabSettings": [
                    {"tab": "Dot_Compliance_QA__c", "visibility": "Visible"},
                ],
            }
        ]
    )

    specs = _run(tab_settings.fetch(client, "CompSuite__Dot_Compliance_QA__c", cache))

    assert len(specs) == 1
    assert specs[0].profile == "Dot_Compliance_QA"
    assert specs[0].visibility == "Visible", (
        "Expected 'Visible' but got 'N/A'. "
        "PermissionSet tab visibility is stored under 'tabSettings', not 'tabVisibilities'."
    )
