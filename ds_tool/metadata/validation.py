"""Validation rules via the Metadata API.

The Tooling API exposes `ValidationRule` but its `Metadata` JSON has been
unreliable across orgs/permissions in our user reports — the field comes back
empty even when the rule definitely exists. The SF tool used `readMetadata` for
parity, so we do the same: `listMetadata("ValidationRule")` filtered to the
object's prefix, then `readMetadata` to pull each rule's body.

Reference: `Ctrl_CMP_Configuration_Report.cls:1697-1732` (`getValidationRules`).
"""

from __future__ import annotations

from ..client import SalesforceClient
from ..models import ValidationRuleSpec


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


async def fetch(client: SalesforceClient, object_api_name: str) -> list[ValidationRuleSpec]:
    try:
        listing = await client.list_metadata("ValidationRule")
    except Exception:
        return []

    prefix = f"{object_api_name}."
    full_names = [
        r["fullName"]
        for r in listing
        if isinstance(r.get("fullName"), str) and r["fullName"].startswith(prefix)
    ]
    if not full_names:
        return []

    try:
        raw_rules = await client.read_metadata("ValidationRule", full_names)
    except Exception:
        return []

    specs: list[ValidationRuleSpec] = []
    for raw in raw_rules:
        full_name = raw.get("fullName") or ""
        # Strip the "<object>." prefix; the listing always returns Object.RuleName.
        api_name = full_name.split(".", 1)[-1] if "." in full_name else full_name
        # `active` in the readMetadata payload defaults to True (the API only
        # emits the tag when explicitly false on some org versions).
        active = _bool(raw.get("active")) if raw.get("active") is not None else True
        error_display_field = raw.get("errorDisplayField") or ""
        error_location = error_display_field.strip() if error_display_field.strip() else "Top of Page"
        specs.append(
            ValidationRuleSpec(
                api_name=api_name,
                active=active,
                description=raw.get("description"),
                error_condition=raw.get("errorConditionFormula"),
                error_message=raw.get("errorMessage"),
                error_location=error_location,
            )
        )
    return specs
