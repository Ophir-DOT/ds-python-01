"""Page layout assignment per profile via Tooling ProfileLayout SOQL.

Orthogonal to `ProfileSpec.layout_assignments`: that field only covers the
profiles the user selected with `--profiles`, because it's parsed off the
single readMetadata pass profiles.py runs. §3.4 in the PDF wants every
profile/layout binding in the org for this object — including profiles the
user did NOT pass on the CLI — so we issue Tooling SOQL covering them all.

Two-step query because of an idiosyncrasy of the Tooling API:

1. `Layout` supports filtering by `EntityDefinition.QualifiedApiName`, but
   `ProfileLayout` does NOT (the planner rewrites the cross-entity filter to
   a non-existent `DurableId` column on Layout and errors out).

2. For custom objects, `Layout.TableEnumOrId` is the 15-char Id of the
   EntityDefinition, not the API name. So we can't filter ProfileLayout by
   `Layout.TableEnumOrId = '<object_api_name>'` either — that only works for
   standard objects.

Therefore: first resolve `Layout.Id` for the object, then issue a second
ProfileLayout query filtered by `LayoutId IN (...)`.
"""

from __future__ import annotations

from ..client import SalesforceClient
from ..models import LayoutAssignment

# Well-known standard Salesforce profile names that ship with every org.
# These are "boilerplate" profiles — present in every org regardless of the
# customer's configuration — that can optionally be hidden from the §3.4 table
# via a future Settings toggle.  The DEFAULT is always to show all profiles;
# this set is exposed solely to support that future filter.
STANDARD_PROFILE_NAMES: frozenset[str] = frozenset(
    {
        "Analytics Cloud Integration User",
        "Analytics Cloud Security User",
        "Authenticated Website",
        "Chatter External User",
        "Chatter Free User",
        "Chatter Moderator User",
        "Contract Manager",
        "Custom: Marketing Profile",
        "Custom: Sales Profile",
        "Custom: Support Profile",
        "Force.com - App Subscription User",
        "Force.com - Free User",
        "Gold Partner User",
        "Guest",
        "High Volume Customer Portal User",
        "Identity User",
        "Minimum Access - Salesforce",
        "Partner App Subscription User",
        "Partner Community Login User",
        "Partner Community User",
        "Read Only",
        "Silver Partner User",
        "Solution Manager",
        "Standard User",
        "System Administrator",
        "Work.com Only User",
    }
)


def is_standard_profile(profile_name: str) -> bool:
    """Return True if *profile_name* is a well-known standard Salesforce profile.

    The check is exact-match, case-sensitive, against ``STANDARD_PROFILE_NAMES``.
    It does NOT filter any collector output — callers must opt in to using this
    helper if they want to hide standard profiles.

    >>> is_standard_profile("System Administrator")
    True
    >>> is_standard_profile("My Custom Profile")
    False
    """
    return profile_name in STANDARD_PROFILE_NAMES


async def _layout_ids_for_object(
    client: SalesforceClient, object_api_name: str
) -> list[str]:
    soql = (
        "SELECT Id FROM Layout "
        f"WHERE EntityDefinition.QualifiedApiName = '{object_api_name}'"
    )
    try:
        result = await client.tooling_query(soql)
    except Exception:
        return []
    return [r["Id"] for r in result.get("records", []) if r.get("Id")]


async def fetch(
    client: SalesforceClient, object_api_name: str
) -> list[LayoutAssignment]:
    layout_ids = await _layout_ids_for_object(client, object_api_name)
    if not layout_ids:
        return []

    quoted = ",".join(f"'{i}'" for i in layout_ids)
    soql = (
        "SELECT Layout.Name, Profile.Name, RecordType.Name "
        "FROM ProfileLayout "
        f"WHERE LayoutId IN ({quoted}) AND ProfileId != null "
        "ORDER BY Profile.Name, Layout.Name"
    )
    try:
        result = await client.tooling_query(soql)
    except Exception:
        return []

    assignments: list[LayoutAssignment] = []
    for r in result.get("records", []):
        layout_name = (r.get("Layout") or {}).get("Name") or ""
        profile_name = (r.get("Profile") or {}).get("Name") or ""
        rt_name = (r.get("RecordType") or {}).get("Name") or None
        if not (layout_name and profile_name):
            continue
        assignments.append(
            LayoutAssignment(
                profile=profile_name,
                layout=layout_name,
                record_type=rt_name,
            )
        )
    return assignments
