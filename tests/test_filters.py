from __future__ import annotations

from ds_tool.filters import ReportSettings, apply_exclusions
from ds_tool.models import (
    EmailAlertSpec,
    FieldSpec,
    ObjectGeneralInfo,
    ObjectSpec,
    ValidationRuleSpec,
    WorkflowRuleSpec,
)


def _spec() -> ObjectSpec:
    return ObjectSpec(
        general=ObjectGeneralInfo(api_name="Account", label="Account", plural_label="Accounts"),
        fields=[
            FieldSpec(api_name="Name", label="Name", type="string"),
            FieldSpec(api_name="Calc__c", label="Calc", type="formula", formula="1+1"),
            FieldSpec(
                api_name="CalcDoc__c",
                label="CalcDoc",
                type="formula",
                formula="2+2",
                help_text="documented",
            ),
        ],
        validation_rules=[ValidationRuleSpec(api_name="V1")],
        workflows=[WorkflowRuleSpec(api_name="W1")],
        email_alerts=[EmailAlertSpec(api_name="A1")],
    )


def test_apply_exclusions_drops_sections() -> None:
    spec = _spec()
    out = apply_exclusions(
        spec,
        ReportSettings(
            exclude_validation_rules=True,
            exclude_state_automations=True,
            exclude_email_alerts=True,
        ),
    )
    assert out.validation_rules == []
    assert out.workflows == []
    assert out.email_alerts == []
    # original is untouched (model_copy, not mutation)
    assert spec.validation_rules and spec.workflows and spec.email_alerts


def test_apply_exclusions_formula_without_description() -> None:
    out = apply_exclusions(_spec(), ReportSettings(exclude_formula_fields_empty_desc=True))
    names = {f.api_name for f in out.fields}
    assert "Calc__c" not in names  # formula, no help text → dropped
    assert "CalcDoc__c" in names  # formula with help text → kept
    assert "Name" in names


def test_no_settings_returns_same_object() -> None:
    spec = _spec()
    assert apply_exclusions(spec, ReportSettings()) is spec
