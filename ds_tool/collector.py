"""Async orchestrator: assemble one ObjectSpec by gathering all sections concurrently.

The profile cache is populated ONCE at run start (see `populate_profile_cache`),
so all per-object work reads from memory rather than re-issuing Metadata API calls.

Most per-object collectors run in a single `asyncio.gather`. Email templates
depend on the alerts pass (template developerNames are extracted from alerts),
so they run in a small second stage after the first gather completes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Iterable

from .cache import ProfileCache
from .client import SalesforceClient
from .metadata import apex_triggers as apex_triggers_md
from .metadata import compact_layouts as compact_layouts_md
from .metadata import email_alerts as email_alerts_md
from .metadata import email_templates as email_templates_md
from .metadata import field_updates as field_updates_md
from .metadata import field_sets as field_sets_md
from .metadata import fields as fields_md
from .metadata import flows as flows_md
from .metadata import layouts as layouts_md
from .metadata import lifecycle as lifecycle_md
from .metadata import lightning_pages as lightning_pages_md
from .metadata import objects as objects_md
from .metadata import page_layouts as page_layouts_md
from .metadata import process_builder as process_builder_md
from .metadata import profiles as profiles_md
from .metadata import record_types as record_types_md
from .metadata import search_layouts as search_layouts_md
from .metadata import sharing as sharing_md
from .metadata import tab_settings as tab_settings_md
from .metadata import validation as validation_md
from .metadata import workflows as workflows_md
from .models import ObjectSpec


@dataclass(frozen=True)
class CollectInputs:
    objects: tuple[str, ...]
    profile_names: tuple[str, ...] | None
    permission_set_names: tuple[str, ...] | None
    concurrency: int = 8


async def populate_profile_cache(
    client: SalesforceClient,
    cache: ProfileCache,
    *,
    profile_names: Iterable[str] | None,
    permission_set_names: Iterable[str] | None,
) -> list[str]:
    profiles, missing = await profiles_md.fetch_all(
        client,
        profile_names=profile_names,
        permission_set_names=permission_set_names,
    )
    cache.populate(profiles)
    return missing


async def collect_object(
    client: SalesforceClient,
    cache: ProfileCache,
    object_api_name: str,
    *,
    semaphore: asyncio.Semaphore,
) -> ObjectSpec:
    async with semaphore:
        history = await objects_md.fetch_history_tracked_fields(client, object_api_name)
        (
            general,
            field_list,
            record_types,
            layout_assignments,
            validation_rules,
            workflows,
            flows,
            email_alerts,
            field_updates,
            apex_triggers,
            lightning_pages,
            life_cycle,
            process_builders,
            tab_visibilities,
            sharing,
            field_sets,
            compact_layouts,
            page_layouts,
            search_layouts,
        ) = await asyncio.gather(
            objects_md.fetch_general(client, object_api_name),
            fields_md.fetch(client, object_api_name, history_tracked=history),
            record_types_md.fetch(client, object_api_name),
            layouts_md.fetch(client, object_api_name),
            validation_md.fetch(client, object_api_name),
            workflows_md.fetch(client, object_api_name),
            flows_md.fetch(client, object_api_name),
            email_alerts_md.fetch(client, object_api_name),
            field_updates_md.fetch(client, object_api_name),
            apex_triggers_md.fetch(client, object_api_name),
            lightning_pages_md.fetch(client, object_api_name),
            lifecycle_md.fetch(client, object_api_name, cache),
            process_builder_md.fetch(client, object_api_name),
            tab_settings_md.fetch(client, object_api_name, cache),
            sharing_md.fetch(client, object_api_name),
            field_sets_md.fetch(client, object_api_name),
            compact_layouts_md.fetch(client, object_api_name),
            page_layouts_md.fetch(client, object_api_name),
            search_layouts_md.fetch(client, object_api_name),
        )

        # Second stage: email templates depend on which template developerNames
        # the alerts pass surfaced. Cheap one-shot SOQL.
        template_refs = email_alerts_md.referenced_template_names(email_alerts)
        email_templates = await email_templates_md.fetch_referenced(client, template_refs)

        profiles_for_obj = cache.for_object(object_api_name)
        return ObjectSpec(
            general=general,
            fields=field_list,
            profiles=profiles_for_obj,
            record_types=record_types,
            layout_assignments=layout_assignments,
            validation_rules=validation_rules,
            workflows=workflows,
            flows=flows,
            email_alerts=email_alerts,
            email_templates=email_templates,
            field_updates=field_updates,
            apex_triggers=apex_triggers,
            lightning_pages=lightning_pages,
            life_cycle=life_cycle,
            process_builders=process_builders,
            tab_visibilities=tab_visibilities,
            sharing=sharing,
            field_sets=field_sets,
            compact_layouts=compact_layouts,
            page_layouts=page_layouts,
            search_layouts=search_layouts,
        )


async def collect_all(
    client: SalesforceClient,
    cache: ProfileCache,
    inputs: CollectInputs,
    *,
    on_done: Callable[[str], None] | None = None,
) -> dict[str, ObjectSpec]:
    if not cache.is_populated:
        await populate_profile_cache(
            client,
            cache,
            profile_names=inputs.profile_names,
            permission_set_names=inputs.permission_set_names,
        )
    semaphore = asyncio.Semaphore(inputs.concurrency)

    async def _one(obj_name: str) -> tuple[str, ObjectSpec]:
        spec = await collect_object(client, cache, obj_name, semaphore=semaphore)
        if on_done:
            on_done(obj_name)
        return obj_name, spec

    pairs = await asyncio.gather(*(_one(o) for o in inputs.objects))
    return dict(pairs)
