"""Tests for FieldSpec.default_value population (WI-04, §2 Fields)
and semantic type labels (WI-007, §2 Fields)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import fields
from ds_tool.metadata.fields import _classify, _extract_default, _semantic_type


# ---------------------------------------------------------------------------
# Unit tests for _semantic_type (WI-007)
# ---------------------------------------------------------------------------


def test_semantic_type_auto_number() -> None:
    """autoNumber=True must produce "AutoNumber" regardless of the raw type."""
    raw = {"type": "string", "autoNumber": True, "calculated": False}
    assert _semantic_type(raw) == "AutoNumber"


def test_semantic_type_formula_date() -> None:
    """A calculated field with type "date" AND a calculatedFormula must produce "Formula (Date)".

    The presence of calculatedFormula distinguishes a formula field from a
    Roll-Up Summary: RUS fields have calculated=True but no calculatedFormula.
    """
    raw = {
        "type": "date",
        "autoNumber": False,
        "calculated": True,
        "calculatedFormula": "MAX(Action__r.Due_Date__c)",
    }
    assert _semantic_type(raw) == "Formula (Date)"


def test_semantic_type_formula_text() -> None:
    """A calculated field with type "string" AND a calculatedFormula must produce "Formula (Text)"."""
    raw = {
        "type": "string",
        "autoNumber": False,
        "calculated": True,
        "calculatedFormula": "Name",
    }
    assert _semantic_type(raw) == "Formula (Text)"


def test_semantic_type_formula_number() -> None:
    """A calculated field with type "double" AND a calculatedFormula must produce "Formula (Number)"."""
    raw = {
        "type": "double",
        "autoNumber": False,
        "calculated": True,
        "calculatedFormula": "Qty__c * Price__c",
    }
    assert _semantic_type(raw) == "Formula (Number)"


def test_semantic_type_formula_currency() -> None:
    """A calculated field with type "currency" AND a calculatedFormula must produce "Formula (Currency)"."""
    raw = {
        "type": "currency",
        "autoNumber": False,
        "calculated": True,
        "calculatedFormula": "Amount__c * 0.1",
    }
    assert _semantic_type(raw) == "Formula (Currency)"


def test_semantic_type_plain_string() -> None:
    """A plain text field must map to the friendly label "Text"."""
    raw = {"type": "string", "autoNumber": False, "calculated": False}
    assert _semantic_type(raw) == "Text"


def test_semantic_type_plain_double() -> None:
    """A plain numeric field (double) must map to "Number"."""
    raw = {"type": "double", "autoNumber": False, "calculated": False}
    assert _semantic_type(raw) == "Number"


def test_semantic_type_plain_picklist() -> None:
    raw = {"type": "picklist", "autoNumber": False, "calculated": False}
    assert _semantic_type(raw) == "Picklist"


def test_semantic_type_plain_boolean() -> None:
    raw = {"type": "boolean", "autoNumber": False, "calculated": False}
    assert _semantic_type(raw) == "Checkbox"


def test_semantic_type_reference() -> None:
    raw = {"type": "reference", "autoNumber": False, "calculated": False}
    assert _semantic_type(raw) == "Lookup"


def test_semantic_type_unknown_type_capitalised() -> None:
    """An unrecognised SOAP type should be returned capitalised as a fallback."""
    raw = {"type": "masterdetail", "autoNumber": False, "calculated": False}
    assert _semantic_type(raw) == "Masterdetail"


def test_semantic_type_auto_number_takes_priority_over_calculated() -> None:
    """autoNumber flag must win even when calculated is also True (defensive)."""
    raw = {"type": "string", "autoNumber": True, "calculated": True}
    assert _semantic_type(raw) == "AutoNumber"


def test_semantic_type_missing_flags_defaults_to_friendly_label() -> None:
    """When autoNumber/calculated keys are absent the helper must not raise."""
    raw = {"type": "email"}
    assert _semantic_type(raw) == "Email"


# ---------------------------------------------------------------------------
# Integration: fetch() wires _semantic_type into FieldSpec.type
# ---------------------------------------------------------------------------


def test_fetch_type_auto_number() -> None:
    """fetch() must store "AutoNumber" when the describe has autoNumber=True."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Name",
                    "label": "Change Control Number",
                    "type": "string",
                    "autoNumber": True,
                    "calculated": False,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    specs = asyncio.run(fields.fetch(client, "Change_Control__c"))
    assert specs[0].type == "AutoNumber"


