"""Field definitions from the REST describe endpoint."""

from __future__ import annotations

import re
from typing import Any

from ..client import SalesforceClient
from ..models import FieldSpec

# Friendly display names for the base SOAP types exposed by the REST describe API.
_BASE_TYPE_LABELS: dict[str, str] = {
    "string": "Text",
    "textarea": "Text Area",
    "email": "Email",
    "phone": "Phone",
    "url": "URL",
    "boolean": "Checkbox",
    "int": "Number",
    "double": "Number",
    "currency": "Currency",
    "percent": "Percent",
    "date": "Date",
    "datetime": "Date/Time",
    "time": "Time",
    "picklist": "Picklist",
    "multipicklist": "Multi-Select Picklist",
    "reference": "Lookup",
    "id": "ID",
    "base64": "File",
    "encryptedstring": "Encrypted Text",
    "combobox": "Combobox",
    "anytype": "Any Type",
    "address": "Address",
    "location": "Geolocation",
    "complexvalue": "Complex Value",
}

# Regex that matches a managed-package namespace prefix, e.g. "CompSuite__" or "ns__".
# A namespace prefix is one or more word chars followed by double underscore, appearing
# at the start of the API name — BEFORE the field's own custom suffix (__c / __r / __s …).
# Standard fields never contain "__"; custom unmanaged fields end with exactly one "__c"
# at the tail; package fields have at least two "__" segments.
_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9]+__")


def _semantic_type(
    raw: dict[str, Any],
    rollup_names: frozenset[str] | None = None,
    meta_formula: str | None = None,
) -> str:
    """Return a human-readable semantic type label for a field describe dict.

    Rules applied in priority order:

    1. ``autoNumber`` is ``True``  →  "AutoNumber"
       (AutoNumber fields have type "string" in the REST describe, so we must
       check this flag first.)

    2. Roll-Up Summary vs Formula disambiguation for ``calculated=True`` fields,
       and Roll-Up Summary detection for non-calculated fields that appear in
       *rollup_names*:

       Roll-Up Summary classification is POSITIVE — a field is only labeled
       "Roll-Up Summary" when there is explicit evidence of ``summaryOperation``
       from the Tooling API ``FieldDefinition`` query or the Metadata API
       ``CustomField.summaryOperation`` element.  These confirmed roll-up field
       names are collected in *rollup_names* before this function is called.

       For ``calculated=True`` fields:

       a. api_name is in *rollup_names* (positive summaryOperation evidence
          from the Tooling API or the Metadata API CustomField record)
          →  "Roll-Up Summary"

       b. ``calculatedFormula`` is non-empty (from the describe)
          →  "Formula (<Base>)"

       c. *meta_formula* is non-empty (Metadata API ``CustomField.formula``
          confirmed it is a formula — e.g. a date/datetime formula field whose
          formula text is not returned by the REST describe)
          →  "Formula (<Base>)"

       d. Neither formula text nor positive summaryOperation evidence available
          (metadata read may have failed or returned nothing)
          →  "Formula (<Base>)" as a safe fallback.  We NEVER infer Roll-Up
          Summary by elimination; doing so would mislabel date/datetime formula
          fields whose formula is temporarily unavailable.

    3. Non-calculated Roll-Up Summary: if *rollup_names* is non-empty and the
       api_name appears there, the field is tagged "Roll-Up Summary" even if
       ``calculated`` is not set in the describe.  This covers rare edge cases.

    4. ``type == "textarea"`` and ``htmlFormatted == True``  →  "Rich Text Area"
       Plain textarea without htmlFormatted falls through to rule 5.

    5. Fallback: look up the raw SOAP type in ``_BASE_TYPE_LABELS``; if not
       found, return the raw type string capitalised (e.g. "Masterdetail").
    """
    raw_type: str = raw.get("type", "")
    api_name: str = raw.get("name", "")

    # Rule 1 — AutoNumber
    if raw.get("autoNumber"):
        return "AutoNumber"

    # Rules 2a/b/c/d — Calculated fields: formula vs. roll-up disambiguation.
    if raw.get("calculated"):
        # Rule 2a — POSITIVE roll-up evidence: api_name confirmed in rollup_names.
        # rollup_names is populated from summaryOperation fields in the Tooling API
        # FieldDefinition query and/or the Metadata API CustomField records.
        if rollup_names and api_name in rollup_names:
            return "Roll-Up Summary"

        # Rules 2b/c/d — True formula field (or safe fallback).
        # Whether or not formula text is available, this is always a Formula field.
        # We never infer Roll-Up Summary by absence of formula text.
        base = _BASE_TYPE_LABELS.get(raw_type, raw_type.capitalize() if raw_type else "")
        return f"Formula ({base})" if base else "Formula"

    # Rule 3 — Non-calculated Roll-Up Summary: positive Tooling/Metadata API signal.
    # (covers fields that might not be flagged calculated=True in the describe).
    if rollup_names and api_name in rollup_names:
        return "Roll-Up Summary"

    # Rule 4 — Rich Text Area (textarea with htmlFormatted=True)
    if raw_type == "textarea" and raw.get("htmlFormatted"):
        return "Rich Text Area"

    # Rule 5 — Friendly base-type label
    return _BASE_TYPE_LABELS.get(raw_type, raw_type.capitalize() if raw_type else "")


