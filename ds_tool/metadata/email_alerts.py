"""Email alerts via the Workflow Metadata API.

`readMetadata("Workflow", [<object>])` returns the workflow container for that
object; the `alerts[]` child holds the WorkflowAlert definitions. Each alert
references an EmailTemplate by developerName via `template` — those template
names are collected here so `email_templates.fetch_referenced` can resolve them
later in the pipeline.

Reference: `Ctrl_CMP_Configuration_Report.cls:796`.
"""

from __future__ import annotations

from typing import Any

from ..client import SalesforceClient
from ..models import EmailAlertSpec


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _recipient_label(entry: dict[str, Any]) -> str:
    recipient = entry.get("recipient") or ""
    rtype = entry.get("type") or ""
    if recipient and rtype:
        return f"{rtype}: {recipient}"
    return recipient or rtype or ""


async def fetch(client: SalesforceClient, object_api_name: str) -> list[EmailAlertSpec]:
    try:
        records = await client.read_metadata("Workflow", [object_api_name])
    except Exception:
        return []

    specs: list[EmailAlertSpec] = []
    for raw in records:
        for alert in _as_list(raw.get("alerts")):
            if not isinstance(alert, dict):
                continue
            full_name = alert.get("fullName") or ""
            if not full_name:
                continue
            recipients = [
                label
                for r in _as_list(alert.get("recipients"))
                if isinstance(r, dict)
                for label in (_recipient_label(r),)
                if label
            ]
            # "Protected Component": the WorkflowAlert metadata exposes a boolean
            # `protected` field that indicates whether the alert is a protected
            # managed-package component.  Map it directly.
            raw_protected = alert.get("protected")
            protected: bool | None = None
            if raw_protected is not None:
                # The SOAP API may return the string "true"/"false" or a real bool.
                if isinstance(raw_protected, bool):
                    protected = raw_protected
                else:
                    protected = str(raw_protected).lower() == "true"

            # "Last Checkbox": this column appeared in the V1 PDF report as "--"
            # for every alert.  There is no standard WorkflowAlert field in the
            # Salesforce Metadata API that corresponds to it.  We always set it to
            # None and render it as blank/"-–" in the template.
            last_checkbox: None = None

            specs.append(
                EmailAlertSpec(
                    api_name=full_name,
                    description=alert.get("description"),
                    sender_type=alert.get("senderType"),
                    sender_address=alert.get("senderAddress"),
                    template=alert.get("template"),
                    recipients=recipients,
                    protected=protected,
                    last_checkbox=last_checkbox,
                )
            )
    return specs


def referenced_template_names(alerts: list[EmailAlertSpec]) -> list[str]:
    """Distinct EmailTemplate developerNames referenced by these alerts."""
    seen: set[str] = set()
    out: list[str] = []
    for a in alerts:
        if a.template and a.template not in seen:
            seen.add(a.template)
            out.append(a.template)
    return out
