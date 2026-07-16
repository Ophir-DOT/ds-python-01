from __future__ import annotations

from ds_tool.cache import ProfileCache
from ds_tool.models import FieldPermission, ObjectPermission, ProfileSpec


def _profile(name: str) -> ProfileSpec:
    return ProfileSpec(
        full_name=name,
        label=name,
        kind="Profile",
        object_permissions=[
            ObjectPermission(obj="Account", read=True),
            ObjectPermission(obj="Opportunity", read=True, edit=True),
        ],
        field_permissions=[
            FieldPermission(field="Account.Name", readable=True, editable=True),
            FieldPermission(field="Opportunity.Amount", readable=True, editable=False),
            FieldPermission(field="Contact.Email", readable=True),
        ],
    )


def test_for_object_filters_object_and_field_perms() -> None:
    cache = ProfileCache()
    cache.populate([_profile("Admin"), _profile("Sales")])

    account_views = cache.for_object("Account")
    assert len(account_views) == 2
    for view in account_views:
        # Only the Account row remains in object_permissions
        assert [op.obj for op in view.object_permissions] == ["Account"]
        # FLS pruned to fields prefixed with the object name
        assert all(fp.field.startswith("Account.") for fp in view.field_permissions)
        assert any(fp.field == "Account.Name" for fp in view.field_permissions)

    opp_views = cache.for_object("Opportunity")
    assert all(
        [op.obj for op in v.object_permissions] == ["Opportunity"] for v in opp_views
    )


def test_populate_is_idempotent_for_same_name() -> None:
    cache = ProfileCache()
    cache.populate([_profile("Admin")])
    cache.populate([_profile("Admin")])
    assert len(cache.all()) == 1