def _classify(api_name: str, obj_namespace: str | None = None) -> str:
    """Return "Package", "Custom", or "Standard" for a field API name.

    Classification rules (WI-03):
    - "Standard"  — no trailing ``__c`` (standard field, no custom suffix).
    - "Package"   — ends with ``__c`` AND has a namespace prefix in the API name
                    matching ``^[A-Za-z0-9]+__`` (two or more ``__`` segments),
                    e.g. ``CompSuite__Count_Open_Action_Items__c``.
                    If *obj_namespace* is supplied (the managed namespace of the
                    parent object), we use it as a cross-check; otherwise the
                    presence of ``__`` before the ``__c`` suffix is sufficient.
    - "Custom"    — ends with ``__c`` but has no managed namespace prefix
                    (unmanaged custom field), e.g. ``Status__c``.
    """
    if not api_name.endswith("__c"):
        return "Standard"

    # Strip the trailing __c to examine the remainder.
    body = api_name[:-3]  # e.g. "CompSuite__Count_Open_Action_Items"

    # If the body still contains "__", a namespace prefix is present.
    if "__" in body and _NAMESPACE_RE.match(api_name):
        return "Package"

    return "Custom"


async def _fetch_rollup_field_names(
    client: SalesforceClient,
    object_api_name: str,
) -> frozenset[str]:
    """Query Tooling API for Roll-Up Summary field API names on *object_api_name*.

    Uses ``FieldDefinition`` where ``SummaryOperation != null``.  Returns an
    empty frozenset on any error so callers fall back gracefully.

    NOTE: For managed-package fields (e.g. CompSuite__Count_Open_Action_Items__c)
    the Tooling API ``FieldDefinition.SummaryOperation`` is often inaccessible
    and returns an empty result set.  The primary roll-up detection in
    ``_semantic_type`` (``calculated=True`` AND no ``calculatedFormula``) is
    more reliable and does not require this query.  This secondary lookup is
    retained as a belt-and-suspenders fallback.
    """
    soql = (
        f"SELECT QualifiedApiName, SummaryOperation "
        f"FROM FieldDefinition "
        f"WHERE EntityDefinition.QualifiedApiName = '{object_api_name}' "
        f"AND SummaryOperation != null"
    )
    try:
        result = await client.tooling_query(soql)
        records = result.get("records", [])
        return frozenset(r["QualifiedApiName"] for r in records if r.get("QualifiedApiName"))
    except Exception:
        # Tooling query may fail (insufficient access, unsupported API version,
        # network error).  Degrade gracefully to no roll-up detection.
        return frozenset()


async def _fetch_formula_expressions(
    client: SalesforceClient,
    object_api_name: str,
    calculated_field_names: list[str],
) -> tuple[dict[str, str], frozenset[str]]:
    """Fetch formula expressions and roll-up confirmation from the Metadata API.

    The REST describe endpoint populates ``calculatedFormula`` for some field
    types (text, number, currency, percent, checkbox) but NOT for date and
    datetime formula fields.  The Metadata API ``CustomField`` type always
    carries the ``formula`` element for formula fields and the
    ``summaryOperation`` element for Roll-Up Summary fields.

    Returns a 2-tuple:

    - ``formula_map``: mapping of field API name → formula string for fields
      where the Metadata API returned a non-empty ``formula`` element.
    - ``metadata_rollup_names``: frozenset of field API names where the
      Metadata API returned a non-empty ``summaryOperation`` element.  These
      are confirmed Roll-Up Summary fields.

    Both collections are empty on any error so callers degrade gracefully.

    The full name for a CustomField is ``<ObjectApiName>.<FieldApiName>``, e.g.
    ``Change_Control__c.Max_Action_Due_Date__c``.
    """
    if not calculated_field_names:
        return {}, frozenset()
    full_names = [f"{object_api_name}.{fn}" for fn in calculated_field_names]
    try:
        records = await client.read_metadata("CustomField", full_names)
    except Exception:
        # Metadata API failures (auth, unsupported type, network) must not
        # block field collection.
        return {}, frozenset()

    formula_result: dict[str, str] = {}
    rollup_result: set[str] = set()
    for rec in records:
        # The Metadata API returns the field's own API name (without the object
        # prefix) in the ``fullName`` element as "<Object>.<Field>".
        full_name: str = rec.get("fullName", "")
        field_name = full_name.split(".", 1)[-1] if "." in full_name else full_name
        if not field_name:
            continue

        # Capture formula text for formula fields (e.g. date/datetime formulas
        # whose calculatedFormula is absent from the REST describe).
        formula_text: str = rec.get("formula", "") or ""
        formula_text = formula_text.strip()
        if formula_text:
            formula_result[field_name] = formula_text

        # Capture Roll-Up Summary evidence. A non-empty summaryOperation OR
        # summaryForeignKey is POSITIVE proof this is a roll-up field (these
        # elements appear ONLY on roll-up summaries, never on formula fields).
        summary_op: str = (rec.get("summaryOperation") or "").strip()
        summary_fk: str = (rec.get("summaryForeignKey") or "").strip()
        if summary_op or summary_fk:
            rollup_result.add(field_name)

    return formula_result, frozenset(rollup_result)


