"""Sharing Rules and Org-Wide Defaults for one object.

OWD (internal + external) comes from ``readMetadata("CustomObject", [object])[0]``
via the ``sharingModel`` and ``externalSharingModel`` fields.

Grant Access Using Hierarchies comes from the same CustomObject payload via the
``grantAccessUsingHierarchies`` boolean field.  This field is present for custom
objects in the Salesforce Metadata API (all supported API versions) and controls
whether users above the record owner in the role hierarchy automatically receive
access.  It is only meaningful – and only returned in the XML – for custom objects
with a non-Public sharing model; standard objects always inherit ``true`` and the
field is not returned by the API.  When absent we set it to ``None`` and the
template renders "—".

Sharing rules come from ``readMetadata("SharingRules", [object])[0]``, which
exposes two child lists:

* ``sharingCriteriaRules`` – rules based on field criteria
* ``sharingOwnerRules``    – rules based on record ownership

Reference: ``Ctrl_CMP_Configuration_Report.cls:1561-1593``.
"""

from __future__ import annotations

from typing import Any

from ..client import SalesforceClient
from ..models import SharingRuleSpec, SharingSpec


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _map_access_level(raw: str | None) -> str | None:
    """Normalise Salesforce accessLevel to "Read" or "Read/Write"."""
    if raw is None:
        return None
    if raw.lower() in ("edit", "read/write"):
        return "Read/Write"
    # "Read", "Read Only" → "Read"
    return "Read"


def _criteria_string(items: list[Any]) -> str:
    """Build a human-readable criteria string from a list of FilterItem dicts."""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        field = item.get("field") or ""
        op = item.get("operation") or ""
        value = item.get("value") or ""
        parts.append(f"{field} {op} {value}".strip())
    return " AND ".join(parts)


def _shared_with(rule: dict[str, Any]) -> str | None:
    """Extract a human-readable 'shared with' label from sharedTo."""
    shared_to: dict[str, Any] = rule.get("sharedTo") or {}
    if not isinstance(shared_to, dict):
        return None
    # Try the most common targets in order
    for key in ("group", "role", "roleAndSubordinates", "publicGroups", "guestUser"):
        val = shared_to.get(key)
        if val:
            label = val if isinstance(val, str) else ", ".join(_as_list(val))
            return label
    # Fallback: return first non-None value
    for val in shared_to.values():
        if val:
            return str(val)
    return None


def _parse_criteria_rules(rules_raw: list[Any]) -> list[SharingRuleSpec]:
    specs: list[SharingRuleSpec] = []
    for rule in rules_raw:
        if not isinstance(rule, dict):
            continue
        full_name = rule.get("fullName") or ""
        if not full_name:
            continue
        criteria = _criteria_string(_as_list(rule.get("criteriaItems")))
        specs.append(
            SharingRuleSpec(
                name=full_name,
                rule_type="criteria",
                criteria=criteria or None,
                shared_with=_shared_with(rule),
                access_level=_map_access_level(rule.get("accessLevel")),
            )
        )
    return specs


def _parse_owner_rules(rules_raw: list[Any]) -> list[SharingRuleSpec]:
    specs: list[SharingRuleSpec] = []
    for rule in rules_raw:
        if not isinstance(rule, dict):
            continue
        full_name = rule.get("fullName") or ""
        if not full_name:
            continue
        specs.append(
            SharingRuleSpec(
                name=full_name,
                rule_type="owner",
                criteria=None,
                shared_with=_shared_with(rule),
                access_level=_map_access_level(rule.get("accessLevel")),
            )
        )
    return specs


def _parse_grant_access(raw: dict[str, Any]) -> bool | None:
    """Extract ``grantAccessUsingHierarchies`` from a CustomObject payload.

    The Metadata API returns the field as a boolean (True/False) or as the
    string ``"true"``/``"false"`` depending on the deserialisation layer.
    When the field is absent (standard objects, Public sharing model) we
    return ``None`` so the template can render "—".
    """
    value = raw.get("grantAccessUsingHierarchies")
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    # String form from some XML parsers
    if isinstance(value, str):
        return value.lower() == "true"
    return None


async def fetch(client: SalesforceClient, object_api_name: str) -> SharingSpec | None:
    """Fetch OWD and sharing rules for *object_api_name*.

    Returns ``None`` only on a catastrophic error; partial data is returned
    as a :class:`~ds_tool.models.SharingSpec` with whatever was readable.
    """
    owd_internal: str | None = None
    owd_external: str | None = None
    grant_access_using_hierarchies: bool | None = None
    rules: list[SharingRuleSpec] = []

    # --- OWD from CustomObject ---
    try:
        custom_obj_records = await client.read_metadata("CustomObject", [object_api_name])
        if custom_obj_records:
            raw = custom_obj_records[0]
            owd_internal = raw.get("sharingModel") or None
            owd_external = raw.get("externalSharingModel") or None
            # grantAccessUsingHierarchies: present for custom objects with non-Public
            # sharing model; absent (→ None) for standard objects and Public OWD.
            grant_access_using_hierarchies = _parse_grant_access(raw)
    except Exception:
        pass  # tolerate; OWD stays None

    # --- Sharing rules ---
    try:
        sharing_records = await client.read_metadata("SharingRules", [object_api_name])
        for raw in sharing_records:
            if not isinstance(raw, dict):
                continue
            rules.extend(_parse_criteria_rules(_as_list(raw.get("sharingCriteriaRules"))))
            rules.extend(_parse_owner_rules(_as_list(raw.get("sharingOwnerRules"))))
    except Exception:
        pass  # tolerate; rules stay empty

    # Return None only if we got absolutely nothing
    if owd_internal is None and owd_external is None and not rules:
        return None

    return SharingSpec(
        owd_internal=owd_internal,
        owd_external=owd_external,
        grant_access_using_hierarchies=grant_access_using_hierarchies,
        rules=rules,
    )