def test_fetch_type_formula_date() -> None:
    """fetch() must store "Formula (Date)" for a calculated date field."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Max_Action_Due_Date__c",
                    "label": "Max Action Due Date",
                    "type": "date",
                    "autoNumber": False,
                    "calculated": True,
                    "calculatedFormula": "MAX(Action__r.Due_Date__c)",
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    specs = asyncio.run(fields.fetch(client, "Change_Control__c"))
    assert specs[0].type == "Formula (Date)"


def test_fetch_type_formula_text() -> None:
    """fetch() must store "Formula (Text)" for a calculated string field."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "CC_Name_Plain_Text__c",
                    "label": "CC Name Plain Text",
                    "type": "string",
                    "autoNumber": False,
                    "calculated": True,
                    "calculatedFormula": "Name",
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    specs = asyncio.run(fields.fetch(client, "Change_Control__c"))
    assert specs[0].type == "Formula (Text)"


def test_fetch_type_plain_field_keeps_friendly_label() -> None:
    """A plain (non-formula, non-autoNumber) field keeps its mapped label."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Status__c",
                    "label": "Status",
                    "type": "picklist",
                    "autoNumber": False,
                    "calculated": False,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    specs = asyncio.run(fields.fetch(client, "Change_Control__c"))
    assert specs[0].type == "Picklist"


# ---------------------------------------------------------------------------
# Unit tests for the _extract_default helper
# ---------------------------------------------------------------------------


def test_extract_default_returns_none_when_absent() -> None:
    assert _extract_default({}) is None


def test_extract_default_returns_literal_value() -> None:
    assert _extract_default({"defaultValue": "false"}) == "false"
    assert _extract_default({"defaultValue": "0"}) == "0"
    assert _extract_default({"defaultValue": "My Default"}) == "My Default"


def test_extract_default_returns_formula_when_no_literal() -> None:
    assert _extract_default({"defaultValueFormula": "TODAY()"}) == "TODAY()"
    assert _extract_default({"defaultValueFormula": "NOW()"}) == "NOW()"


def test_extract_default_prefers_literal_over_formula() -> None:
    """When both keys are present, the literal value takes precedence."""
    raw = {"defaultValue": "some literal", "defaultValueFormula": "TODAY()"}
    assert _extract_default(raw) == "some literal"


def test_extract_default_returns_none_for_empty_strings() -> None:
    assert _extract_default({"defaultValue": ""}) is None
    assert _extract_default({"defaultValueFormula": "   "}) is None


def test_extract_default_coerces_non_string_to_str() -> None:
    """Numeric or boolean defaults from JSON should be coerced to str."""
    assert _extract_default({"defaultValue": 42}) == "42"
    assert _extract_default({"defaultValue": True}) == "True"


# ---------------------------------------------------------------------------
# Integration test: fetch() populates default_value on FieldSpec
# ---------------------------------------------------------------------------


def test_fetch_populates_default_value_literal() -> None:
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Status__c",
                    "label": "Status",
                    "type": "picklist",
                    "defaultValue": "Active",
                    "picklistValues": [],
                    "referenceTo": [],
                },
            ]
        }
    )
    specs = asyncio.run(fields.fetch(client, "MyObject__c"))
    assert len(specs) == 1
    assert specs[0].default_value == "Active"


def test_fetch_populates_default_value_formula() -> None:
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Created_Date__c",
                    "label": "Created Date",
                    "type": "date",
                    "defaultValueFormula": "TODAY()",
                    "picklistValues": [],
                    "referenceTo": [],
                },
            ]
        }
    )
    specs = asyncio.run(fields.fetch(client, "MyObject__c"))
    assert specs[0].default_value == "TODAY()"


def test_fetch_default_value_is_none_when_not_set() -> None:
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Name",
                    "label": "Name",
                    "type": "string",
                    "picklistValues": [],
                    "referenceTo": [],
                },
            ]
        }
    )
    specs = asyncio.run(fields.fetch(client, "Account"))
    assert specs[0].default_value is None


# ---------------------------------------------------------------------------
# G-1: custom_settings_extended_history is always None (left unpopulated)
# ---------------------------------------------------------------------------


def test_fetch_general_leaves_custom_settings_extended_history_none() -> None:
    """ObjectGeneralInfo.custom_settings_extended_history must be None.

    The extended-history flag comes from a DotCompliance-specific custom
    setting (CompSuite__EnvironmentSettings__c) and cannot be derived from
    the standard describe/REST surface.  We verify the collector leaves it
    None so callers / templates know it is not applicable.
    """
    from ds_tool.metadata import objects

    client = MagicMock()
    client.creds = MagicMock()
    client.creds.api_version = "59.0"
    client.rest_get = AsyncMock(
        return_value={
            "objectDescribe": {
                "name": "MyCS__c",
                "label": "My Custom Setting",
                "labelPlural": "My Custom Settings",
            }
        }
    )
    client.describe = AsyncMock(
        return_value={
            "description": None,
            "sharingModel": "Read",
            "trackHistory": False,
        }
    )
    info = asyncio.run(objects.fetch_general(client, "MyCS__c"))
    assert info.custom_settings_extended_history is None


# ---------------------------------------------------------------------------
# WI-01: Rich Text Area detection
# ---------------------------------------------------------------------------


def test_semantic_type_rich_text_area() -> None:
    """A textarea with htmlFormatted=True must produce "Rich Text Area"."""
    raw = {"type": "textarea", "autoNumber": False, "calculated": False, "htmlFormatted": True}
    assert _semantic_type(raw) == "Rich Text Area"


def test_semantic_type_plain_text_area_no_html_formatted() -> None:
    """A textarea without htmlFormatted must remain "Text Area"."""
    raw = {"type": "textarea", "autoNumber": False, "calculated": False, "htmlFormatted": False}
    assert _semantic_type(raw) == "Text Area"


def test_semantic_type_plain_text_area_missing_html_formatted() -> None:
    """A textarea with no htmlFormatted key at all must remain "Text Area"."""
    raw = {"type": "textarea", "autoNumber": False, "calculated": False}
    assert _semantic_type(raw) == "Text Area"


def test_fetch_rich_text_area() -> None:
    """fetch() must label a textarea+htmlFormatted field as "Rich Text Area"."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Xact_Comment__c",
                    "label": "Xact Comment",
                    "type": "textarea",
                    "autoNumber": False,
                    "calculated": False,
                    "htmlFormatted": True,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    client.tooling_query = AsyncMock(return_value={"records": []})
    specs = asyncio.run(fields.fetch(client, "MyObject__c"))
    assert specs[0].type == "Rich Text Area"


