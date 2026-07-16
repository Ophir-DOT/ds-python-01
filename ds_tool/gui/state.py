"""Shared application state passed to every tab."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..auth import OrgCredentials
from ..filters import ReportSettings
from ..metadata.catalog import ObjectRef, ProfileRef


@dataclass
class OrgConnection:
    """One connected org plus its cached catalogs."""

    creds: OrgCredentials
    objects: list[ObjectRef] = field(default_factory=list)
    profiles: list[ProfileRef] = field(default_factory=list)


@dataclass
class AppState:
    demo: bool = False
    out_dir: Path = field(default_factory=lambda: Path.cwd() / "out")
    settings: ReportSettings = field(default_factory=ReportSettings)
    source: OrgConnection | None = None
    compare: OrgConnection | None = None

    @property
    def source_connected(self) -> bool:
        return self.source is not None

    @property
    def compare_connected(self) -> bool:
        return self.compare is not None
