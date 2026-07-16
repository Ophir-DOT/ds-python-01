"""Backend-driving helpers shared by the tabs (collect + render)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from ..cache import ProfileCache
from ..client import SalesforceClient
from ..collector import CollectInputs, collect_all, populate_profile_cache
from ..filters import ReportSettings, apply_exclusions
from ..models import ObjectSpec
from ..pdf.render import (
    PdfBackendUnavailable,
    ReportMeta,
    render_combined_html_file,
    render_combined_pdf,
    render_html_file,
    render_pdf,
)
from .demo import make_demo_spec
from .state import OrgConnection

Progress = Callable[[str], None]


async def collect_specs(
    conn: OrgConnection,
    objects: Sequence[str],
    profiles: tuple[str, ...] | None,
    permission_sets: tuple[str, ...] | None,
    concurrency: int,
    on_progress: Progress,
) -> dict[str, ObjectSpec]:
    """Collect ObjectSpecs from a live org."""
    client = SalesforceClient(conn.creds)
    cache = ProfileCache()
    try:
        on_progress("Fetching profiles & permission sets…")
        await populate_profile_cache(
            client, cache, profile_names=profiles, permission_set_names=permission_sets
        )
        inputs = CollectInputs(
            objects=tuple(objects),
            profile_names=profiles,
            permission_set_names=permission_sets,
            concurrency=concurrency,
        )
        return await collect_all(
            client, cache, inputs, on_done=lambda n: on_progress(f"Collected {n}")
        )
    finally:
        await client.aclose()


def build_demo_specs(conn: OrgConnection, objects: Sequence[str]) -> dict[str, ObjectSpec]:
    label_by_key = {o.api_name: o.label for o in conn.objects}
    return {api: make_demo_spec(api, label_by_key.get(api, api)) for api in objects}


def render_specs(
    specs: dict[str, ObjectSpec],
    out_dir: Path,
    settings: ReportSettings,
    on_progress: Progress,
    conn: OrgConnection | None = None,
) -> tuple[list[Path], str]:
    """Render per-object + combined documents. Falls back to HTML if WeasyPrint
    can't load native libs. Returns (written_paths, format_label).

    `conn` supplies the org URL/ID stamped on the combined report's cover; omit
    it (e.g. demo runs) and only the generation timestamp is shown."""
    filtered = {k: apply_exclusions(v, settings) for k, v in specs.items()}
    meta = (
        ReportMeta(instance_url=conn.creds.instance_url, org_id=conn.creds.org_id)
        if conn is not None
        else None
    )
    written: list[Path] = []
    pdf_ok = True

    for api_name, spec in filtered.items():
        if pdf_ok:
            try:
                written.append(render_pdf(spec, out_dir / f"{api_name}_DS.pdf"))
                on_progress(f"Rendered {api_name} (PDF)")
                continue
            except PdfBackendUnavailable:
                pdf_ok = False
                on_progress("WeasyPrint native libs unavailable — writing HTML instead.")
        written.append(render_html_file(spec, out_dir / f"{api_name}_DS.html"))
        on_progress(f"Rendered {api_name} (HTML)")

    ordered = list(filtered.values())
    if pdf_ok:
        try:
            written.append(render_combined_pdf(ordered, out_dir / "Combined_DS.pdf", meta))
        except PdfBackendUnavailable:
            pdf_ok = False
    if not pdf_ok:
        written.append(
            render_combined_html_file(ordered, out_dir / "Combined_DS.html", meta)
        )
    on_progress("Rendered Combined document")

    return written, "PDF" if pdf_ok else "HTML"
