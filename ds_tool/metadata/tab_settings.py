"""Tab visibility per profile/permission-set for this object's tab. §3.6 (WI-05).

For a custom object the tab name in Profile.tabVisibilities[] equals the object
API name (e.g. "MyObject__c"). For standard objects it is "standard-<Name>"
(e.g. "standard-Account").  We match on both forms so the caller never needs to
know which kind of object they have.

For managed (namespaced) objects such as "CompSuite__Dot_Compliance_QA__c" the
Salesforce Metadata API may store the tab name either as the full namespaced
form or as the bare local name without the namespace prefix.  We therefore add
both forms to the candidate set so that a profile entry recorded under either
name is matched correctly.

Profile label mapping (WI-NEW-D): the Metadata API returns standard profile
fullNames such as "Admin" and "Standard". We map these to their friendly UI
labels ("System Administrator", "Standard User") so §3.6 is consistent with
§3.1/§3.2/§3.3.  Custom profiles and permission sets keep their own name.

Permission set tab key (WI-02): Salesforce Metadata API stores tab visibility
under the key "tabVisibilities" for Profiles but under "tabSettings" for
PermissionSets (see Ctrl_CMP_Configuration_Report.cls ~line 436).  We check
both keys so that permission-set entries are not silently emitted as "N/A".

Reference: Ctrl_CMP_Configuration_Report.cls ~line 436, 530-541.
"""

from __future__ import annotations

import re
from typing import Any

from ..client import SalesforceClient
from ..models import TabVisibilitySpec
from .profiles import STANDARD_PROFILE_FULLNAME_TO_LABEL

# Matches a namespaced Salesforce API name: <Namespace>__<LocalName>__<suffix>
# where <suffix> is "c", "mdt", "e", "b", "x", etc.
# Capture groups: (1) namespace, (2) local-name-with-suffix  e.g. "LocalName__c"
_NAMESPACED_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)__(.+__(?:c|mdt|e|b|x|ka|kav))$")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _tab_names_for_object(object_api_name: str) -> set[str]:
    """Return the set of tab names that can represent this object in metadata.

    Custom objects use the object API name directly; standard objects are
    prefixed with "standard-".  We accept both so that callers do not need to
    distinguish between the two.

    Managed (namespaced) objects (e.g. "CompSuite__Dot_Compliance_QA__c") may
    appear in profile tabVisibilities entries using either the full namespaced
    form or just the bare local name ("Dot_Compliance_QA__c").  Both variants
    are included in the returned set so that either encoding in the org metadata
    is matched correctly.

    NOTE: if the caller passes only the bare local name and the profile entry
    uses the namespaced form, there is no way to reconstruct the namespace
    prefix here.  The recommended practice is to always pass the full API name
    (namespaced) when calling this function for managed objects.
    """
    names: set[str] = {object_api_name}

    # Build the "standard-" variant for non-custom names.
    if not object_api_name.endswith("__c") and not object_api_name.endswith("__mdt"):
        names.add(f"standard-{object_api_name}")

    # For namespaced custom objects (Namespace__LocalName__<suffix>), also add
    # the bare local name (LocalName__<suffix>) as a candidate.  Some Salesforce
    # orgs emit the tab name without the namespace prefix in tabVisibilities,
    # which would otherwise cause a false "N/A" result.
    m = _NAMESPACED_RE.match(object_api_name)
    if m:
        bare_name = m.group(2)  # e.g. "Dot_Compliance_QA__c"
        names.add(bare_name)

    return names


async def fetch(client: SalesforceClient, object_api_name: str, cache: Any) -> list[TabVisibilitySpec]:
    """Return one TabVisibilitySpec per profile/permset that has a tab visibility entry.

    Profiles and permission sets that have no entry for this object's tab are
    emitted with visibility "N/A", matching the legacy Apex tool behaviour.

    Parameters
    ----------
    client:
        An authenticated SalesforceClient.
    object_api_name:
        The object API name (e.g. "Account" or "MyObject__c").
    cache:
        A ds_tool.cache.ProfileCache whose .all() returns the list of
        ProfileSpec to iterate over.
    """
    tab_names = _tab_names_for_object(object_api_name)

    all_profiles = cache.all()
    if not all_profiles:
        return []

    profile_names = [p.full_name for p in all_profiles if p.kind == "Profile" and p.full_name]
    permset_names = [p.full_name for p in all_profiles if p.kind != "Profile" and p.full_name]

    raw_profiles: list[dict[str, Any]] = []
    raw_permsets: list[dict[str, Any]] = []

    if profile_names:
        try:
            raw_profiles = await client.read_metadata("Profile", profile_names)
        except Exception:
            raw_profiles = []

    if permset_names:
        try:
            raw_permsets = await client.read_metadata("PermissionSet", permset_names)
        except Exception:
            raw_permsets = []

    if not raw_profiles and not raw_permsets:
        # Either there were no names to fetch, or all read_metadata calls failed.
        # Surface empty per resilience rule.
        return []

    specs: list[TabVisibilitySpec] = []

    for raw in raw_profiles + raw_permsets:
        if not isinstance(raw, dict):
            continue
        full_name = raw.get("fullName") or raw.get("FullName") or ""
        if not full_name:
            continue

        visibility = "N/A"
        # Profiles use "tabVisibilities"; PermissionSets use "tabSettings".
        # Check both keys so neither kind silently falls through to "N/A".
        for entry in _as_list(raw.get("tabVisibilities")) + _as_list(raw.get("tabSettings")):
            if not isinstance(entry, dict):
                continue
            if entry.get("tab") in tab_names:
                visibility = entry.get("visibility") or "N/A"
                break

        # Map standard-profile fullNames to their friendly UI labels so §3.6
        # shows "System Administrator" etc., consistent with §3.1/§3.2/§3.3.
        display_name = STANDARD_PROFILE_FULLNAME_TO_LABEL.get(full_name, full_name)
        specs.append(TabVisibilitySpec(profile=display_name, visibility=visibility))

    return specs
