from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import sharing


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def test_map_access_level_edit_becomes_read_write() -> None:
    from ds_tool.metadata.sharing import _map_access_level

    assert _map_access_level("Edit") == "Read/Write"
    assert _map_access_level("Read") == "Read"
    assert _map_access_level("Read Only") == "Read"
    assert _map_access_level(None) is None


def test_criteria_string_joins_filter_items() -> None:
    from ds_tool.metadata.sharing import _criteria_string

    items = [
        {"field": "Status__c", "operation": "equals", "value": "Active"},
        {"field": "Amount", "operation": "greaterThan", "value": "1000"},
    ]
    result = _criteria_string(items)
    assert result == "Status__c equals Active AND Amount greaterThan 1000"


def test_criteria_string_empty_on_empty_list() -> None:
    from ds_tool.metadata.sharing import _criteria_string

    assert _criteria_string([]) == ""


def test_shared_with_extracts_group() -> None:
    from ds_tool.metadata.sharing import _shared_with

    rule = {"sharedTo": {"group": "Sales_Team"}}
    assert _shared_with(rule) == "Sales_Team"


def test_shared_with_returns_none_on_empty() -> None:
    from ds_tool.metadata.sharing import _shared_with

    assert _shared_with({}) is None
    assert _shared_with({"sharedTo": {}}) is None


# ---------------------------------------------------------------------------
# fetch – full happy path (OWD + both rule types)
# ---------------------------------------------------------------------------


def test_fetch_parses_owd_and_criteria_rules() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            # CustomObject response
            [
                {
                    "fullName": "Account",
                    "sharingModel": "ReadWrite",
                    "externalSharingModel": "Private",
                }
            ],
            # SharingRules response
            [
                {
                    "fullName": "Account",
                    "sharingCriteriaRules": [
                        {
                            "fullName": "Account.Active_Criteria_Rule",
                            "accessLevel": "Edit",
                            "sharedTo": {"group": "Sales_Group"},
                            "criteriaItems": [
                                {
                                    "field": "Status__c",
                                    "operation": "equals",
                                    "value": "Active",
                                }
                            ],
                        }
                    ],
                    "sharingOwnerRules": [],
                }
            ],
        ]
    )
    spec = _run(sharing.fetch(client, "Account"))
    assert spec is not None
    assert spec.owd_internal == "ReadWrite"
    assert spec.owd_external == "Private"
    assert len(spec.rules) == 1
    rule = spec.rules[0]
    assert rule.name == "Account.Active_Criteria_Rule"
    assert rule.rule_type == "criteria"
    assert rule.criteria == "Status__c equals Active"
    assert rule.shared_with == "Sales_Group"
    assert rule.access_level == "Read/Write"


def test_fetch_parses_owner_rules() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            # CustomObject
            [{"fullName": "Opportunity", "sharingModel": "Private", "externalSharingModel": None}],
            # SharingRules
            [
                {
                    "fullName": "Opportunity",
                    "sharingCriteriaRules": None,
                    "sharingOwnerRules": [
                        {
                            "fullName": "Opportunity.Owner_Rule",
                            "accessLevel": "Read",
                            "sharedTo": {"role": "VP_Sales"},
                        }
                    ],
                }
            ],
        ]
    )
    spec = _run(sharing.fetch(client, "Opportunity"))
    assert spec is not None
    assert spec.owd_internal == "Private"
    assert spec.owd_external is None
    assert len(spec.rules) == 1
    rule = spec.rules[0]
    assert rule.rule_type == "owner"
    assert rule.criteria is None
    assert rule.shared_with == "VP_Sales"
    assert rule.access_level == "Read"


def test_fetch_single_dict_sharing_rules_treated_as_list() -> None:
    """A single dict (not a list) for sharingCriteriaRules must still be parsed."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            [{"fullName": "Case", "sharingModel": "Read", "externalSharingModel": "Private"}],
            [
                {
                    "fullName": "Case",
                    # Metadata API sometimes returns a single dict instead of a list
                    "sharingCriteriaRules": {
                        "fullName": "Case.Single_Rule",
                        "accessLevel": "Read",
                        "sharedTo": {"group": "Support"},
                        "criteriaItems": [],
                    },
                    "sharingOwnerRules": None,
                }
            ],
        ]
    )
    spec = _run(sharing.fetch(client, "Case"))
    assert spec is not None
    assert len(spec.rules) == 1
    assert spec.rules[0].name == "Case.Single_Rule"
    assert spec.rules[0].rule_type == "criteria"


# ---------------------------------------------------------------------------
# fetch – resilience / error cases
# ---------------------------------------------------------------------------


def test_fetch_returns_none_when_both_calls_fail() -> None:
    client = MagicMock()
    client.read_metadata = AsyncMock(side_effect=RuntimeError("SOAP fault"))
    result = _run(sharing.fetch(client, "Account"))
    assert result is None


def test_fetch_returns_partial_spec_when_sharing_rules_fail() -> None:
    """OWD succeeds but SharingRules call raises — return partial SharingSpec."""
    client = MagicMock()

    async def _side_effect(type_name, _full_names):
        if type_name == "CustomObject":
            return [{"fullName": "Lead", "sharingModel": "Private", "externalSharingModel": "Private"}]
        raise RuntimeError("SharingRules call failed")

    client.read_metadata = AsyncMock(side_effect=_side_effect)
    spec = _run(sharing.fetch(client, "Lead"))
    assert spec is not None
    assert spec.owd_internal == "Private"
    assert spec.rules == []


def test_fetch_returns_rules_when_custom_object_fails() -> None:
    """CustomObject call raises but SharingRules succeeds — OWD is None, rules populated."""
    client = MagicMock()

    async def _side_effect(type_name, _full_names):
        if type_name == "CustomObject":
            raise RuntimeError("CustomObject call failed")
        return [
            {
                "fullName": "Contact",
                "sharingCriteriaRules": [
                    {
                        "fullName": "Contact.Some_Rule",
                        "accessLevel": "Edit",
                        "sharedTo": {"group": "All_Internal_Users"},
                        "criteriaItems": [],
                    }
                ],
                "sharingOwnerRules": None,
            }
        ]

    client.read_metadata = AsyncMock(side_effect=_side_effect)
    spec = _run(sharing.fetch(client, "Contact"))
    assert spec is not None
    assert spec.owd_internal is None
    assert len(spec.rules) == 1
    assert spec.rules[0].name == "Contact.Some_Rule"
    assert spec.rules[0].access_level == "Read/Write"


def test_fetch_returns_none_on_empty_results() -> None:
    """Both calls succeed but return empty lists — should return None."""
    client = MagicMock()
    client.read_metadata = AsyncMock(return_value=[])
    result = _run(sharing.fetch(client, "CustomObj__c"))
    assert result is None


def test_fetch_owd_only_returns_spec() -> None:
    """Only OWD present (no rules) — SharingSpec is returned (not None)."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            [{"fullName": "Account", "sharingModel": "Public", "externalSharingModel": "Private"}],
            [],  # no sharing rules
        ]
    )
    spec = _run(sharing.fetch(client, "Account"))
    assert spec is not None
    assert spec.owd_internal == "Public"
    assert spec.rules == []


