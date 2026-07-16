"""Render-time section filtering driven by the GUI 'Settings' exclusions.

The collector always gathers every section; these helpers drop sections from an
`ObjectSpec` just before rendering so users can exclude content from the output
without changing what is collected. Mirrors the Aura 'Settings' tab checkboxes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import ObjectSpec


@dataclass
class ReportSettings:
    exclude_formula_fields_empty_desc: bool = False
    exclude_state_automations: bool = False  # Workflow rules
    exclude_email_alerts: bool = False
    exclude_validation_rules: bool = False
    exclude_related_lists: bool = False  # reserved: no related-list section in model yet
    exclude_date_time: bool = False  # display-only: suppresses generated-on header
    strip_fls_suffix: bool = False  # strip "(Profile)"/"(Permission Set)" from FLS labels
    choose_profiles: bool = False
    selected_profiles: tuple[str, ...] = field(default_factory=tuple)


def apply_exclusions(spec: ObjectSpec, settings: ReportSettings) -> ObjectSpec:
    """Return a copy of `spec` with excluded sections emptied."""
    updates: dict = {}

    if settings.exclude_validation_rules:
        updates["validation_rules"] = []
    if settings.exclude_state_automations:
        updates["workflows"] = []
    if settings.exclude_email_alerts:
        updates["email_alerts"] = []
        updates["email_templates"] = []
    if settings.exclude_formula_fields_empty_desc:
        # "Formula fields with an empty description." We don't store the field
        # description separately, so help_text is the closest proxy.
        updates["fields"] = [
            f
            for f in spec.fields
            if not (f.formula and not (f.help_text or "").strip())
        ]

    return spec.model_copy(update=updates) if updates else spec
