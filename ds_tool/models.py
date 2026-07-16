"""Typed metadata models used across collectors and the PDF renderer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class FieldSpec(_Model):
    api_name: str
    label: str
    type: str
    length: int | None = None
    required: bool = False
    unique: bool = False
    external_id: bool = False
    history_tracked: bool = False
    formula: str | None = None
    help_text: str | None = None
    # Explicit default value (literal or formula) for the field, when one is set. §2 (WI-04).
    default_value: str | None = None
    picklist_values: list[str] = Field(default_factory=list)
    reference_to: list[str] = Field(default_factory=list)
    # "Package" (managed/CompSuite__ namespace) vs "Custom". §2 (WI-03).
    classification: str | None = None


class FieldPermission(_Model):
    field: str
    readable: bool = False
    editable: bool = False


class ObjectPermission(_Model):
    obj: str
    create: bool = False
    read: bool = False
    edit: bool = False
    delete: bool = False
    view_all: bool = False
    modify_all: bool = False


class LayoutAssignmentEntry(_Model):
    """One row of Profile.layoutAssignments[] from the Metadata API.

    `record_type` is None for the default (no-RT) assignment.
    """

    layout: str
    record_type: str | None = None


class LayoutAssignment(_Model):
    """Flat row used by §3.4: profile + layout + record type.

    Sourced from a Tooling SOQL on ProfileLayout so the table covers EVERY
    profile in the org, not just the user-selected --profiles. See layouts.py.
    """

    profile: str
    layout: str
    record_type: str | None = None


class ProfileSpec(_Model):
    """A Profile *or* PermissionSet — they share the same shape for our purposes."""

    full_name: str
    label: str
    kind: str  # "Profile" | "PermissionSet"
    user_license: str | None = None
    object_permissions: list[ObjectPermission] = Field(default_factory=list)
    field_permissions: list[FieldPermission] = Field(default_factory=list)
    record_type_visibilities: dict[str, bool] = Field(default_factory=dict)
    layout_assignments: list[LayoutAssignmentEntry] = Field(default_factory=list)


class RecordTypeSpec(_Model):
    api_name: str
    label: str
    active: bool = True
    description: str | None = None
    business_process: str | None = None
    # Map of picklist field API name → ordered list of values active on this RT.
    # Populated from readMetadata("RecordType", ...) — see record_types.py.
    picklist_values: dict[str, list[str]] = Field(default_factory=dict)


class ValidationRuleSpec(_Model):
    api_name: str
    active: bool = True
    description: str | None = None
    error_condition: str | None = None
    error_message: str | None = None
    # Where the error renders: "Top of Page" or a field API name. §5.1 (WI-08).
    error_location: str | None = None


class WorkflowRuleSpec(_Model):
    api_name: str
    active: bool = True
    description: str | None = None
    trigger_type: str | None = None
    criteria: str | None = None


class FlowSpec(_Model):
    api_name: str
    label: str
    process_type: str | None = None
    status: str | None = None
    description: str | None = None
    package_state: str | None = None  # Managed/Unmanaged (§5.12, WI-14)


class EmailAlertSpec(_Model):
    """One WorkflowAlert from readMetadata("Workflow", [object]).alerts[]."""

    api_name: str
    description: str | None = None
    sender_type: str | None = None
    sender_address: str | None = None
    template: str | None = None
    # Flattened "<type>:<recipient>" strings (e.g. "user:john", "role:Sales Manager").
    recipients: list[str] = Field(default_factory=list)
    # §5.3 Email Alerts extra columns (WI-11).
    protected: bool | None = None  # "Protected Component"
    last_checkbox: bool | None = None  # legacy "Last Checkbox" column


class EmailTemplateSpec(_Model):
    """An EmailTemplate referenced by this object's Email Alerts or approval-process rejections."""

    developer_name: str
    label: str
    folder: str | None = None
    template_type: str | None = None
    subject: str | None = None
    # Extended metadata for §5.4 (WI-09).
    letterhead_id: str | None = None
    email_layout_id: str | None = None
    folder_id: str | None = None
    body: str | None = None  # HTML body
    body_plain: str | None = None  # plain-text body


class ApexTriggerSpec(_Model):
    """One ApexTrigger row from Tooling SOQL, scoped to a single object via TableEnumOrId."""

    name: str
    status: str | None = None
    api_version: float | None = None
    # Collapsed events like ["before insert", "after update"].
    events: list[str] = Field(default_factory=list)
    # Extended metadata for §5.5 (WI-13).
    classification: str | None = None  # "Custom" | "Package"
    code_length: int | None = None
    source: str | None = None  # full Apex body