# ---------------------------------------------------------------------------
# WI-03: Classification column — _classify() and integration via fetch()
# ---------------------------------------------------------------------------


def test_classify_standard_field() -> None:
    """Standard fields (no __c suffix) must be classified as "Standard"."""
    assert _classify("Name") == "Standard"
    assert _classify("CreatedDate") == "Standard"
    assert _classify("OwnerId") == "Standard"


def test_classify_custom_unmanaged_field() -> None:
    """Unmanaged custom fields (__c, no namespace prefix) must be "Custom"."""
    assert _classify("Status__c") == "Custom"
    assert _classify("My_Field__c") == "Custom"
    assert _classify("Description__c") == "Custom"


def test_classify_package_field() -> None:
    """Managed-package fields (namespace__ prefix + __c suffix) must be "Package"."""
    assert _classify("CompSuite__Count_Open_Action_Items__c") == "Package"
    assert _classify("ns__MyField__c") == "Package"
    assert _classify("PkgA__SomeField__c") == "Package"


def test_fetch_classification_standard() -> None:
    """fetch() must assign classification="Standard" for a standard field."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Name",
                    "label": "Name",
                    "type": "string",
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    client.tooling_query = AsyncMock(return_value={"records": []})
    specs = asyncio.run(fields.fetch(client, "Account"))
    assert specs[0].classification == "Standard"


def test_fetch_classification_custom() -> None:
    """fetch() must assign classification="Custom" for an unmanaged custom field."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Status__c",
                    "label": "Status",
                    "type": "picklist",
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    client.tooling_query = AsyncMock(return_value={"records": []})
    specs = asyncio.run(fields.fetch(client, "MyObject__c"))
    assert specs[0].classification == "Custom"


