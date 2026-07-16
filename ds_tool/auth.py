"""Resolve a Salesforce org from a `sf` CLI alias.

Shells out to `sf org display --target-org <alias> --json` and extracts the
access token and instance URL so we can attach to existing authorizations
without running an OAuth flow ourselves.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


class AuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class OrgCredentials:
    alias: str
    access_token: str
    instance_url: str
    username: str
    org_id: str
    api_version: str = "59.0"


@dataclass(frozen=True)
class OrgInfo:
    """A single authorized org, as listed by `sf org list`."""

    alias: str
    username: str
    is_default: bool = False

    @property
    def display(self) -> str:
        label = self.alias or self.username
        if self.alias and self.username and self.alias != self.username:
            label = f"{self.alias} ({self.username})"
        return f"{label} (default)" if self.is_default else label

    @property
    def target(self) -> str:
        """The value to pass to `resolve_org` — alias if set, else username."""
        return self.alias or self.username


def _find_sf() -> str:
    sf_path = shutil.which("sf")
    if not sf_path:
        raise AuthError(
            "The `sf` CLI was not found on PATH. Install Salesforce CLI and run "
            "`sf org login web --alias <name>` before using ds-tool."
        )
    return sf_path


def _looks_redacted(token: str | None) -> bool:
    """True when `sf org display` gave us no usable access token.

    The Salesforce CLI security update (production 2026-05-27) redacts secrets
    from `sf org display --json`; the accessToken field comes back empty or as a
    placeholder like '<redacted>'. In that case we must read the real token from
    the dedicated `org auth show-access-token` command instead.
    """
    if not token:
        return True
    t = token.strip().lower()
    return not t or "redact" in t or t in ("<redacted>", "***", "********", "null")


def _fetch_access_token(sf_path: str, alias: str) -> str | None:
    """Read a live access token via `sf org auth show-access-token`.

    `--no-prompt` skips the interactive "reveal sensitive info?" confirmation so
    this works non-interactively (GUI / CI). Returns None if the command is
    unavailable (older CLI) or fails.
    """
    try:
        completed = subprocess.run(
            [
                sf_path, "org", "auth", "show-access-token",
                "--target-org", alias, "--no-prompt", "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    result = payload.get("result")
    if isinstance(result, str):
        return result.strip() or None
    if isinstance(result, dict):
        tok = result.get("accessToken") or result.get("token")
        return (tok or "").strip() or None
    return None


def list_orgs() -> list[OrgInfo]:
    """Return every authorized org from `sf org list --json`.

    Used to populate the GUI connection picker. Aggregates the org buckets the
    CLI reports (non-scratch, scratch, sandboxes, devhubs) and dedupes by
    username so an org that appears in several buckets is listed once.
    """
    sf_path = _find_sf()
    try:
        completed = subprocess.run(
            [sf_path, "org", "list", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise AuthError(f"Failed to invoke `sf` CLI: {exc}") from exc

    if completed.returncode != 0:
        raise AuthError(
            "`sf org list` failed:\n"
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AuthError(f"Could not parse `sf org list` JSON output: {exc}") from exc

    result = payload.get("result") or {}
    buckets = ("nonScratchOrgs", "scratchOrgs", "sandboxes", "devHubs", "other")
    orgs: list[OrgInfo] = []
    seen: set[str] = set()
    for bucket in buckets:
        for entry in result.get(bucket) or []:
            username = entry.get("username") or ""
            alias = entry.get("alias") or ""
            key = username or alias
            if not key or key in seen:
                continue
            seen.add(key)
            orgs.append(
                OrgInfo(
                    alias=alias,
                    username=username,
                    is_default=bool(entry.get("isDefaultUsername")),
                )
            )
    orgs.sort(key=lambda o: (not o.is_default, o.display.lower()))
    return orgs


def resolve_org(alias: str, api_version: str = "59.0") -> OrgCredentials:
    """Look up an alias previously authorized via `sf org login`."""
    # On Windows, `sf` resolves to sf.cmd. `subprocess.run(["sf", ...])` won't
    # auto-resolve the extension, so we capture the full path from `which`.
    sf_path = _find_sf()

    try:
        completed = subprocess.run(
            [sf_path, "org", "display", "--target-org", alias, "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise AuthError(f"Failed to invoke `sf` CLI: {exc}") from exc

    if completed.returncode != 0:
        raise AuthError(
            f"`sf org display --target-org {alias}` failed:\n"
            f"{completed.stderr.strip() or completed.stdout.strip()}\n"
            f"Authorize first with: sf org login web --alias {alias}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AuthError(f"Could not parse `sf` CLI JSON output: {exc}") from exc

    result = payload.get("result") or {}
    access_token = result.get("accessToken")
    instance_url = result.get("instanceUrl")
    username = result.get("username", "")
    org_id = result.get("id") or result.get("orgId") or ""

    # Post 2026-05-27, `sf org display` redacts the access token. Fall back to the
    # dedicated command that still reveals it.
    if _looks_redacted(access_token):
        access_token = _fetch_access_token(sf_path, alias)

    if not access_token or not instance_url:
        raise AuthError(
            f"`sf` CLI returned no usable accessToken/instanceUrl for alias '{alias}'.\n"
            "Recent Salesforce CLI versions redact secrets from `sf org display`; "
            "ds-tool now reads the token via `sf org auth show-access-token`. "
            "Make sure your CLI is up to date (`sf update`) and the org session is "
            f"valid, then re-authorize if needed: sf org login web --alias {alias}"
        )

    return OrgCredentials(
        alias=alias,
        access_token=access_token,
        instance_url=instance_url.rstrip("/"),
        username=username,
        org_id=org_id,
        api_version=api_version,
    )
