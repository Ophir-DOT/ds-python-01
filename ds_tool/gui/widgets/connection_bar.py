"""Top connection bar: pick + connect a Source org and a Compare org (sf aliases)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...auth import AuthError, OrgInfo, list_orgs, resolve_org
from ...client import SalesforceClient
from ...metadata.catalog import list_objects, list_profiles_permsets
from ..async_bridge import run_async
from ..demo import DEMO_OBJECTS, DEMO_ORGS, DEMO_PROFILES, demo_creds
from ..state import AppState, OrgConnection


class ConnectionBar(QWidget):
    connected = Signal(str)  # role: "source" | "compare"

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._combos: dict[str, QComboBox] = {}
        self._status: dict[str, QLabel] = {}

        row = QHBoxLayout(self)
        row.addWidget(self._org_panel("Source Org", "source"))
        row.addWidget(self._org_panel("Compare Org (optional)", "compare"))

        self.refresh_btn = QPushButton("Refresh orgs")
        self.refresh_btn.clicked.connect(self.populate_orgs)
        side = QVBoxLayout()
        side.addWidget(self.refresh_btn)
        side.addStretch(1)
        side_box = QWidget()
        side_box.setLayout(side)
        row.addWidget(side_box)

        self.populate_orgs()

    def _org_panel(self, title: str, role: str) -> QGroupBox:
        box = QGroupBox(title)
        combo = QComboBox()
        combo.setObjectName(f"{role}_combo")
        connect_btn = QPushButton("Connect")
        connect_btn.setObjectName(f"{role}_connect")
        connect_btn.clicked.connect(lambda: self._on_connect(role))
        status = QLabel("Not connected")
        status.setObjectName(f"{role}_status")

        self._combos[role] = combo
        self._status[role] = status

        if role == "compare":
            # Compare features are a later phase, so connecting a second org has
            # no use yet — disable it to avoid confusion.
            combo.setEnabled(False)
            connect_btn.setEnabled(False)
            tip = "Not yet available — org-to-org compare is planned for a later phase."
            combo.setToolTip(tip)
            connect_btn.setToolTip(tip)
            status.setText("Compare features coming in a later phase.")

        top = QHBoxLayout()
        top.addWidget(combo, 1)
        top.addWidget(connect_btn)
        layout = QVBoxLayout(box)
        layout.addLayout(top)
        layout.addWidget(status)
        return box

    # ---- org list ---------------------------------------------------------

    def populate_orgs(self) -> None:
        orgs = DEMO_ORGS if self._state.demo else self._list_orgs_safe()
        for combo in self._combos.values():
            combo.clear()
            if not orgs:
                combo.addItem("<no authorized orgs>", userData=None)
            for org in orgs:
                combo.addItem(org.display, userData=org.target)

    def _list_orgs_safe(self) -> list[OrgInfo]:
        try:
            return list_orgs()
        except AuthError as exc:
            QMessageBox.warning(self, "Salesforce CLI", str(exc))
            return []

    # ---- connect ----------------------------------------------------------

    def _on_connect(self, role: str) -> None:
        combo = self._combos[role]
        target = combo.currentData()
        if not target:
            QMessageBox.warning(self, "Connect", "No org selected.")
            return

        if self._state.demo:
            org = next((o for o in DEMO_ORGS if o.target == target), DEMO_ORGS[0])
            self._apply(role, OrgConnection(demo_creds(org), list(DEMO_OBJECTS), list(DEMO_PROFILES)))
            return

        self._status[role].setText(f"Connecting to {target}…")

        async def _coro(_progress):
            creds = resolve_org(target)
            client = SalesforceClient(creds)
            try:
                objects = await list_objects(client)
                profiles = await list_profiles_permsets(client)
            finally:
                await client.aclose()
            return OrgConnection(creds, objects, profiles)

        run_async(
            self,
            _coro,
            on_done=lambda conn: self._apply(role, conn),
            on_error=lambda exc: self._on_error(role, exc),
        )

    def _apply(self, role: str, conn: OrgConnection) -> None:
        if role == "source":
            self._state.source = conn
        else:
            self._state.compare = conn
        self._status[role].setText(
            f"Connected: {conn.creds.username}  ·  {len(conn.objects)} objects, "
            f"{len(conn.profiles)} profiles/perm sets"
        )
        self.connected.emit(role)

    def _on_error(self, role: str, exc: Exception) -> None:
        self._status[role].setText("Connection failed")
        QMessageBox.critical(self, "Connection failed", str(exc))