async def fetch(
    client: SalesforceClient,
    object_api_name: str,
    *,
    history_tracked: set[str] | None = None,
) -> list[FieldSpec]:
    """Fetch all fields for *object_api_name* and return FieldSpec instances.

    Three async calls are made concurrently:
    1. REST describe — field attributes.
    2. Tooling FieldDefinition query — secondary roll-up detection.
    3. (deferred) Metadata API CustomField read — formula expressions for
       calculated fields whose ``calculatedFormula`` is absent in the describe.
    """
    import asyncio as _asyncio

    describe, rollup_names = await _asyncio.gather(
        client.describe(object_api_name),
        _fetch_rollup_field_names(client, object_api_name),
    )
    raw_fields: list[dict[str, Any]] = describe.get("fields", [])

    # Identify calculated fields that lack a calculatedFormula in the describe.
    # We batch-read all such fields via the Metadata API to recover:
    #   - ``formula`` elements for true formula fields (e.g. date/datetime
    #     formula fields whose calculatedFormula is absent from the REST describe).
    #   - ``summaryOperation`` elements for Roll-Up Summary fields, providing
    #     POSITIVE evidence for roll-up classification (not by elimination).
    fields_needing_metadata = [
        f["name"]
        for f in raw_fields
        if f.get("calculated")
        and not (f.get("calculatedFormula") and str(f.get("calculatedFormula", "")).strip())
    ]
    formula_map, metadata_rollup_names = await _fetch_formula_expressions(
        client, object_api_name, fields_needing_metadata
    )

    # Merge Tooling-detected rollup names with Metadata-API-confirmed rollup names
    # so that _semantic_type has a single unified set of positively-confirmed rollups.
    combined_rollup_names = rollup_names | metadata_rollup_names

    tracked = history_tracked or set()
    return [
        _to_field(f, tracked, rollup_names=combined_rollup_names, formula_map=formula_map)
        for f in raw_fields
    ]


def _to_field(
    raw: dict[str, Any],
    tracked: set[str],
    *,
    rollup_names: frozenset[str] | None = None,
    formula_map: dict[str, str] | None = None,
) -> FieldSpec:
    picklist_values = [
        v.get("value") for v in raw.get("picklistValues", []) if v.get("active", True)
    ]
    api_name: str = raw["name"]

    # Resolve the formula expression.  Prefer the REST describe value
    # (``calculatedFormula``); fall back to the Metadata API value from
    # *formula_map* (populated for fields where describe returned nothing).
    describe_formula: str | None = raw.get("calculatedFormula") or None
    if describe_formula and not str(describe_formula).strip():
        describe_formula = None
    meta_formula: str | None = (formula_map or {}).get(api_name) or None
    formula = describe_formula or meta_formula

    return FieldSpec(
        api_name=api_name,
        label=raw.get("label", api_name),
        type=_semantic_type(raw, rollup_names, meta_formula),
        length=raw.get("length") or None,
        required=not raw.get("nillable", True) and not raw.get("defaultedOnCreate", False),
        unique=bool(raw.get("unique")),
        external_id=bool(raw.get("externalId")),
        history_tracked=api_name in tracked,
        formula=formula,
        help_text=raw.get("inlineHelpText"),
        default_value=_extract_default(raw),
        picklist_values=[v for v in picklist_values if v],
        reference_to=list(raw.get("referenceTo") or []),
        classification=_classify(api_name),
    )


def _extract_default(raw: dict[str, Any]) -> str | None:
    """Return the field's default value, preferring a literal value over a formula.

    The REST describe endpoint exposes:
      - ``defaultValue``        — a literal default (e.g. ``"false"``, ``"0"``).
      - ``defaultValueFormula`` — a formula string when the default is computed
                                  (e.g. ``"TODAY()"``).

    Both may be present (rare), in which case ``defaultValue`` takes precedence
    because it is the resolved literal. Returns ``None`` when neither is set.
    """
    literal = raw.get("defaultValue")
    if literal is not None and str(literal).strip():
        return str(literal)
    formula = raw.get("defaultValueFormula")
    if formula is not None and str(formula).strip():
        return str(formula)
    return None
