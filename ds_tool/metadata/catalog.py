"""Org catalog helpers for populating GUI selection widgets.

These are intentionally lightweight (names/labels only) and distinct from the
heavy collectors:
  - `list_objects` drives the object multi-select (mirrors Aura `getAllObjectsList`).
  - `list_profiles_permsets` drives the profile/permission-set dual-list
    (mirrors the Aura Settings dual-listbox). It returns NAMES only; the full
    permission metadata is still read once via `profiles.fetch_all`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..client import SalesforceClient

# Auto-generated companion objects the user never reports on directly.
_EXCLUDE_SUFFIXES: tuple[str, ...] = (
    "__Share",
    "__History",
    "__Feed",
    "__Tag",
    "__ChangeEvent",
    "__mdt",  # custom metadata types — handled by their own tab/flow
)


@dataclass(frozen=True)
class ObjectRef:
    api_name: str
    label: str
    custom: bool


@dataclass(frozen=True)
class ProfileRef:
    name: str
    label: str
    kind: str  # "Profile" | "PermissionSet"


def _reportable(entry: dict) -> bool:
    name = entry.get("name") or ""
    if not name or not entry.get("queryable"):
        return False
    return not name.endswith(_EXCLUDE_SUFFIXES)


async def list_objects(client: SalesforceClient) -> list[ObjectRef]:
    """All custom + standard reportable sobjects, sorted by label."""
    version = client.creds.api_version
    payload = await client.rest_get(f"/services/data/v{version}/sobjects/")
    refs = [
        ObjectRef(
            api_name=e["name"],
            label=e.get("label") or e["name"],
            custom=bool(e.get("custom")),
        )
        for e in payload.get("sobjects", [])
        if _reportable(e)
    ]
    refs.sort(key=lambda r: r.label.lower())
    return refs


async def list_profiles_permsets(client: SalesforceClient) -> list[ProfileRef]:
    """Profile + (non-profile-owned) PermissionSet names for the picker.

    Permission sets with `IsOwnedByProfile = true` are the hidden sets backing
    each profile; they are excluded so the list matches what users see in Setup.
    """
    refs: list[ProfileRef] = []

    for r in await client.query_all("SELECT Id, Name FROM Profile ORDER BY Name"):
        name = r.get("Name") or ""
        if name:
            refs.append(ProfileRef(name=name, label=name, kind="Profile"))

    perm_soql = (
        "SELECT Id, Name, Label FROM PermissionSet "
        "WHERE IsOwnedByProfile = false ORDER BY Label"
    )
    for r in await client.query_all(perm_soql):
        name = r.get("Name") or ""
        if name:
            refs.append(
                ProfileRef(
                    name=name,
                    label=r.get("Label") or name,
                    kind="PermissionSet",
                )
            )

    return refs