def test_fetch_classification_package() -> None:
    """fetch() must assign classification="Package" for a managed namespace field."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "CompSuite__Count_Open_Action_Items__c",
                    "label": "Count Open Action Items",
                    "type": "double",
                    "autoNumber": False,
                    "calculated": False,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    client.tooling_query = AsyncMock(return_value={"records": []})
    specs = asyncio.run(fields.fetch(client, "CompSuite__Change_Control__c"))
    assert specs[0].classification == "Package"


# ---------------------------------------------------------------------------
# WI-NEW-C: Roll-Up Summary detection via Tooling API
# ---------------------------------------------------------------------------


def test_semantic_type_rollup_summary() -> None:
    """_semantic_type must return "Roll-Up Summary" when the api name is in rollup_names."""
    raw = {
        "name": "CompSuite__Count_Open_Action_Items__c",
        "type": "double",
        "autoNumber": False,
        "calculated": False,
    }
    rollup_names: frozenset[str] = frozenset({"CompSuite__Count_Open_Action_Items__c"})
    assert _semantic_type(raw, rollup_names) == "Roll-Up Summary"


def test_semantic_type_rollup_takes_priority_over_formula() -> None:
    """Roll-Up Summary check must fire before the calculated/formula branch."""
    raw = {
        "name": "MyRollup__c",
        "type": "double",
        "autoNumber": False,
        "calculated": True,  # would normally yield "Formula (Number)"
    }
    rollup_names: frozenset[str] = frozenset({"MyRollup__c"})
    assert _semantic_type(raw, rollup_names) == "Roll-Up Summary"


def test_semantic_type_no_rollup_set_falls_through() -> None:
    """Without rollup_names the field must fall through to Formula/base label."""
    raw = {
        "name": "CompSuite__Count_Open_Action_Items__c",
        "type": "double",
        "autoNumber": False,
        "calculated": False,
    }
    assert _semantic_type(raw) == "Number"
    assert _semantic_type(raw, None) == "Number"
    assert _semantic_type(raw, frozenset()) == "Number"


def test_fetch_rollup_summary_via_tooling() -> None:
    """fetch() must label a field as "Roll-Up Summary" when the Tooling query returns it."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "CompSuite__Count_Open_Action_Items__c",
                    "label": "Count Open Action Items",
                    "type": "double",
                    "autoNumber": False,
                    "calculated": False,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    # Tooling API returns the field as a Roll-Up Summary
    client.tooling_query = AsyncMock(
        return_value={
            "records": [
                {
                    "QualifiedApiName": "CompSuite__Count_Open_Action_Items__c",
                    "SummaryOperation": "COUNT",
                }
            ]
        }
    )
    specs = asyncio.run(fields.fetch(client, "CompSuite__Change_Control__c"))
    assert specs[0].type == "Roll-Up Summary"


def test_fetch_rollup_tooling_failure_falls_back() -> None:
    """If the Tooling query raises, fetch() must still return results (graceful fallback)."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "CompSuite__Count_Open_Action_Items__c",
                    "label": "Count Open Action Items",
                    "type": "double",
                    "autoNumber": False,
                    "calculated": False,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    # Tooling API raises (e.g. insufficient access)
    client.tooling_query = AsyncMock(side_effect=Exception("Tooling API unavailable"))
    specs = asyncio.run(fields.fetch(client, "CompSuite__Change_Control__c"))
    # Must not crash; field falls through to base-type label
    assert len(specs) == 1
    assert specs[0].type == "Number"


# ---------------------------------------------------------------------------
# WI-02: Formula expression populated for non-text formula fields
# ---------------------------------------------------------------------------


def test_fetch_formula_date_populates_formula_field() -> None:
    """fetch() must store calculatedFormula on a date formula field."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Max_Action_Due_Date__c",
                    "label": "Max Action Due Date",
                    "type": "date",
                    "autoNumber": False,
                    "calculated": True,
                    "calculatedFormula": "MAX(Action__r.Due_Date__c)",
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    client.tooling_query = AsyncMock(return_value={"records": []})
    specs = asyncio.run(fields.fetch(client, "Change_Control__c"))
    assert specs[0].formula == "MAX(Action__r.Due_Date__c)"
    assert specs[0].type == "Formula (Date)"


