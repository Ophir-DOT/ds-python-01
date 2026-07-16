from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from ds_tool.metadata.apex_triggers import _classification, _code_length, _events, fetch


# ---------------------------------------------------------------------------
# _events
# ---------------------------------------------------------------------------

def test_events_collapses_usage_booleans() -> None:
    record = {
        "Name": "AccountTrigger",
        "Status": "Active",
        "ApiVersion": 59.0,
        "UsageBeforeInsert": True,
        "UsageBeforeUpdate": False,
        "UsageBeforeDelete": False,
        "UsageAfterInsert": True,
        "UsageAfterUpdate": True,
        "UsageAfterDelete": False,
        "UsageAfterUndelete": False,
    }
    assert _events(record) == ["before insert", "after insert", "after update"]


def test_events_empty_when_no_flags_set() -> None:
    assert _events({"Name": "X"}) == []


def test_events_preserves_canonical_order() -> None:
    # before-* must precede after-* regardless of dict insertion order.
    record = {
        "UsageAfterUndelete": True,
        "UsageBeforeInsert": True,
        "UsageAfterUpdate": True,
        "UsageBeforeDelete": True,
    }
    assert _events(record) == [
        "before insert",
        "before delete",
        "after update",
        "after undelete",
    ]


# ---------------------------------------------------------------------------
# _classification
# ---------------------------------------------------------------------------

def test_classification_package_when_namespace_present() -> None:
    assert _classification({"NamespacePrefix": "mypkg"}) == "Package"


def test_classification_custom_when_namespace_absent() -> None:
    assert _classification({}) == "Custom"


def test_classification_custom_when_namespace_empty_string() -> None:
    assert _classification({"NamespacePrefix": ""}) == "Custom"


def test_classification_custom_when_namespace_none() -> None:
    assert _classification({"NamespacePrefix": None}) == "Custom"


# ---------------------------------------------------------------------------
# _code_length
# ---------------------------------------------------------------------------

def test_code_length_prefers_length_without_comments() -> None:
    record = {"LengthWithoutComments": 120, "Body": "x" * 200}
    assert _code_length(record) == 120


def test_code_length_falls_back_to_body_length() -> None:
    record = {"Body": "trigger T on Account (before insert) {}"}
    assert _code_length(record) == len("trigger T on Account (before insert) {}")


def test_code_length_none_when_both_absent() -> None:
    assert _code_length({}) is None


def test_code_length_handles_string_length_without_comments() -> None:
    # Tooling API sometimes returns numeric fields as strings.
    assert _code_length({"LengthWithoutComments": "42"}) == 42


def test_code_length_falls_back_when_lwc_invalid() -> None:
    body = "abc"
    assert _code_length({"LengthWithoutComments": "not_a_number", "Body": body}) == len(body)


# ---------------------------------------------------------------------------
# fetch — integration via mock client
# ---------------------------------------------------------------------------

_USAGE_ALL_FALSE = {
    "UsageBeforeInsert": False,
    "UsageBeforeUpdate": False,
    "UsageBeforeDelete": False,
    "UsageAfterInsert": False,
    "UsageAfterUpdate": False,
    "UsageAfterDelete": False,
    "UsageAfterUndelete": False,
}

_CUSTOM_RECORD = {
    "Name": "AccountTrigger",
    "Status": "Active",
    "ApiVersion": 59.0,
    "NamespacePrefix": None,
    "LengthWithoutComments": 150,
    "Body": "trigger AccountTrigger on Account (before insert) { }",
    "UsageBeforeInsert": True,
    **{k: False for k, _ in [
        ("UsageBeforeUpdate", None),
        ("UsageBeforeDelete", None),
        ("UsageAfterInsert", None),
        ("UsageAfterUpdate", None),
        ("UsageAfterDelete", None),
        ("UsageAfterUndelete", None),
    ]},
}

_PACKAGE_RECORD = {
    "Name": "pkgAccountTrigger",
    "Status": "Active",
    "ApiVersion": 58.0,
    "NamespacePrefix": "mypkg",
    "LengthWithoutComments": 80,
    "Body": "trigger pkgAccountTrigger on Account (after insert) { }",
    **_USAGE_ALL_FALSE,
    "UsageAfterInsert": True,
}


def _make_client(records: list[dict]) -> AsyncMock:
    client = AsyncMock()
    client.tooling_query = AsyncMock(return_value={"records": records})
    return client


def test_fetch_custom_trigger_classification() -> None:
    client = _make_client([_CUSTOM_RECORD])
    specs = asyncio.get_event_loop().run_until_complete(fetch(client, "Account"))
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "AccountTrigger"
    assert spec.classification == "Custom"
    assert spec.code_length == 150
    assert spec.source == "trigger AccountTrigger on Account (before insert) { }"
    assert spec.events == ["before insert"]


def test_fetch_package_trigger_classification() -> None:
    client = _make_client([_PACKAGE_RECORD])
    specs = asyncio.get_event_loop().run_until_complete(fetch(client, "Account"))
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "pkgAccountTrigger"
    assert spec.classification == "Package"
    assert spec.code_length == 80
    assert spec.source == "trigger pkgAccountTrigger on Account (after insert) { }"
    assert spec.events == ["after insert"]


def test_fetch_mixed_triggers() -> None:
    client = _make_client([_CUSTOM_RECORD, _PACKAGE_RECORD])
    specs = asyncio.get_event_loop().run_until_complete(fetch(client, "Account"))
    assert len(specs) == 2
    classifications = {s.name: s.classification for s in specs}
    assert classifications["AccountTrigger"] == "Custom"
    assert classifications["pkgAccountTrigger"] == "Package"


def test_fetch_returns_empty_list_on_tooling_error() -> None:
    client = AsyncMock()
    client.tooling_query = AsyncMock(side_effect=RuntimeError("API error"))
    specs = asyncio.get_event_loop().run_until_complete(fetch(client, "Account"))
    assert specs == []


def test_fetch_source_none_when_body_absent() -> None:
    record = {
        "Name": "NoBodyTrigger",
        "Status": "Active",
        "ApiVersion": 59.0,
        "NamespacePrefix": None,
        "LengthWithoutComments": 10,
        "Body": None,
        **_USAGE_ALL_FALSE,
    }
    client = _make_client([record])
    specs = asyncio.get_event_loop().run_until_complete(fetch(client, "Account"))
    assert specs[0].source is None
