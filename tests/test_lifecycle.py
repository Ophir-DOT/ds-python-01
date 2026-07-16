"""Tests for lifecycle template columns added in WI-09 and WI-05."""

from __future__ import annotations

from ds_tool.models import (
    LifeCycleApprovalProcessInit,
    LifeCycleSpec,
    LifeCycleTransition,
    ObjectGeneralInfo,
    ObjectSpec,
)
from ds_tool.pdf.render import render_html


def _make_spec(life_cycle: LifeCycleSpec) -> ObjectSpec:
    return ObjectSpec(
        general=ObjectGeneralInfo(
            api_name="Account", label="Account", plural_label="Accounts"
        ),
        life_cycle=life_cycle,
    )


# ---------------------------------------------------------------------------
# WI-09 — §4.1 Change Checkbox Fields column
# ---------------------------------------------------------------------------


def test_41_change_fields_column_header_present() -> None:
    spec = _make_spec(
        LifeCycleSpec(
            compsuite_installed=True,
            transitions=[
                LifeCycleTransition(
                    transition_action_id="ta1",
                    transition_label="Submit",
                    source_state="Draft",
                    destination_state="Submitted",
                    change_fields=["Field__c", "Other__c"],
                )
            ],
        )
    )
    html = render_html(spec)
    assert "Change Checkbox Fields" in html


def test_41_change_fields_joined_value_appears() -> None:
    spec = _make_spec(
        LifeCycleSpec(
            compsuite_installed=True,
            transitions=[
                LifeCycleTransition(
                    transition_action_id="ta1",
                    transition_label="Submit",
                    source_state="Draft",
                    destination_state="Submitted",
                    change_fields=["Field__c", "Other__c"],
                )
            ],
        )
    )
    html = render_html(spec)
    assert "Field__c, Other__c" in html


def test_41_change_fields_empty_renders_no() -> None:
    spec = _make_spec(
        LifeCycleSpec(
            compsuite_installed=True,
            transitions=[
                LifeCycleTransition(
                    transition_action_id="ta1",
                    transition_label="Submit",
                    source_state="Draft",
                    destination_state="Submitted",
                    change_fields=[],
                )
            ],
        )
    )
    html = render_html(spec)
    assert "Change Checkbox Fields" in html
    # "No" should appear at least once (for empty change_fields)
    assert "No" in html


# ---------------------------------------------------------------------------
# WI-05 — §4.2 Reviewers / Reject Action Lock Fields / Approver Filters columns
# ---------------------------------------------------------------------------


def test_42_new_column_headers_present() -> None:
    spec = _make_spec(
        LifeCycleSpec(
            compsuite_installed=True,
            approval_processes=[
                LifeCycleApprovalProcessInit(
                    transition_action_id="api1",
                    transition_label="Submit",
                    name="Approval Init 1",
                    reject_lock_fields="Status__c",
                    approver_filters="QA_Group",
                )
            ],
        )
    )
    html = render_html(spec)
    assert "Reviewers" in html
    assert "Reject Action Lock Fields" in html
    assert "Approver Filters" in html


def test_42_reviewers_placeholder() -> None:
    """Reviewers column must show the '--' placeholder (no model field exists)."""
    spec = _make_spec(
        LifeCycleSpec(
            compsuite_installed=True,
            approval_processes=[
                LifeCycleApprovalProcessInit(
                    transition_action_id="api1",
                    transition_label="Submit",
                    name="Approval Init 1",
                )
            ],
        )
    )
    html = render_html(spec)
    assert "--" in html


def test_42_reject_lock_fields_value_appears() -> None:
    spec = _make_spec(
        LifeCycleSpec(
            compsuite_installed=True,
            approval_processes=[
                LifeCycleApprovalProcessInit(
                    transition_action_id="api1",
                    transition_label="Submit",
                    name="Approval Init 1",
                    reject_lock_fields="Status__c,Stage__c",
                )
            ],
        )
    )
    html = render_html(spec)
    assert "Status__c,Stage__c" in html


def test_42_approver_filters_value_appears() -> None:
    spec = _make_spec(
        LifeCycleSpec(
            compsuite_installed=True,
            approval_processes=[
                LifeCycleApprovalProcessInit(
                    transition_action_id="api1",
                    transition_label="Submit",
                    name="Approval Init 1",
                    approver_filters="QA_Group, Dev_Group",
                )
            ],
        )
    )
    html = render_html(spec)
    assert "QA_Group, Dev_Group" in html


def test_42_empty_lock_and_filters_render_no() -> None:
    spec = _make_spec(
        LifeCycleSpec(
            compsuite_installed=True,
            approval_processes=[
                LifeCycleApprovalProcessInit(
                    transition_action_id="api1",
                    transition_label="Submit",
                    name="Approval Init 1",
                    reject_lock_fields=None,
                    approver_filters=None,
                )
            ],
        )
    )
    html = render_html(spec)
    # Both empty fields should fall back to "No"
    assert html.count("No") >= 2
