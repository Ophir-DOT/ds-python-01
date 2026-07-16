"""ds-tool CLI entry point."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from .auth import AuthError, resolve_org
from .cache import ProfileCache
from .client import SalesforceClient
from .collector import CollectInputs, collect_all
from .pdf.render import (
    PdfBackendUnavailable,
    ReportMeta,
    render_combined_html_file,
    render_combined_pdf,
    render_html_file,
    render_pdf,
)


def _split_csv(value: str | None, *, strip_all_whitespace: bool = False) -> tuple[str, ...] | None:
    """Split a comma/semicolon-separated list, normalizing whitespace.

    Terminal line-wrap on copy/paste often injects extra whitespace inside tokens
    (e.g. `CompSuit  e__Action_Item__c`, `System   Administrator`). We normalize:
      - strip_all_whitespace=True for tokens that can never contain spaces
        (sObject API names) — collapse all whitespace to nothing
      - default for tokens that may contain single spaces (profile labels) —
        collapse runs of whitespace to a single space, trim ends
    """
    if value is None:
        return None
    parts: list[str] = []
    for raw in value.replace(";", ",").split(","):
        if strip_all_whitespace:
            cleaned = re.sub(r"\s+", "", raw)
        else:
            cleaned = re.sub(r"\s+", " ", raw).strip()
        if cleaned:
            parts.append(cleaned)
    return tuple(parts) or None


@click.group()
@click.version_option(package_name="ds-tool")
def main() -> None:
    """Salesforce Design Specification generator."""


@main.command()
@click.option("--org-alias", required=True, help="`sf` CLI org alias (e.g. prod, dev1).")
@click.option(
    "--objects",
    required=True,
    help="Comma-separated SObject API names (e.g. Account,Opportunity).",
)
@click.option(
    "--profiles",
    default=None,
    help="Comma-separated Profile names. Omit to use all profiles with active users.",
)
@click.option(
    "--permission-sets",
    default=None,
    help="Comma-separated PermissionSet names. Omit to use all permission sets with assignees.",
)
@click.option(
    "--out",
    "out_dir",
    default="./out",
    type=click.Path(file_okay=False, path_type=Path),
    help="Output directory for PDFs.",
)
@click.option("--concurrency", default=8, show_default=True, type=int)
@click.option(
    "--api-version",
    default="59.0",
    show_default=True,
    help="Salesforce API version.",
)
def generate(
    org_alias: str,
    objects: str,
    profiles: str | None,
    permission_sets: str | None,
    out_dir: Path,
    concurrency: int,
    api_version: str,
) -> None:
    """Generate a Design Specification PDF per object."""
    object_list = _split_csv(objects, strip_all_whitespace=True) or ()
    if not object_list:
        raise click.UsageError("--objects must contain at least one API name")

    inputs = CollectInputs(
        objects=object_list,
        profile_names=_split_csv(profiles),
        permission_set_names=_split_csv(permission_sets, strip_all_whitespace=True),
        concurrency=concurrency,
    )

    try:
        asyncio.run(_run(org_alias, api_version, inputs, out_dir))
    except AuthError as exc:
        click.echo(f"Auth error: {exc}", err=True)
        sys.exit(2)


async def _run(
    org_alias: str,
    api_version: str,
    inputs: CollectInputs,
    out_dir: Path,
) -> None:
    console = Console()
    creds = resolve_org(org_alias, api_version=api_version)
    console.print(
        f"[bold]Authorized[/] as [cyan]{creds.username}[/] @ "
        f"[cyan]{creds.instance_url}[/]"
    )

    # Nest output by org id so multi-org runs don't clobber each other.
    org_slug = creds.org_id or creds.alias or "unknown_org"
    org_out_dir = out_dir / org_slug

    client = SalesforceClient(creds)
    cache = ProfileCache()
    pdf_failure: PdfBackendUnavailable | None = None
    written_format = "PDF"
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            prof_task = progress.add_task("Fetching profiles & permission sets…", total=1)
            from .collector import populate_profile_cache

            missing = await populate_profile_cache(
                client,
                cache,
                profile_names=inputs.profile_names,
                permission_set_names=inputs.permission_set_names,
            )
            progress.update(
                prof_task,
                completed=1,
                description=f"Profiles cached: {len(cache.all())} entries",
            )
        if missing:
            console.print(
                "[yellow]Warning:[/] no metadata returned for: "
                + ", ".join(missing)
                + "  (check spelling / Profile fullName vs. label)"
            )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:

            obj_task = progress.add_task(
                f"Collecting metadata for {len(inputs.objects)} object(s)…",
                total=len(inputs.objects),
            )

            def _on_done(_name: str) -> None:
                progress.update(obj_task, advance=1)

            specs = await collect_all(client, cache, inputs, on_done=_on_done)

            render_task = progress.add_task("Rendering PDFs…", total=len(specs) + 1)
            for api_name, spec in specs.items():
                if pdf_failure is None:
                    try:
                        render_pdf(spec, org_out_dir / f"{api_name}_DS.pdf")
                    except PdfBackendUnavailable as exc:
                        pdf_failure = exc
                if pdf_failure is not None:
                    render_html_file(spec, org_out_dir / f"{api_name}_DS.html")
                    written_format = "HTML"
                progress.update(render_task, advance=1)

            # Combined doc with every spec, page-broken between objects.
            ordered_specs = [specs[name] for name in inputs.objects if name in specs]
            meta = ReportMeta(
                instance_url=creds.instance_url, org_id=creds.org_id
            )
            if pdf_failure is None:
                try:
                    render_combined_pdf(
                        ordered_specs, org_out_dir / "Combined_DS.pdf", meta
                    )
                except PdfBackendUnavailable as exc:
                    pdf_failure = exc
            if pdf_failure is not None:
                render_combined_html_file(
                    ordered_specs, org_out_dir / "Combined_DS.html", meta
                )
                written_format = "HTML"
            progress.update(render_task, advance=1)
        if pdf_failure is not None:
            console.print(
                "[yellow]WeasyPrint could not load native libs[/] "
                "(libgobject/Pango/Cairo). Wrote HTML files instead. "
                "Install the GTK runtime to get PDFs: "
                "[link]https://weasyprint.readthedocs.io/en/stable/install.html#windows[/link]"
            )
    finally:
        await client.aclose()

    console.print(
        f"[green]Wrote {len(inputs.objects)} per-object {written_format} file(s) "
        f"+ Combined_DS.{written_format.lower()} to[/] "
        f"[bold]{org_out_dir.resolve()}"
    )


if __name__ == "__main__":
    main()
