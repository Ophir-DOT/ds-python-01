"""Scripted UI test + screen recorder for the Design Specification Tool GUI.

Runs the app in demo mode (no Salesforce org needed), drives every tab —
toggling options and clicking every button — and captures a screenshot frame
per step. Frames are stitched into an animated GIF (and MP4 if imageio is
available) so the whole test run is recorded.

Usage:
    QT_QPA_PLATFORM=offscreen python tools/ui_test_record.py
Outputs under  python/test_recording/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["DS_TOOL_DEMO"] = "1"

# Make the package importable when run as a loose script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from ds_tool.gui.main_window import MainWindow  # noqa: E402
from ds_tool.gui.state import AppState  # noqa: E402
from ds_tool.gui.theme import apply_theme  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REC_DIR = ROOT / "test_recording"


class Recorder:
    def __init__(self, app: QApplication, win: MainWindow, name: str = "ui_test") -> None:
        self.app = app
        self.win = win
        self.name = name
        self.frames: list[tuple[Path, str]] = []
        self.frames_dir = REC_DIR / f"{name}_frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        for old in self.frames_dir.glob("*.png"):
            old.unlink()

    def pump(self, times: int = 5) -> None:
        for _ in range(times):
            self.app.processEvents()

    def snap(self, caption: str) -> None:
        self.win.statusBar().showMessage(f"STEP {len(self.frames) + 1}: {caption}")
        self.pump()
        pix = self.win.grab()
        path = self.frames_dir / f"f{len(self.frames):03d}.png"
        pix.save(str(path))
        self.frames.append((path, caption))
        print(f"  [frame {len(self.frames):02d}] {caption}")


def drive(rec: Recorder, win: MainWindow) -> None:
    """Exercise every ENABLED control. Disabled (later-phase) controls are
    shown but not clicked — Qt ignores clicks on disabled widgets anyway."""
    tabs = win.tabs

    # --- Connection ----------------------------------------------------
    rec.snap("App launched (demo mode) — Design Specification tab")
    win.connection._on_connect("source")
    rec.snap("Connected Source org (demo) — catalogs loaded (Compare org disabled)")

    # --- Design Specification -----------------------------------------
    tabs.setCurrentWidget(win.design)
    win.design.compsuite_only.setChecked(True)
    rec.snap("Design Spec: 'Show CompSuite objects only' filters the available list")
    win.design.compsuite_only.setChecked(False)
    win.design.objects.select_keys(["Account", "Claim__c", "Opportunity"])
    rec.snap("Design Spec: selected 3 objects")
    win.design.profiles.select_keys(["Admin", "Standard", "Sales_User_PS"])
    rec.snap("Design Spec: selected profiles/permission sets")

    win.design.generate_btn.click()
    rec.snap("Clicked 'Generate Report' — wrote per-object + combined docs")
    win.design.excel_btn.click()
    rec.snap("Clicked 'Excel Export' — wrote DesignSpec.xlsx")
    win.design.profiles_btn.click()
    rec.snap("Clicked 'Generate Profiles & Permission Sets'")
    rec.snap("(Custom Settings / Custom Metadata Types buttons disabled — later phase)")

    # --- Settings ------------------------------------------------------
    tabs.setCurrentWidget(win.settings)
    rec.snap("Settings tab (no-op exclusions disabled, 4 working ones enabled)")
    for cb in (
        win.settings.cb_formula,
        win.settings.cb_state,
        win.settings.cb_email,
        win.settings.cb_rules,
    ):
        cb.setChecked(True)
    rec.snap("Settings: enabled the 4 wired report exclusions")

    # --- Traceability (disabled) --------------------------------------
    tabs.setCurrentWidget(win.traceability)
    rec.snap("URS / Traceability tab — disabled (later phase), controls greyed out")

    # --- Multiple & Compare -------------------------------------------
    tabs.setCurrentWidget(win.multiple)
    rec.snap("Multiple & Compare tab (Compare buttons disabled — later phase)")
    win.multiple.export_template_btn.click()
    win.multiple.export_example_btn.click()
    rec.snap("Exported CSV template + request example")
    example_csv = win._state.out_dir / "Request_Example.csv"
    win.multiple.import_csv(example_csv)
    rec.snap("Imported request CSV — results table populated")
    win.multiple.generate_ds_btn.click()
    rec.snap("Clicked 'Generate DS' — batch generated, Output column filled")

    tabs.setCurrentWidget(win.design)
    rec.snap("Test run complete — all ENABLED options and buttons exercised")


def wait_idle(app: QApplication, timeout: float = 300.0) -> None:
    """Pump the Qt loop until all background workers finish (live mode)."""
    import time

    from ds_tool.gui.async_bridge import _LIVE_WORKERS

    start = time.time()
    while _LIVE_WORKERS and time.time() - start < timeout:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()


def drive_live(rec: Recorder, win: MainWindow, app: QApplication, alias: str) -> None:
    rec.snap("App launched (LIVE mode) — Design Specification tab")

    combo = win.connection._combos["source"]
    # `sf org list` may report this org by username only (not the alias), so the
    # alias might be absent from the dropdown. resolve_org handles the alias, so
    # inject it explicitly to guarantee we target exactly the requested org.
    idx = next((i for i in range(combo.count()) if combo.itemData(i) == alias), -1)
    if idx < 0:
        combo.insertItem(0, alias, alias)
        idx = 0
    combo.setCurrentIndex(idx)
    rec.snap(f"Selected org alias '{alias}'")

    win.connection._on_connect("source")
    rec.snap(f"Connecting to '{alias}' (resolving creds + fetching catalogs)…")
    wait_idle(app)
    src = win._state.source
    rec.snap(
        f"Connected: {src.creds.username} — "
        f"{len(src.objects)} objects, {len(src.profiles)} profiles/perm sets"
    )

    have = {o.api_name for o in src.objects}
    objects = [o for o in ("Account", "CompSuite__Action_Item__c", "Contact") if o in have][:2]
    win.design.objects.select_keys(objects)
    rec.snap(f"Selected objects: {objects}")

    names = [p.name for p in src.profiles if p.kind == "Profile"]
    profiles = [n for n in names if n == "System Administrator"][:1]
    for n in names:
        if len(profiles) >= 2:
            break
        if n not in profiles:
            profiles.append(n)
    win.design.profiles.select_keys(profiles)
    rec.snap(f"Selected profiles (limits the run): {profiles}")

    win.design.generate_btn.click()
    rec.snap("Clicked 'Generate Report' — collecting live metadata…")
    wait_idle(app)
    rec.snap("Live report generated (per-object + combined)")

    win.design.excel_btn.click()
    rec.snap("Clicked 'Excel Export' — collecting + writing xlsx…")
    wait_idle(app)
    rec.snap("Live Excel export complete — test run finished")


def assemble(rec: Recorder) -> None:
    from PIL import Image, ImageDraw, ImageFont

    try:
        caption_font = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 18)
    except OSError:
        caption_font = ImageFont.load_default()

    raw = [(Image.open(p).convert("RGB"), cap) for p, cap in rec.frames]
    # Window width grows as status text widens; normalize every frame to a
    # single canvas size so GIF/MP4 encoders get uniform dimensions.
    max_w = max(im.width for im, _ in raw)
    max_h = max(im.height for im, _ in raw)
    caption_h = 34
    cw = max_w + (max_w % 2)
    ch = max_h + caption_h
    ch += ch % 2

    images = []
    for im, caption in raw:
        canvas = Image.new("RGB", (cw, ch), "white")
        canvas.paste(im, (0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text((10, max_h + 8), caption[:160], fill="black", font=caption_font)
        images.append(canvas)

    gif_path = REC_DIR / f"{rec.name}.gif"
    images[0].save(
        gif_path,
        save_all=True,
        append_images=images[1:],
        duration=1400,
        loop=0,
    )
    print(f"GIF written: {gif_path}  ({len(images)} frames)")

    try:
        import imageio.v2 as imageio
        import numpy as np

        mp4_path = REC_DIR / f"{rec.name}.mp4"
        writer = imageio.get_writer(str(mp4_path), fps=10, macro_block_size=1)
        for im in images:
            frame = np.asarray(im)
            for _ in range(14):  # ~1.4s per step at 10 fps
                writer.append_data(frame)
        writer.close()
        print(f"MP4 written: {mp4_path}")
    except Exception as exc:  # noqa: BLE001 - MP4 is best-effort; GIF is the primary artifact
        print(f"MP4 skipped ({exc})")


def main() -> int:
    live_alias = None
    if "--live" in sys.argv:
        i = sys.argv.index("--live")
        live_alias = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    demo = live_alias is None

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    state = AppState(demo=demo, out_dir=ROOT / ("out_demo" if demo else "out_live"))
    win = MainWindow(state)
    win.resize(1060, 840)
    win.show()
    app.processEvents()

    rec = Recorder(app, win, name="ui_test" if demo else "ui_test_live")
    if demo:
        print("Driving UI test (demo mode)...")
        drive(rec, win)
    else:
        print(f"Driving UI test (LIVE against '{live_alias}')...")
        drive_live(rec, win, app, live_alias)
    print(f"Captured {len(rec.frames)} frames. Assembling recording...")
    assemble(rec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
