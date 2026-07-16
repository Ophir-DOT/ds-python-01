"""Process Builder flows for one object via FlowDefinitionView + Metadata API.

Process Builders are Flows whose processType is 'Workflow' or 'InvocableProcess'.
They are distinct from §5.12 Flows (AutoLaunchedFlow) and are filtered by
TriggerObjectOrEvent.QualifiedApiName so only builders that act on the requested
object are returned.

Criteria and actions are extracted from the full Flow metadata payload:
- criteria  → decisions[].rules[].label + conditions
- actions   → actionCalls[].actionType + label

Reference: `Ctrl_CMP_Configuration_Report.cls:841-1070`,
           `DataAPIController.cls:1404`.
"""

from __future__ import annotations

from typing import Any

from ..client import SalesforceClient
from ..models import ProcessBuilderSpec

_PROCESS_TYPES = ("Workflow", "InvocableProcess")


def _object_type(raw_flow: dict[str, Any]) -> str | None:
    """The object a Process Builder acts on, from processMetadataValues[ObjectType]."""
    for pmv in _as_list(raw_flow.get("processMetadataValues")):
        if isinstance(pmv, dict) and (pmv.get("name") or "").lower() == "objecttype":
            val = pmv.get("value") or {}
            if isinstance(val, dict):
                return val.get("stringValue")
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_criteria(raw_flow: dict[str, Any]) -> str | None:
    """Collapse decisions → rules → conditions into a single summary string.

    Mirrors Ctrl_CMP_Configuration_Report.cls:912-962.
    """
    parts: list[str] = []
    for decision in _as_list(raw_flow.get("decisions")):
        if not isinstance(decision, dict):
            continue
        for rule in _as_list(decision.get("rules")):
            if not isinstance(rule, dict):
                continue
            label = rule.get("label") or ""
            rule_parts: list[str] = [label] if label else []

            # Connector hint: targetReference contains 'myRule' → conditions are met
            connector = rule.get("connector") or {}
            if isinstance(connector, dict):
                target = connector.get("targetReference") or ""
                if "myRule" in target.lower():
                    rule_parts.append("Conditions are met")
                else:
                    rule_parts.append("Formula evaluates to true")

            for condition in _as_list(rule.get("conditions")):
                if not isinstance(condition, dict):
                    continue
                left = (condition.get("leftValueReference") or "").replace(
                    "myVariable_current.", ""
                )
                operator = condition.get("operator") or ""
                cond_str = f"{left} {operator}".strip()

                right_val = condition.get("rightValue") or {}
                if isinstance(right_val, dict):
                    if right_val.get("stringValue") is not None:
                        cond_str += f" String {right_val['stringValue']}"
                    elif right_val.get("numberValue") is not None:
                        cond_str += f" Number {right_val['numberValue']}"
                    elif right_val.get("elementReference") is not None:
                        cond_str += f" Field Reference {right_val['elementReference']}"
                    elif right_val.get("dateValue") is not None:
                        cond_str += f" Date {right_val['dateValue']}"
                    elif right_val.get("dateTimeValue") is not None:
                        cond_str += f" Date Time {right_val['dateTimeValue']}"
                    elif right_val.get("booleanValue") is not None:
                        cond_str += f" Boolean {right_val['booleanValue']}"
                rule_parts.append(cond_str)

            logic = (rule.get("conditionLogic") or "").lower()
            if logic == "or":
                rule_parts.append("Any of the conditions are met (OR)")
            elif logic == "and":
                rule_parts.append("All of the conditions are met (AND)")
            elif logic:
                rule_parts.append("Customize the logic")

            parts.append(" - ".join(p for p in rule_parts if p))

    return ", ".join(parts) if parts else None


def _action_call_str(call: dict[str, Any]) -> str:
    """Format a single actionCalls entry as a readable string."""
    action_type = call.get("actionType") or ""
    label = call.get("label") or ""
    parts = [p for p in (action_type, label) if p]
    return " - ".join(parts) if parts else "(unknown action)"


