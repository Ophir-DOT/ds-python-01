"""Smoke tests for the Jinja-rendered HTML.

We don't run WeasyPrint here (it has heavy native deps); we render the HTML
and assert the structural properties that fix pain point #4 — long profile
lists are chunked into stacked tables instead of a single overflowing table.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ds_tool.models import (
    FieldPermission,
    FieldSpec,
    ObjectGeneralInfo,
    ObjectPermission,
    ObjectSpec,
    ProfileSpec,
)
from ds_tool.pdf.render import (
    PROFILE_CHUNK,
    ReportMeta,
    render_combined_html,
    render_html,
)


def _make_spec(num_profiles: int) -> ObjectSpec:
    profiles = [
        ProfileSpec(
            full_name=f"Profile{i:02d}",
            label=f"Profile {i}",
            kind="Profile",
            object_permissions=[ObjectPermission(obj="Account", read=True, edit=i % 2 == 0)],
            field_permissions=[
                FieldPermission(field="Account.Name", readable=True, editable=True)
            ],
        )
        for i in range(num_profiles)
    ]
    return ObjectSpec(
        general=ObjectGeneralInfo(
            api_name="Account", label="Account", plural_label="Accounts"
        ),
        fields=[FieldSpec(api_name="Name", label="Name", type="string")],
        profiles=profiles,
    )


def test_render_html_chunks_many_profiles_into_multiple_tables() -> None:
    # With 14 profiles and chunk size 6, expect ceil(14/6) = 3 chunks per section.
    spec = _make_spec(14)
    html = render_html(spec)
    assert html.count('class="perm"') >= 6  # 3 chunks × 2 sections (object perms + FLS)
    # Each chunk repeats the leftmost name column
    assert html.count('class="name"') > 6


def test_render_html_single_chunk_for_few_profiles() -> None:
    spec = _make_spec(3)
    html = render_html(spec)
    # 1 chunk per section = 2 perm tables total
    assert html.count('class="perm"') == 2


def test_profile_chunk_constant_matches_template_expectation() -> None:
    # Guard against accidentally changing the chunk size without updating tests
    assert PROFILE_CHUNK == 6


def test_combined_cover_includes_org_provenance() -> None:
    meta = ReportMeta(
        instance_url="https://example.my.salesforce.com",
        org_id="00D000000000123EAA",
        generated_at=datetime(2026, 6, 2, 14, 30, tzinfo=timezone.utc),
    )
    html = render_combined_html([_make_spec(1)], meta)
    assert "2026-06-02 14:30 UTC" in html
    assert "https://example.my.salesforce.com" in html
    assert "00D000000000123EAA" in html


def test_combined_cover_stamps_timestamp_without_org_meta() -> None:
    # No ReportMeta → only the generation timestamp is shown; URL/ID blocks omitted.
    html = render_combined_html([_make_spec(1)])
    assert "Generated" in html
    assert "Org URL" not in html
    assert "Org ID" not in html
