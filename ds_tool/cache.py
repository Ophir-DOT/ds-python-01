"""Per-run, in-memory cache for Profile/PermissionSet metadata.

The current Apex tool re-reads Profile & PermissionSet metadata for every object,
which is the dominant source of latency and the reason users have to "run multiple
times for each object". This module makes those reads happen exactly once per
ds-tool invocation; every per-object collector reads from the cache.
"""

from __future__ import annotations

from threading import Lock
from typing import Iterable

from .models import ProfileSpec


class ProfileCache:
    """Single-pass profile cache. Populate once at run start."""

    def __init__(self) -> None:
        self._by_full_name: dict[str, ProfileSpec] = {}
        self._id_to_name: dict[str, str] = {}
        # Auxiliary Id→Name maps populated lazily by domain collectors (e.g.
        # lifecycle.py loads "states", "groups", "email_templates" once per run).
        self._aux: dict[str, dict[str, str]] = {}
        self._lock = Lock()
        self._populated = False

    def populate(self, profiles: list[ProfileSpec]) -> None:
        with self._lock:
            for spec in profiles:
                self._by_full_name[spec.full_name] = spec
            self._populated = True

    def set_id_to_name(self, mapping: dict[str, str]) -> None:
        """Stash an Id→Name map for Profiles + PermissionSets.

        Life Cycle (legacy 4.3) references profile/permset IDs in CSV columns;
        resolving them to display names requires a Salesforce-Id → Name lookup
        that the cache does not normally hold. Populated lazily once per run by
        the lifecycle collector.

        Each entry is indexed under BOTH its 18-char and 15-char form so lookups
        succeed regardless of which form the caller supplies.
        """
        with self._lock:
            self._id_to_name = {}
            for raw_id, name in mapping.items():
                if not raw_id:
                    continue
                self._id_to_name[raw_id] = name
                if len(raw_id) == 18:
                    self._id_to_name[raw_id[:15]] = name

    @property
    def has_id_map(self) -> bool:
        return bool(self._id_to_name)

    def resolve_ids(self, ids: Iterable[str]) -> list[str]:
        """Return profile/permset display names for the given Salesforce IDs.

        Tolerates both 15- and 18-character IDs by retrying the lookup with the
        ID truncated to 15 chars (Salesforce treats them as equivalent).
        Preserves first-seen order; deduplicates.
        """
        out: list[str] = []
        seen: set[str] = set()
        for raw in ids:
            if not raw:
                continue
            name = self._id_to_name.get(raw) or self._id_to_name.get(raw[:15])
            if name and name not in seen:
                seen.add(name)
                out.append(name)
        return out

    def set_aux(self, name: str, mapping: dict[str, str]) -> None:
        """Register an auxiliary Id→Name lookup, indexed by both 15- and 18-char IDs."""
        with self._lock:
            store: dict[str, str] = {}
            for raw_id, value in mapping.items():
                if not raw_id or value is None:
                    continue
                store[raw_id] = value
                if len(raw_id) == 18:
                    store[raw_id[:15]] = value
            self._aux[name] = store

    def has_aux(self, name: str) -> bool:
        return name in self._aux

    def aux_lookup(self, name: str, value_id: str | None) -> str | None:
        if not value_id:
            return None
        store = self._aux.get(name)
        if not store:
            return None
        return store.get(value_id) or store.get(value_id[:15] if len(value_id) == 18 else value_id)

    @property
    def is_populated(self) -> bool:
        return self._populated

    def all(self) -> list[ProfileSpec]:
        return list(self._by_full_name.values())

    def for_object(self, object_api_name: str) -> list[ProfileSpec]:
        """Return profile/permission-set specs scoped to one object.

        Each ProfileSpec returned is a shallow copy with object_permissions,
        field_permissions, record_type_visibilities, and layout_assignments
        filtered to the rows relevant to `object_api_name`. Layout names in
        the Metadata API are `<object>-<layout label>`, so we filter on that
        prefix for the layout-per-profile section (3.4 in the PDF).
        """
        scoped: list[ProfileSpec] = []
        prefix = f"{object_api_name}."
        layout_prefix = f"{object_api_name}-"
        for spec in self._by_full_name.values():
            obj_perms = [p for p in spec.object_permissions if p.obj == object_api_name]
            field_perms = [
                p for p in spec.field_permissions if p.field.startswith(prefix)
            ]
            record_type_vis = {
                k: v
                for k, v in spec.record_type_visibilities.items()
                if k.startswith(prefix)
            }
            layout_assignments = [
                la for la in spec.layout_assignments if la.layout.startswith(layout_prefix)
            ]
            scoped.append(
                spec.model_copy(
                    update={
                        "object_permissions": obj_perms,
                        "field_permissions": field_perms,
                        "record_type_visibilities": record_type_vis,
                        "layout_assignments": layout_assignments,
                    }
                )
            )
        return scoped