class LightningPageAssignment(_Model):
    """One row of FlexiPage assignment for the current object.

    Built from CustomApplication.actionOverrides[] + profileActionOverrides[]
    where pageOrSobjectType == <object> and actionName == "View".
    """

    app: str
    profile: str | None = None
    record_type: str | None = None
    form_factor: str = "Large"
    flexipage: str


class ObjectGeneralInfo(_Model):
    api_name: str
    label: str
    plural_label: str
    description: str | None = None
    sharing_model: str | None = None
    history_tracking_enabled: bool = False
    # "Extended History in Custom Settings" flag from the PDF §2 (G-1). Optional;
    # None when not applicable / not captured.
    custom_settings_extended_history: bool | None = None


class LifeCycleTransition(_Model):
    """One row of legacy section 4.1 — a state transition + its action metadata.

    Mirrors `CompSuite__Transition_Action__c` joined to `CompSuite__State_Transition__c`
    as queried at force-app/.../DataAPIController.cls:428.
    """

    transition_action_id: str
    record_type: str | None = None
    index: int | None = None
    transition_label: str
    source_state: str
    destination_state: str
    button_style: str | None = None
    needs_e_signature: bool = False
    lock_fields: str | None = None  # comma-joined; LockAttachments separated below
    lock_attachments: bool = False
    mandatory_fields: list[str] = Field(default_factory=list)
    skip_approval: bool = False
    change_fields: list[str] = Field(default_factory=list)  # "FieldLabel:value" pairs
    dependency_on_related_forms: str | None = None  # "Promote" | "Restrict" | None
    xact: bool | None = None


class LifeCycleApprovalProcessInit(_Model):
    """One row of legacy section 4.2 — approval process bound to a transition."""

    transition_action_id: str
    record_type: str | None = None
    index: int | None = None
    transition_label: str
    name: str
    skip_start_action: bool = False
    rejected_state: str | None = None
    manageable_states: list[str] = Field(default_factory=list)
    has_last_approval: bool = False
    minimum_approvers: int | None = None
    reject_lock_fields: str | None = None
    approver_filters: str | None = None
    rejection_email_template: str | None = None


class LifeCyclePermission(_Model):
    """One row of legacy section 4.3 — profiles/permsets allowed on a transition."""

    transition_action_id: str
    record_type: str | None = None
    index: int | None = None
    transition_label: str
    profile_or_permset_names: list[str] = Field(default_factory=list)


class LifeCycleAutoPopulateDate(_Model):
    """One row of legacy section 4.4 — date fields auto-populated on transition."""

    transition_action_id: str
    record_type: str | None = None
    index: int | None = None
    transition_label: str
    source_state: str
    destination_state: str
    # Each tuple is (field_label, avoid_override). "avoid_override=True" renders as
    # "Update the field only if blank" in the PDF (per Ctrl_CMP_Configuration_Report.cls:2998).
    fields: list[tuple[str, bool]] = Field(default_factory=list)


class LifeCycleSpec(_Model):
    """Aggregate of the four legacy Life Cycle subsections.

    `compsuite_installed=False` is set when the org has no CompSuite__* objects;
    the template renders a "not applicable" empty state instead of crashing.
    """

    compsuite_installed: bool = True
    transitions: list[LifeCycleTransition] = Field(default_factory=list)
    approval_processes: list[LifeCycleApprovalProcessInit] = Field(default_factory=list)
    permissions: list[LifeCyclePermission] = Field(default_factory=list)
    auto_populate_dates: list[LifeCycleAutoPopulateDate] = Field(default_factory=list)
    # Union of every profile/permset name referenced across all transitions in this object,
    # used to build the column header set of the 4.3 pivot table.
    related_profile_names: list[str] = Field(default_factory=list)


class ProcessBuilderSpec(_Model):
    """A Process Builder (Flow processType Workflow/InvocableProcess) on this object. §5.6 (WI-02)."""

    api_name: str
    label: str
    status: str | None = None
    description: str | None = None
    trigger_object: str | None = None
    criteria: str | None = None
    actions: list[str] = Field(default_factory=list)


class TabVisibilitySpec(_Model):
    """Per-profile visibility of this object's tab. §3.6 (WI-05)."""

    profile: str
    visibility: str  # "DefaultOn" | "DefaultOff" | "Hidden" | "Visible" | "N/A"