# ---------------------------------------------------------------------------
# grant_access_using_hierarchies
# ---------------------------------------------------------------------------


def test_fetch_grant_access_using_hierarchies_true_bool() -> None:
    """Boolean True in payload → spec.grant_access_using_hierarchies is True."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            [
                {
                    "fullName": "MyObj__c",
                    "sharingModel": "Private",
                    "externalSharingModel": "Private",
                    "grantAccessUsingHierarchies": True,
                }
            ],
            [],  # no sharing rules
        ]
    )
    spec = _run(sharing.fetch(client, "MyObj__c"))
    assert spec is not None
    assert spec.grant_access_using_hierarchies is True


def test_fetch_grant_access_using_hierarchies_false_bool() -> None:
    """Boolean False in payload → spec.grant_access_using_hierarchies is False."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            [
                {
                    "fullName": "MyObj__c",
                    "sharingModel": "Private",
                    "externalSharingModel": "Private",
                    "grantAccessUsingHierarchies": False,
                }
            ],
            [],
        ]
    )
    spec = _run(sharing.fetch(client, "MyObj__c"))
    assert spec is not None
    assert spec.grant_access_using_hierarchies is False


def test_fetch_grant_access_using_hierarchies_string_true() -> None:
    """String 'true' from XML parser → spec.grant_access_using_hierarchies is True."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            [
                {
                    "fullName": "MyObj__c",
                    "sharingModel": "ReadWrite",
                    "externalSharingModel": None,
                    "grantAccessUsingHierarchies": "true",
                }
            ],
            [],
        ]
    )
    spec = _run(sharing.fetch(client, "MyObj__c"))
    assert spec is not None
    assert spec.grant_access_using_hierarchies is True


def test_fetch_grant_access_using_hierarchies_string_false() -> None:
    """String 'false' from XML parser → spec.grant_access_using_hierarchies is False."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            [
                {
                    "fullName": "MyObj__c",
                    "sharingModel": "Private",
                    "externalSharingModel": "Private",
                    "grantAccessUsingHierarchies": "false",
                }
            ],
            [],
        ]
    )
    spec = _run(sharing.fetch(client, "MyObj__c"))
    assert spec is not None
    assert spec.grant_access_using_hierarchies is False


def test_fetch_grant_access_using_hierarchies_absent_is_none() -> None:
    """Field absent from payload (standard objects, Public OWD) → None."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            # No grantAccessUsingHierarchies key in payload
            [
                {
                    "fullName": "Account",
                    "sharingModel": "ReadWrite",
                    "externalSharingModel": "Private",
                }
            ],
            [],
        ]
    )
    spec = _run(sharing.fetch(client, "Account"))
    assert spec is not None
    assert spec.grant_access_using_hierarchies is None


def test_fetch_grant_access_using_hierarchies_none_value_is_none() -> None:
    """Explicit None value in payload → spec.grant_access_using_hierarchies is None."""
    client = MagicMock()
    client.read_metadata = AsyncMock(
        side_effect=[
            [
                {
                    "fullName": "Account",
                    "sharingModel": "ReadWrite",
                    "externalSharingModel": None,
                    "grantAccessUsingHierarchies": None,
                }
            ],
            [],
        ]
    )
    spec = _run(sharing.fetch(client, "Account"))
    assert spec is not None
    assert spec.grant_access_using_hierarchies is None


def test_parse_grant_access_helper() -> None:
    """Unit-test _parse_grant_access directly for all input variants."""
    from ds_tool.metadata.sharing import _parse_grant_access

    assert _parse_grant_access({}) is None
    assert _parse_grant_access({"grantAccessUsingHierarchies": None}) is None
    assert _parse_grant_access({"grantAccessUsingHierarchies": True}) is True
    assert _parse_grant_access({"grantAccessUsingHierarchies": False}) is False
    assert _parse_grant_access({"grantAccessUsingHierarchies": "true"}) is True
    assert _parse_grant_access({"grantAccessUsingHierarchies": "false"}) is False
    assert _parse_grant_access({"grantAccessUsingHierarchies": "True"}) is True
    assert _parse_grant_access({"grantAccessUsingHierarchies": "FALSE"}) is False
