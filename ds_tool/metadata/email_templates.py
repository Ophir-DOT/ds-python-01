"""Email templates referenced by this object's email alerts.

Scope: only templates referenced by the object's WorkflowAlerts. Approval-
process rejection templates are already resolved separately inside `lifecycle.py`
via the auxiliary `email_templates` cache, so they don't need a second pass here.

The `template` field on a WorkflowAlert is a folder-qualified developerName
(e.g. `Sales_Folder/Win_Notification` or `unfiled$public/MyTemplate`). We split
on `/`, then SOQL EmailTemplate by `DeveloperName` (the bare template name).

Reference: `DataAPIController.cls:511`.
"""

from __future__ import annotations

from ..client import SalesforceClient
from ..models import EmailTemplateSpec


def _developer_name(template_ref: str) -> str:
    """Strip the `<folder>/` prefix from a WorkflowAlert.template reference."""
    if "/" in template_ref:
        return template_ref.split("/", 1)[1]
    return template_ref


def _soql_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def fetch_referenced(
    client: SalesforceClient, template_refs: list[str]
) -> list[EmailTemplateSpec]:
    if not template_refs:
        return []

    # Preserve insertion order so the rendered section matches alert order.
    seen: set[str] = set()
    dev_names: list[str] = []
    for ref in template_refs:
        name = _developer_name(ref)
        if name and name not in seen:
            seen.add(name)
            dev_names.append(name)
    if not dev_names:
        return []

    quoted = ",".join(f"'{_soql_quote(n)}'" for n in dev_names)
    soql = (
        "SELECT DeveloperName, Name, FolderName, TemplateType, Subject, "
        "BrandTemplateId, FolderId, HtmlValue, Body "
        f"FROM EmailTemplate WHERE DeveloperName IN ({quoted})"
    )
    try:
        records = await client.query_all(soql)
    except Exception:
        return []

    by_dev: dict[str, dict] = {r["DeveloperName"]: r for r in records if r.get("DeveloperName")}
    specs: list[EmailTemplateSpec] = []
    for dev_name in dev_names:
        r = by_dev.get(dev_name)
        if not r:
            continue
        specs.append(
            EmailTemplateSpec(
                developer_name=dev_name,
                label=r.get("Name") or dev_name,
                folder=r.get("FolderName"),
                template_type=r.get("TemplateType"),
                subject=r.get("Subject"),
                letterhead_id=r.get("BrandTemplateId") or None,
                email_layout_id=None,  # Not available via standard SOQL
                folder_id=r.get("FolderId") or None,
                body=r.get("HtmlValue") or None,
                body_plain=r.get("Body") or None,
            )
        )
    return specs
