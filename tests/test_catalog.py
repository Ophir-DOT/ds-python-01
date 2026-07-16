from __future__ import annotations

from ds_tool.metadata.catalog import (
    _reportable,
    list_objects,
    list_profiles_permsets,
)


class _Creds:
    api_version = "59.0"


class FakeClient:
    creds = _Creds()

    def __init__(self, sobjects=None, profiles=None, permsets=None) -> None:
        self._sobjects = sobjects or []
        self._profiles = profiles or []
        self._permsets = permsets or []

    async def rest_get(self, path, params=None):
        return {"sobjects": self._sobjects}

    async def query_all(self, soql):
        return self._profiles if "FROM Profile" in soql else self._permsets


def test_reportable_excludes_system_suffixes() -> None:
    assert _reportable({"name": "Account", "queryable": True})
    assert not _reportable({"name": "Account__Share", "queryable": True})
    assert not _reportable({"name": "Thing__mdt", "queryable": True})
    assert not _reportable({"name": "NoQuery__c", "queryable": False})


async def test_list_objects_filters_and_sorts() -> None:
    client = FakeClient(
        sobjects=[
            {"name": "Zebra__c", "label": "Zebra", "custom": True, "queryable": True},
            {"name": "Account", "label": "Account", "custom": False, "queryable": True},
            {"name": "Account__History", "label": "h", "queryable": True},
            {"name": "Lead__ChangeEvent", "label": "c", "queryable": True},
        ]
    )
    refs = await list_objects(client)
    assert [r.api_name for r in refs] == ["Account", "Zebra__c"]  # sorted by label
    assert refs[0].custom is False and refs[1].custom is True


async def test_list_profiles_permsets_tags_kind() -> None:
    client = FakeClient(
        profiles=[{"Id": "1", "Name": "System Administrator"}],
        permsets=[{"Id": "2", "Name": "Sales_PS", "Label": "Sales"}],
    )
    refs = await list_profiles_permsets(client)
    pairs = {(r.name, r.kind) for r in refs}
    assert ("System Administrator", "Profile") in pairs
    assert ("Sales_PS", "PermissionSet") in pairs
