from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ds_tool.auth import AuthError, resolve_org


class _CompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_resolve_org_parses_sf_output() -> None:
    payload = {
        "result": {
            "accessToken": "00Dxx!ABCDEF",
            "instanceUrl": "https://my-org.my.salesforce.com/",
            "username": "user@example.com",
            "id": "00DABC0000123ABC",
        }
    }
    with patch("ds_tool.auth.shutil.which", return_value="/usr/bin/sf"), \
         patch("ds_tool.auth.subprocess.run", return_value=_CompletedProcess(0, json.dumps(payload))):
        creds = resolve_org("prod")
    assert creds.access_token == "00Dxx!ABCDEF"
    assert creds.instance_url == "https://my-org.my.salesforce.com"
    assert creds.username == "user@example.com"
    assert creds.org_id == "00DABC0000123ABC"


def test_resolve_org_missing_sf_cli() -> None:
    with patch("ds_tool.auth.shutil.which", return_value=None):
        with pytest.raises(AuthError, match="sf` CLI was not found"):
            resolve_org("prod")


def test_resolve_org_unknown_alias() -> None:
    with patch("ds_tool.auth.shutil.which", return_value="/usr/bin/sf"), \
         patch(
             "ds_tool.auth.subprocess.run",
             return_value=_CompletedProcess(1, stderr="No org found"),
         ):
        with pytest.raises(AuthError, match="No org found"):
            resolve_org("ghost")
