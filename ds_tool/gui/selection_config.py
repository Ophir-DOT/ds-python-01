"""(De)serialization for the Design-Spec selection export/import feature.

Deliberately free of PySide6 imports so the round-trip logic is unit-testable
headlessly. The GUI tab (`tabs/design_spec.py`) calls these to read/write the
small JSON file that captures the user's chosen objects + profiles/permission
sets.
"""

from __future__ import annotations

from typing import Any

SELECTION_VERSION = 1


def build_selection_payload(objects: list[str], profiles: list[str]) -> dict[str, Any]:
    """Build the JSON-serializable selection config."""
    return {
        "version": SELECTION_VERSION,
        "objects": list(objects),
        "profiles_permission_sets": list(profiles),
    }


def parse_selection_payload(data: Any) -> tuple[list[str], list[str]]:
    """Extract (objects, profiles) from parsed JSON.

    Tolerates the legacy "profiles" key. Raises ValueError on a bad shape so the
    caller can surface a clean error.
    """
    if not isinstance(data, dict):
        raise ValueError("Selection file must be a JSON object.")
    objects = [str(k) for k in (data.get("objects") or [])]
    raw_profiles = data.get("profiles_permission_sets")
    if raw_profiles is None:
        raw_profiles = data.get("profiles") or []
    profiles = [str(k) for k in raw_profiles]
    return objects, profiles
