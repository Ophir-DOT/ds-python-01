# ds-tool — Salesforce Design Specification PDF generator

Standalone Python tool that scans a Salesforce org and emits a Design Specification PDF per object. Replaces the in-org Aura/Apex tool in `force-app/` with a faster, leaner pipeline. Ships with both a CLI (`ds-tool`) and a native desktop GUI (`ds-tool-gui`, PySide6).

## Why a rewrite?

| Pain point in the SF tool | Fix in ds-tool |
| --- | --- |
| Performance — every object re-queried Profile/PermissionSet metadata | Single-pass profile fetch cached for the whole run (`cache.ProfileCache`) |
| Multiple permission sets → re-run per object | All profiles + permission sets fetched once; applied to every object in one run |
| Brittle Lightning UI | Runs anywhere: `ds-tool generate` (CLI) or `ds-tool-gui` (native PySide6 desktop app) |
| Truncated permission tables with many profiles | Permissions section is chunked into stacked tables of ≤ 6 columns each, on landscape A4 |
| External `dot-portal.herokuapp.com` PDF service | WeasyPrint renders locally; no external service |

## Install

```bash
cd python
pip install -e .[dev]
```

Prereqs: Python 3.10+, `sf` CLI authorized for your target org(s).

WeasyPrint needs system libraries (Cairo, Pango). On Windows install via [GTK runtime](https://weasyprint.readthedocs.io/en/stable/install.html#windows).

### Metadata API WSDL

The Metadata API is SOAP, so the client needs a WSDL. On first run, ds-tool downloads it from the authorized org (`/services/wsdl/metadata`) and caches it at `ds_tool/metadata_wsdl/metadata.wsdl`. No manual setup. To force a refresh, delete that file.

## Usage

```bash
# Authorize once via SFDX (browser flow)
sf org login web --alias prod

# Generate a PDF per object (bash / zsh)
ds-tool generate \
    --org-alias prod \
    --objects Account,Opportunity \
    --profiles "System Administrator,Sales User" \
    --permission-sets "DotCompliance" \
    --out ./out
```

PowerShell uses backticks for line continuation:

```powershell
ds-tool generate `
    --org-alias prod `
    --objects Account,Opportunity `
    --profiles "System Administrator,Sales User" `
    --permission-sets "DotCompliance" `
    --out ./out
```

Outputs are nested per org id: `./out/<orgId>/Account_DS.pdf`, `Opportunity_DS.pdf`, plus a `Combined_DS.pdf` containing every selected object (page-broken between them). If WeasyPrint's native libs are unavailable, ds-tool transparently writes `.html` instead of `.pdf`.

Omit `--profiles` / `--permission-sets` to default to every Profile/PermissionSet that has at least one active assignee (matches the SF tool's default selection).

## Desktop GUI

```bash
ds-tool-gui              # installed entry point
python -m ds_tool.gui    # or run the module directly
```

A native PySide6 app that mirrors the original Aura UI's option selection across four tabs:

- **Design Specification** — pick objects (with a "Show CompSuite objects only" filter) + profiles/permission sets (auto-fetched from the org), then Generate Report (PDF/HTML) or Excel Export.
- **URS, PQ & Traceability** — object selection + project name. *Disabled (later phase).*
- **Multiple & Compare** — CSV-driven batch: export request template/example, import, Generate DS. *Compare actions are disabled (later phase).*
- **Settings** — four wired render-time exclusions (validation rules, workflow rules, email alerts, formula fields). Other toggles (related lists, date/time, FLS-suffix strip, explicit profile selection) are disabled until wired.

Connect a **Source** org by `sf` alias from the top bar — orgs are listed via `sf org list`. Auth reuses the same `sf` CLI authorization as the CLI; no passwords are entered in the app. The **Compare** org slot is disabled until the org-to-org compare backend lands.

**Demo mode** runs the whole UI against synthetic data with no org required — useful for trying the app or for screenshots/recordings:

```bash
ds-tool-gui --demo
```

> Features that have no backend yet are **disabled in the UI** (greyed out with a "later phase" note) rather than failing silently: org-to-org Compare, the full URS/PQ document, and the Custom Settings / Custom Metadata Types collectors. See the Roadmap.

### Branding

The GUI uses the **Dot Compliance** brand theme (`ds_tool/gui/theme.py`) — purple/pink/white palette, a purple header bar with the DOT mark, Quicksand UI font, and JetBrains Mono for technical text. Fonts and the logo are bundled under `ds_tool/gui/assets/`. The theme implements the "Branded baseline" direction from the design handoff; the source wireframes/brand guidelines are saved under `../design/dotlocalclient/`.

## Layout

```
ds_tool/
  auth.py            sf CLI → access token + instance URL; list_orgs() for the GUI picker
  client.py          httpx (REST/Tooling) + zeep (Metadata SOAP)
  cache.py           per-run ProfileCache
  collector.py       asyncio.gather orchestration with bounded concurrency
  filters.py         render-time section exclusions (Settings tab)
  metadata/          one module per metadata type
  metadata/catalog.py  list org objects + profiles for the GUI selection lists
  pdf/render.py      Jinja2 + WeasyPrint
  pdf/templates/     base + section templates, print CSS
  excel/export.py    openpyxl workbook export (one sheet per section)
  gui/               PySide6 desktop app (tabs/, widgets/, async_bridge, actions)
  cli.py             Click CLI entry point
```

## Tests

```bash
pytest
```

Tests use recorded JSON fixtures / stubbed clients and don't require a live org.

### UI test + recording

`tools/ui_test_record.py` drives the GUI through every tab/option/button and stitches the captured frames into a GIF + MP4 under `test_recording/`.

```bash
# Demo mode (no org required)
QT_QPA_PLATFORM=offscreen python tools/ui_test_record.py

# Live mode against a real sf alias (end-to-end)
QT_QPA_PLATFORM=offscreen python tools/ui_test_record.py --live <alias>
```

`QT_QPA_PLATFORM=offscreen` renders headlessly so it runs in CI / over SSH.

## Packaging (PyInstaller)

```bash
pyinstaller ds_tool.spec        # from python/
# → dist/ds-tool-gui/ds-tool-gui.exe
```

Notes baked into `ds_tool.spec`:

- **WeasyPrint** needs GTK native libs (Pango/Cairo/GObject), which PyInstaller can't bundle reliably on Windows. The frozen app degrades to HTML output when they're missing; install the GTK runtime on the host for PDFs.
- The **`sf` CLI is not bundled** — it's invoked via subprocess, so the host must have Salesforce CLI on `PATH`.

## Roadmap

- Org-to-org **Compare** (object diff, Apex classes, profiles/permission sets) — counterpart to the SF tool's `compareMultiple`.
- **Custom Settings** & **Custom Metadata Types** collectors + render/Excel.
- Full **URS / PQ** document (the Traceability tab currently emits a preliminary CSV).