def test_fetch_formula_number_populates_formula_field() -> None:
    """fetch() must store calculatedFormula on a number formula field."""
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Total_Cost__c",
                    "label": "Total Cost",
                    "type": "double",
                    "autoNumber": False,
                    "calculated": True,
                    "calculatedFormula": "Qty__c * UnitPrice__c",
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    client.tooling_query = AsyncMock(return_value={"records": []})
    specs = asyncio.run(fields.fetch(client, "Order__c"))
    assert specs[0].formula == "Qty__c * UnitPrice__c"
    assert specs[0].type == "Formula (Number)"


# ---------------------------------------------------------------------------
# WI-NEW-C (new): Roll-Up Summary via CustomField Metadata API summaryOperation
# ---------------------------------------------------------------------------


def test_fetch_rollup_via_metadata_api_summary_operation() -> None:
    """fetch() must label a field as "Roll-Up Summary" when the describe has
    calculated=True and no calculatedFormula — the primary REST describe heuristic.

    This test additionally verifies the secondary path: if the Tooling API
    returns no records (as happens for managed-package fields) but the
    Metadata API CustomField record carries summaryOperation, the field is
    still detected via the primary describe heuristic (calculated=True, no
    calculatedFormula).

    Root cause for the previous failure: the code only checked rollup_names
    (Tooling path) and never applied the REST describe heuristic, so managed-
    package roll-up fields whose FieldDefinition.SummaryOperation is
    inaccessible always fell through to "Formula (Number)".
    """
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "CompSuite__Count_Open_Action_Items__c",
                    "label": "Count Open Action Items",
                    "type": "double",
                    "autoNumber": False,
                    # Salesforce exposes roll-up summary fields as calculated=True
                    # with no calculatedFormula in the REST describe.
                    "calculated": True,
                    "calculatedFormula": None,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    # Tooling API returns empty (inaccessible for managed-package fields)
    client.tooling_query = AsyncMock(return_value={"records": []})
    # Metadata API returns summaryOperation for the field
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "CompSuite__Change_Control__c.CompSuite__Count_Open_Action_Items__c",
                "type": "Summary",
                "summaryOperation": "COUNT",
                "summaryForeignKey": "CompSuite__Action_Item__c.CompSuite__Change_Control__c",
            }
        ]
    )
    specs = asyncio.run(fields.fetch(client, "CompSuite__Change_Control__c"))
    # Primary REST describe heuristic: calculated=True + no calculatedFormula = Roll-Up Summary
    assert specs[0].type == "Roll-Up Summary"
    # Roll-up fields must not carry a formula expression
    assert specs[0].formula is None


# ---------------------------------------------------------------------------
# WI-01 / 005 / 008 (new): Date formula expression from Metadata API
# ---------------------------------------------------------------------------


def test_fetch_date_formula_expression_from_metadata_api() -> None:
    """fetch() must populate FieldSpec.formula from the Metadata API CustomField
    when the REST describe returns no calculatedFormula for a date formula field.

    The REST describe endpoint omits calculatedFormula for date/datetime formula
    fields (a known Salesforce API limitation).  fetch() must call
    client.read_metadata("CustomField", ...) for these fields and populate
    FieldSpec.formula from the ``formula`` element in the metadata record.
    """
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Max_Action_Due_Date__c",
                    "label": "Max Action Due Date",
                    "type": "date",
                    "autoNumber": False,
                    "calculated": True,
                    # calculatedFormula absent — as Salesforce returns for date formulas
                    "calculatedFormula": None,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    client.tooling_query = AsyncMock(return_value={"records": []})
    # Metadata API returns the formula text in the ``formula`` element
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Change_Control__c.Max_Action_Due_Date__c",
                "type": "Date",
                "formula": "MAX(Action__r.Due_Date__c)",
            }
        ]
    )
    specs = asyncio.run(fields.fetch(client, "Change_Control__c"))
    # The Metadata API ``formula`` element is fed into _semantic_type as meta_formula.
    # This overrides the Roll-Up Summary classification (rule 2b: calculated=True,
    # no describe calculatedFormula, but meta_formula present → "Formula (Date)").
    assert specs[0].type == "Formula (Date)"
    # Formula expression populated from Metadata API
    assert specs[0].formula == "MAX(Action__r.Due_Date__c)"
    # Verify read_metadata was called with the correct arguments
    client.read_metadata.assert_called_once_with(
        "CustomField", ["Change_Control__c.Max_Action_Due_Date__c"]
    )