def _parse_actions(raw_flow: dict[str, Any]) -> list[str]:
    """Collect human-readable action strings from all action sources in a Flow/PB payload.

    Process Builders can surface actions via several top-level node types:
      1. actionCalls[]          – invocable actions, email alerts, flows, quick actions …
      2. recordUpdates[]        – "Update Records" nodes (very common in PBs)
      3. recordCreates[]        – "Create Records" nodes
      4. recordDeletes[]        – "Delete Records" nodes
      5. Nested actionCalls inside decision rules' scheduledPaths[] / actionSequence[]
         (time-triggered actions in PBs use this structure)

    Mirrors Ctrl_CMP_Configuration_Report.cls:864-901 and extends it for the
    record-DML node types that the original Apex code omitted.
    """
    actions: list[str] = []

    # 1. Top-level actionCalls
    for call in _as_list(raw_flow.get("actionCalls")):
        if isinstance(call, dict):
            actions.append(_action_call_str(call))

    # 2–4. Record DML nodes (Update / Create / Delete)
    for node_key, verb in (
        ("recordUpdates", "Update Records"),
        ("recordCreates", "Create Records"),
        ("recordDeletes", "Delete Records"),
    ):
        for node in _as_list(raw_flow.get(node_key)):
            if not isinstance(node, dict):
                continue
            label = node.get("label") or node.get("object") or ""
            actions.append(f"{verb}: {label}" if label else verb)

    # 5. Nested actionCalls inside decisions → scheduledPaths / actionSequence
    for decision in _as_list(raw_flow.get("decisions")):
        if not isinstance(decision, dict):
            continue
        for path_key in ("scheduledPaths", "actionSequence"):
            for path in _as_list(decision.get(path_key)):
                if not isinstance(path, dict):
                    continue
                for call in _as_list(path.get("actionCalls")):
                    if isinstance(call, dict):
                        actions.append(_action_call_str(call))

    return actions


async def fetch(client: SalesforceClient, object_api_name: str) -> list[ProcessBuilderSpec]:
    """Return all Process Builders that act on *object_api_name*.

    Process Builders are the legacy "Workflow" process type. Unlike record-triggered
    Flows, they do NOT populate FlowDefinitionView.TriggerObjectOrEventId — the
    object lives only in the flow metadata (processMetadataValues[ObjectType]).
    So we enumerate every Workflow/InvocableProcess (standard Query API, no object
    filter) and keep the ones whose metadata ObjectType matches. This mirrors the
    legacy DataAPIController query (`WHERE ProcessType='Workflow'` + metadata match).
    """
    types_in = ", ".join(f"'{t}'" for t in _PROCESS_TYPES)
    soql = (
        "SELECT ApiName, Label, ProcessType, IsActive, Description "
        "FROM FlowDefinitionView "
        f"WHERE ProcessType IN ({types_in})"
    )
    try:
        result = await client.query(soql)
    except Exception:
        return []

    records = result.get("records", [])
    if not records:
        return []

    # Resolve each builder's object from its full Flow metadata.
    api_names = [r["ApiName"] for r in records if r.get("ApiName")]
    try:
        full_metadata = await client.read_metadata("Flow", api_names)
    except Exception:
        full_metadata = []

    meta_by_name: dict[str, dict[str, Any]] = {}
    for m in full_metadata:
        if isinstance(m, dict) and m.get("fullName"):
            meta_by_name[m["fullName"]] = m

    specs: list[ProcessBuilderSpec] = []
    for r in records:
        api_name = r.get("ApiName") or ""
        raw = meta_by_name.get(api_name, {})
        obj_type = _object_type(raw)
        # Keep only process builders built on the requested object.
        if obj_type != object_api_name:
            continue
        specs.append(
            ProcessBuilderSpec(
                api_name=api_name,
                label=r.get("Label") or api_name,
                status="Active" if r.get("IsActive") else "Inactive",
                description=r.get("Description"),
                trigger_object=obj_type,
                criteria=_parse_criteria(raw) if raw else None,
                actions=_parse_actions(raw) if raw else [],
            )
        )
    return specs
