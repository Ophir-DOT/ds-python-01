from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import flows


def _run(coro):
    return asyncio.run(coro)


def _client(view_records, durable_id="01Iabc000000001"):
    """fetch() calls client.query twice: EntityDefinition durable id, then FlowDefinitionView."""
    client = MagicMock()
    client.query = AsyncMock(
        side_effect=[
            {"records": [{"DurableId": durable_id}] if durable_id else []},
            {"records": view_records},
        ]
    )
    return client


def test_fetch_parses_record_triggered_flows() -> None:
    view_records = [
        {
            "ApiName": "Restrict_Implementation_State",
            "Label": "Xact | Change Control | Restrict Implementation State",
            "ProcessType": "AutoLaunchedFlow",
            "IsActive": True,
            "Description": "Restrict transitions",
            "ManageableState": "unmanaged",
        },
        {
            "ApiName": "Notify_Owner",
            "Label": "Dot Xpress | Change Control notification",
            "ProcessType": "AutoLaunchedFlow",
            "IsActive": False,
            "Description": None,
            "ManageableState": "installed",
        },
    ]
    specs = _run(flows.fetch(_client(view_records), "CompSuite__Change_Control__c"))
    assert [s.api_name for s in specs] == ["Restrict_Implementation_State", "Notify_Owner"]
    assert specs[0].status == "Active"
    assert specs[1].status == "Inactive"
    assert specs[0].process_type == "AutoLaunchedFlow"
    assert specs[0].package_state == "Unmanaged"
    assert specs[1].package_state == "Managed - Installed"


def test_fetch_queries_by_durable_id_via_standard_api() -> None:
    client = _client([], durable_id="01I5j0000008XYZ")
    _run(flows.fetch(client, "CompSuite__Change_Control__c"))
    # Standard Query API (not tooling); second query filters FlowDefinitionView by id.
    assert not hasattr(client, "tooling_query") or not client.tooling_query.called
    flow_soql = client.query.await_args_list[1].args[0]
    assert "FlowDefinitionView" in flow_soql
    assert "TriggerObjectOrEventId = '01I5j0000008XYZ'" in flow_soql


def test_fetch_returns_empty_when_object_not_found() -> None:
    client = MagicMock()
    client.query = AsyncMock(return_value={"records": []})
    assert _run(flows.fetch(client, "Bogus__c")) == []


def test_fetch_returns_empty_on_query_error() -> None:
    client = MagicMock()
    client.query = AsyncMock(side_effect=RuntimeError("boom"))
    assert _run(flows.fetch(client, "Account")) == []


def test_package_state_mapping() -> None:
    from ds_tool.metadata.flows import _map_manageable_state

    assert _map_manageable_state("unmanaged") == "Unmanaged"
    assert _map_manageable_state("installed") == "Managed - Installed"
    assert _map_manageable_state("installedEditable") == "Managed - Installed (Editable)"
    assert _map_manageable_state("released") == "Managed - Released"
    assert _map_manageable_state("deprecated") == "Managed - Deprecated"
    assert _map_manageable_state("deprecatedEditable") == "Managed - Deprecated (Editable)"
    assert _map_manageable_state("deleted") == "Managed - Deleted"
    assert _map_manageable_state(None) is None
    # Unknown raw values pass through unchanged.
    assert _map_manageable_state("someFutureState") == "someFutureState"


def test_fetch_package_state_none_when_field_missing() -> None:
    """ManageableState may be absent; package_state must be None, not a KeyError."""
    view_records = [
        {
            "ApiName": "My_Flow",
            "Label": "My Flow",
            "ProcessType": "AutoLaunchedFlow",
            "IsActive": True,
            "Description": None,
            # No ManageableState key
        }
    ]
    specs = _run(flows.fetch(_client(view_records), "Account"))
    assert len(specs) == 1
    assert specs[0].package_state is None
