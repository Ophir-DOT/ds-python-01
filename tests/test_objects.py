"""Tests for ds_tool.metadata.objects.fetch_general history-tracking logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from ds_tool.metadata import objects


def _run(coro):
    return asyncio.run(coro)


def _make_client(
    *,
    rest_payload: dict | None = None,
    describe_payload: dict | None = None,
    read_metadata_return: list | None = None,
    read_metadata_side_effect: Exception | None = None,
) -> MagicMock:
    """Build a minimal mock SalesforceClient."""
    client = MagicMock()
    client.creds = MagicMock()
    client.creds.api_version = "59.0"

    client.rest_get = AsyncMock(
        return_value=rest_payload
        if rest_payload is not None
        else {"name": "Account", "label": "Account", "labelPlural": "Accounts"}
    )
    client.describe = AsyncMock(
        return_value=describe_payload if describe_payload is not None else {}
    )

    if read_metadata_side_effect is not None:
        client.read_metadata = AsyncMock(side_effect=read_metadata_side_effect)
    else:
        client.read_metadata = AsyncMock(
            return_value=read_metadata_return if read_metadata_return is not None else []
        )

    return client


# ---------------------------------------------------------------------------
# enableHistory = true  →  history_tracking_enabled = True
# ---------------------------------------------------------------------------


def test_enable_history_true_sets_enabled() -> None:
    client = _make_client(
        describe_payload={"trackHistory": False},
        read_metadata_return=[{"fullName": "Account", "enableHistory": True}],
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is True


def test_enable_history_string_true_sets_enabled() -> None:
    """Metadata API sometimes returns booleans as strings."""
    client = _make_client(
        describe_payload={"trackHistory": False},
        read_metadata_return=[{"fullName": "Account", "enableHistory": "true"}],
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is True


# ---------------------------------------------------------------------------
# enableHistory absent or false  →  history_tracking_enabled = False
# ---------------------------------------------------------------------------


def test_enable_history_false_sets_disabled() -> None:
    client = _make_client(
        describe_payload={"trackHistory": True},  # should be overridden
        read_metadata_return=[{"fullName": "Account", "enableHistory": False}],
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is False


def test_enable_history_absent_uses_describe_track_history_true() -> None:
    """When enableHistory key is missing, describe.trackHistory is the source of truth."""
    client = _make_client(
        describe_payload={"trackHistory": True},
        read_metadata_return=[{"fullName": "Account"}],  # no enableHistory key
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is True


def test_enable_history_absent_uses_describe_track_history_false() -> None:
    client = _make_client(
        describe_payload={"trackHistory": False},
        read_metadata_return=[{"fullName": "Account"}],  # no enableHistory key
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is False


def test_empty_read_metadata_result_falls_back_to_describe() -> None:
    """If read_metadata returns an empty list, fall back to describe trackHistory."""
    client = _make_client(
        describe_payload={"trackHistory": True},
        read_metadata_return=[],
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is True


# ---------------------------------------------------------------------------
# hasSubtypes alone must NOT force history_tracking_enabled = True
# ---------------------------------------------------------------------------


def test_has_subtypes_alone_does_not_enable_history() -> None:
    """hasSubtypes indicates record types/subtypes — it must be ignored for history."""
    client = _make_client(
        describe_payload={"trackHistory": False, "hasSubtypes": True},
        read_metadata_return=[{"fullName": "Account", "enableHistory": False}],
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is False


def test_has_subtypes_true_with_no_metadata_record_stays_false() -> None:
    """Even when read_metadata is empty, hasSubtypes must not leak into history."""
    client = _make_client(
        describe_payload={"trackHistory": False, "hasSubtypes": True},
        read_metadata_return=[],
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is False


# ---------------------------------------------------------------------------
# read_metadata error  →  fall back to describe trackHistory (not hasSubtypes)
# ---------------------------------------------------------------------------


def test_read_metadata_error_falls_back_to_describe_track_history_true() -> None:
    client = _make_client(
        describe_payload={"trackHistory": True},
        read_metadata_side_effect=RuntimeError("SOAP fault"),
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is True


def test_read_metadata_error_falls_back_to_describe_track_history_false() -> None:
    client = _make_client(
        describe_payload={"trackHistory": False},
        read_metadata_side_effect=RuntimeError("SOAP fault"),
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is False


def test_read_metadata_error_with_has_subtypes_does_not_enable_history() -> None:
    """Fall-back on error must ignore hasSubtypes."""
    client = _make_client(
        describe_payload={"trackHistory": False, "hasSubtypes": True},
        read_metadata_side_effect=RuntimeError("SOAP fault"),
    )
    result = _run(objects.fetch_general(client, "Account"))
    assert result.history_tracking_enabled is False
