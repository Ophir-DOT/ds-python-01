"""Render ObjectSpec(s) to PDF/HTML via Jinja2 + WeasyPrint.

Two output shapes:
- One file per ObjectSpec  → render_pdf / render_html_file
- One combined file for many ObjectSpecs → render_combined_pdf / render_combined_html_file
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import islice
from pathlib import Path
from typing import Iterable, Iterator, Sequence, TypeVar

from jinja2 import Environment, PackageLoader, select_autoescape

from ..models import ObjectSpec

T = TypeVar("T")


@dataclass(frozen=True)
class ReportMeta:
    """Provenance shown on the combined report cover: which org, generated when.

    `instance_url`/`org_id` come from the resolved org credentials. `generated_at`
    defaults to render time (local time, see `_meta_context`) when left None.
    """

    instance_url: str | None = None
    org_id: str | None = None
    generated_at: datetime | None = None


def _meta_context(meta: ReportMeta | None) -> dict[str, str | None]:
    """Build the template variables for the combined-report cover provenance."""
    meta = meta or ReportMeta()
    generated = meta.generated_at or datetime.now().astimezone()
    return {
        "instance_url": meta.instance_url,
        "org_id": meta.org_id,
        # e.g. "2026-06-02 14:30 IDT"; %Z is empty on naive datetimes, so trim.
        "generated_at": generated.strftime("%Y-%m-%d %H:%M %Z").strip(),
    }

# Profiles-per-chunk cap that resolves the table-truncation issue.
# The current SF UI puts every profile in one wide table with hard-coded
# `width:30%/40%/44%`; >6 profiles overflow and get truncated. We split the
# permissions section into stacked tables of up to PROFILE_CHUNK columns.
PROFILE_CHUNK = 6


def _batched(iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    iterator = iter(iterable)
    while batch := list(islice(iterator, size)):
        yield batch


def _build_env() -> Environment:
    env = Environment(
        loader=PackageLoader("ds_tool.pdf", "templates"),
        # Templates are named "*.html.j2", so the extension select_autoescape sees
        # is ".j2" — include it (and default_for_string) so variable interpolation
        # is HTML-escaped. Without this, fields that contain markup (e.g. an email
        # template's raw HTML body) inject real tags and break the document.
        autoescape=select_autoescape(
            enabled_extensions=("html", "xml", "j2"),
            default_for_string=True,
        ),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["profile_chunks"] = lambda profiles: list(
        _batched(profiles, PROFILE_CHUNK)
    )
    env.globals["PROFILE_CHUNK"] = PROFILE_CHUNK
    return env


_ENV: Environment | None = None


def _env() -> Environment:
    global _ENV
    if _ENV is None:
        _ENV = _build_env()
    return _ENV


class PdfBackendUnavailable(RuntimeError):
    pass


class IncompleteRenderError(RuntimeError):
    """Raised when a rendered HTML document is missing its closing tags.

    Guards against silently writing a truncated .html file. With Jinja's
    full-string render() this should never trigger (render either completes or
    raises), but the explicit check turns any regression into a loud failure
    instead of an unnoticed partial document.
    """


def _assert_complete_html(html_str: str) -> str:
    if "</body>" not in html_str or not html_str.rstrip().endswith("</html>"):
        raise IncompleteRenderError(
            "Rendered HTML is missing </body>/</html> — refusing to write a "
            f"truncated document ({len(html_str)} chars)."
        )
    return html_str


def render_pdf(spec: ObjectSpec, output_path: Path) -> Path:
    try:
        from weasyprint import HTML  # imported lazily so module import stays cheap
    except (OSError, ModuleNotFoundError) as exc:
        # WeasyPrint raises OSError when libgobject/Pango/Cairo aren't installed
        # (typical on Windows without the GTK runtime). ModuleNotFoundError means
        # the package itself isn't installed — both cases fall back to HTML output.
        raise PdfBackendUnavailable(str(exc)) from exc

    html_str = _env().get_template("base.html.j2").render(spec=spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_str, base_url=str(_templates_dir())).write_pdf(str(output_path))
    return output_path


def render_html_file(spec: ObjectSpec, output_path: Path) -> Path:
    """Fallback when WeasyPrint can't load: emit standalone HTML + inlined CSS."""
    html_str = _assert_complete_html(_env().get_template("base.html.j2").render(spec=spec))
    css_path = _templates_dir() / "styles.css"
    css = css_path.read_text(encoding="utf-8")
    # Inline the stylesheet so the HTML is self-contained.
    html_str = html_str.replace(
        '<link rel="stylesheet" href="styles.css">',
        f"<style>{css}</style>",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_str, encoding="utf-8")
    return output_path


def render_html(spec: ObjectSpec) -> str:
    return _env().get_template("base.html.j2").render(spec=spec)


def _templates_dir() -> Path:
    import ds_tool.pdf as pdf_pkg

    return Path(pdf_pkg.__file__).parent / "templates"


def render_many(specs: Sequence[ObjectSpec], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for spec in specs:
        paths.append(render_pdf(spec, out_dir / f"{spec.general.api_name}_DS.pdf"))
    return paths


# ---- Combined-report variants ------------------------------------------------


def _render_combined_html_string(
    specs: Sequence[ObjectSpec], meta: ReportMeta | None = None
) -> str:
    return (
        _env()
        .get_template("combined.html.j2")
        .render(specs=list(specs), **_meta_context(meta))
    )


def render_combined_html(
    specs: Sequence[ObjectSpec], meta: ReportMeta | None = None
) -> str:
    """Combined report as an HTML string (cover includes org/timestamp meta)."""
    return _render_combined_html_string(specs, meta)


def render_combined_pdf(
    specs: Sequence[ObjectSpec], output_path: Path, meta: ReportMeta | None = None
) -> Path:
    """One PDF containing every spec, separated by page breaks."""
    try:
        from weasyprint import HTML
    except (OSError, ModuleNotFoundError) as exc:
        raise PdfBackendUnavailable(str(exc)) from exc

    html_str = _render_combined_html_string(specs, meta)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_str, base_url=str(_templates_dir())).write_pdf(str(output_path))
    return output_path


def render_combined_html_file(
    specs: Sequence[ObjectSpec], output_path: Path, meta: ReportMeta | None = None
) -> Path:
    """HTML fallback for the combined report. Self-contained: CSS is inlined."""
    html_str = _assert_complete_html(_render_combined_html_string(specs, meta))
    css_path = _templates_dir() / "styles.css"
    css = css_path.read_text(encoding="utf-8")
    html_str = html_str.replace(
        '<link rel="stylesheet" href="styles.css">',
        f"<style>{css}</style>",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_str, encoding="utf-8")
    return output_path