class SharingRuleSpec(_Model):
    name: str
    rule_type: str | None = None  # "criteria" | "owner"
    criteria: str | None = None
    shared_with: str | None = None
    access_level: str | None = None  # "Read" | "Read/Write"


class SharingSpec(_Model):
    """Org-wide defaults + sharing rules for this object. §5.11 (WI-06)."""

    owd_internal: str | None = None
    owd_external: str | None = None
    grant_access_using_hierarchies: bool | None = None  # OWD column (§5.11, WI-15)
    rules: list[SharingRuleSpec] = Field(default_factory=list)


class FieldSetSpec(_Model):
    """A field set on this object. §5.13 (WI-07)."""

    api_name: str
    label: str | None = None
    description: str | None = None
    fields: list[str] = Field(default_factory=list)  # field API names


class CompactLayoutSpec(_Model):
    """A compact layout on this object. §5.9 (WI-10)."""

    api_name: str
    label: str | None = None
    fields: list[str] = Field(default_factory=list)


class LayoutFieldSpec(_Model):
    label: str
    position: str | None = None  # e.g. "1L", "1R"
    behavior: str | None = None  # "Edit" | "Readonly" | "Required"


class LayoutSectionSpec(_Model):
    label: str | None = None
    columns: int | None = None
    fields: list[LayoutFieldSpec] = Field(default_factory=list)


class RelatedListSpec(_Model):
    name: str
    fields: list[str] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)


class PageLayoutSpec(_Model):
    """Full page-layout schema (sections, buttons, related lists). §5.10 (WI-11)."""

    api_name: str
    sections: list[LayoutSectionSpec] = Field(default_factory=list)
    standard_buttons: list[str] = Field(default_factory=list)
    custom_buttons: list[str] = Field(default_factory=list)
    mobile_actions: list[str] = Field(default_factory=list)  # Mobile/Lightning actions (§5.10, WI-06)
    related_lists: list[RelatedListSpec] = Field(default_factory=list)


class SearchLayoutSpec(_Model):
    """One search-layout config for this object. §5.8 (WI-12).

    `layout_type` is e.g. "Default Layout", "List View", "Lookup Dialog", "Tab".
    """

    layout_type: str
    columns: list[str] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)


class FieldUpdateSpec(_Model):
    """A workflow Field Update action (§5.3 Field Update Details, WI-10)."""

    api_name: str
    name: str | None = None
    description: str | None = None
    field: str | None = None
    operation: str | None = None  # e.g. "Literal value" | "Formula" | "Null value"
    value: str | None = None  # literal value or formula expression
    notify_assignee: bool | None = None
    reevaluate_workflow_rules: bool | None = None


class ObjectSpec(_Model):
    """The full spec for one object, ready to feed into the PDF template."""

    general: ObjectGeneralInfo
    fields: list[FieldSpec] = Field(default_factory=list)
    profiles: list[ProfileSpec] = Field(default_factory=list)
    record_types: list[RecordTypeSpec] = Field(default_factory=list)
    layout_assignments: list[LayoutAssignment] = Field(default_factory=list)
    validation_rules: list[ValidationRuleSpec] = Field(default_factory=list)
    workflows: list[WorkflowRuleSpec] = Field(default_factory=list)
    flows: list[FlowSpec] = Field(default_factory=list)
    email_alerts: list[EmailAlertSpec] = Field(default_factory=list)
    email_templates: list[EmailTemplateSpec] = Field(default_factory=list)
    apex_triggers: list[ApexTriggerSpec] = Field(default_factory=list)
    lightning_pages: list[LightningPageAssignment] = Field(default_factory=list)
    life_cycle: LifeCycleSpec | None = None
    # Sections added for old→new tool parity (traceability v2):
    process_builders: list[ProcessBuilderSpec] = Field(default_factory=list)  # §5.6 (WI-02)
    field_updates: list[FieldUpdateSpec] = Field(default_factory=list)  # §5.3 (WI-10)
    tab_visibilities: list[TabVisibilitySpec] = Field(default_factory=list)  # §3.6 (WI-05)
    sharing: SharingSpec | None = None  # §5.11 (WI-06)
    field_sets: list[FieldSetSpec] = Field(default_factory=list)  # §5.13 (WI-07)
    compact_layouts: list[CompactLayoutSpec] = Field(default_factory=list)  # §5.9 (WI-10)
    page_layouts: list[PageLayoutSpec] = Field(default_factory=list)  # §5.10 (WI-11)
    search_layouts: list[SearchLayoutSpec] = Field(default_factory=list)  # §5.8 (WI-12)