# ---------------------------------------------------------------------------
# V4 NEW-006 / open 005 / 008: Positive summaryOperation evidence for rollup
# ---------------------------------------------------------------------------


def test_fetch_calculated_with_summary_operation_is_rollup() -> None:
    """A calculated field whose CustomField metadata has summaryOperation must
    be classified as "Roll-Up Summary".

    Positive summaryOperation evidence (not by-elimination): the Metadata API
    CustomField record carries a non-empty ``summaryOperation`` element, so
    _fetch_formula_expressions populates metadata_rollup_names with this field.
    _semantic_type then returns "Roll-Up Summary" via rule 2a (rollup_names check
    fires before any formula-text inspection).
    """
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "CompSuite__Count_Open_Action_Items__c",
                    "label": "Count Open Action Items",
                    "type": "double",
                    "autoNumber": False,
                    "calculated": True,
                    "calculatedFormula": None,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    client.tooling_query = AsyncMock(return_value={"records": []})
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "CompSuite__Change_Control__c.CompSuite__Count_Open_Action_Items__c",
                "type": "Summary",
                "summaryOperation": "COUNT",
                "summaryForeignKey": "CompSuite__Action_Item__c.CompSuite__Change_Control__c",
            }
        ]
    )
    specs = asyncio.run(fields.fetch(client, "CompSuite__Change_Control__c"))
    assert specs[0].type == "Roll-Up Summary"
    # Roll-up fields must not carry a formula expression
    assert specs[0].formula is None


def test_fetch_calculated_date_without_summary_operation_is_formula() -> None:
    """A calculated DATE field with no summaryOperation but with a formula in
    the Metadata API must be classified as "Formula (Date)", NOT "Roll-Up Summary".

    This is the Max_Action_Due_Date__c regression scenario (V4 NEW-006 / open 005/008):
    the REST describe omits calculatedFormula for date formula fields, and the old
    by-elimination heuristic wrongly classified them as Roll-Up Summary when the
    Metadata API formula was not read.  With positive-evidence detection:
    - No summaryOperation in metadata → NOT added to rollup_names.
    - formula in metadata → meta_formula is populated → "Formula (Date)".
    - FieldSpec.formula is populated with the expression from metadata.
    """
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Max_Action_Due_Date__c",
                    "label": "Max Action Due Date",
                    "type": "date",
                    "autoNumber": False,
                    "calculated": True,
                    "calculatedFormula": None,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    client.tooling_query = AsyncMock(return_value={"records": []})
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "Change_Control__c.Max_Action_Due_Date__c",
                "type": "Date",
                "formula": "MAX(Action__r.Due_Date__c)",
                # no summaryOperation key
            }
        ]
    )
    specs = asyncio.run(fields.fetch(client, "Change_Control__c"))
    assert specs[0].type == "Formula (Date)"
    assert specs[0].formula == "MAX(Action__r.Due_Date__c)"


def test_fetch_calculated_metadata_yields_neither_is_not_rollup() -> None:
    """A calculated field where the Metadata API returns neither a formula nor
    a summaryOperation must NOT be labeled "Roll-Up Summary".

    When the metadata read fails or returns an empty/incomplete record, there is
    no positive evidence for roll-up.  The safe fallback is "Formula (<Base>)",
    which avoids the false-positive mislabeling that the old by-elimination
    approach produced.
    """
    client = MagicMock()
    client.describe = AsyncMock(
        return_value={
            "fields": [
                {
                    "name": "Some_Calc_Field__c",
                    "label": "Some Calculated Field",
                    "type": "date",
                    "autoNumber": False,
                    "calculated": True,
                    "calculatedFormula": None,
                    "picklistValues": [],
                    "referenceTo": [],
                }
            ]
        }
    )
    client.tooling_query = AsyncMock(return_value={"records": []})
    # Metadata API returns a record with neither formula nor summaryOperation
    client.read_metadata = AsyncMock(
        return_value=[
            {
                "fullName": "MyObject__c.Some_Calc_Field__c",
                # neither "formula" nor "summaryOperation" present
            }
        ]
    )
    specs = asyncio.run(fields.fetch(client, "MyObject__c"))
    # Must NOT be "Roll-Up Summary" — no positive summaryOperation evidence
    assert specs[0].type != "Roll-Up Summary"
    # Should fall back to "Formula (Date)"
    assert specs[0].type == "Formula (Date)"
