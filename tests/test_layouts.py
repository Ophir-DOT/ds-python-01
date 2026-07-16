"""Tests for ds_tool.metadata.layouts helpers.

Only the pure helper functions are tested here; the async fetch() functions
require a live Salesforce connection and are covered by integration/recording
tests elsewhere.
"""

from __future__ import annotations

import pytest

from ds_tool.metadata.layouts import STANDARD_PROFILE_NAMES, is_standard_profile


# ---------------------------------------------------------------------------
# is_standard_profile
# ---------------------------------------------------------------------------


class TestIsStandardProfile:
    def test_system_administrator_is_standard(self) -> None:
        assert is_standard_profile("System Administrator") is True

    def test_chatter_external_is_standard(self) -> None:
        assert is_standard_profile("Chatter External User") is True

    def test_analytics_cloud_is_standard(self) -> None:
        assert is_standard_profile("Analytics Cloud Integration User") is True

    def test_contract_manager_is_standard(self) -> None:
        assert is_standard_profile("Contract Manager") is True

    def test_guest_is_standard(self) -> None:
        assert is_standard_profile("Guest") is True

    def test_custom_profile_is_not_standard(self) -> None:
        assert is_standard_profile("My Custom Profile") is False

    def test_empty_string_is_not_standard(self) -> None:
        assert is_standard_profile("") is False

    def test_case_sensitive_mismatch(self) -> None:
        # The check must be exact-case; lower-cased versions are not standard.
        assert is_standard_profile("system administrator") is False
        assert is_standard_profile("SYSTEM ADMINISTRATOR") is False

    def test_partial_match_is_not_standard(self) -> None:
        # A substring of a standard name must not match.
        assert is_standard_profile("Administrator") is False
        assert is_standard_profile("Chatter") is False


# ---------------------------------------------------------------------------
# STANDARD_PROFILE_NAMES sanity checks
# ---------------------------------------------------------------------------


class TestStandardProfileNamesSet:
    def test_is_frozenset(self) -> None:
        assert isinstance(STANDARD_PROFILE_NAMES, frozenset)

    def test_not_empty(self) -> None:
        assert len(STANDARD_PROFILE_NAMES) > 0

    def test_no_empty_strings(self) -> None:
        assert "" not in STANDARD_PROFILE_NAMES

    def test_all_entries_are_strings(self) -> None:
        assert all(isinstance(name, str) for name in STANDARD_PROFILE_NAMES)

    def test_consistent_with_helper(self) -> None:
        # Every name in the set must return True from the helper.
        for name in STANDARD_PROFILE_NAMES:
            assert is_standard_profile(name), f"{name!r} should be standard"
