from __future__ import annotations

from ds_tool.metadata.record_types import _parse_picklist_values


def test_parse_picklist_values_basic() -> None:
    raw = {
        "fullName": "Account.Customer",
        "picklistValues": [
            {
                "picklist": "Industry",
                "values": [
                    {"fullName": "Banking", "default": "false"},
                    {"fullName": "Insurance", "default": "true"},
                ],
            },
            {
                "picklist": "Type",
                "values": [{"fullName": "Prospect"}, {"fullName": "Customer"}],
            },
        ],
    }
    result = _parse_picklist_values(raw)
    assert result == {
        "Industry": ["Banking", "Insurance"],
        "Type": ["Prospect", "Customer"],
    }


def test_parse_picklist_values_singular_collapsed() -> None:
    # readMetadata returns a single dict instead of a list when there's only one entry.
    raw = {
        "picklistValues": {
            "picklist": "Stage",
            "values": {"fullName": "Closed Won"},
        }
    }
    assert _parse_picklist_values(raw) == {"Stage": ["Closed Won"]}


def test_parse_picklist_values_handles_missing_values() -> None:
    raw = {
        "picklistValues": [
            {"picklist": "Industry", "values": []},
            {"picklist": "Type"},  # no values key at all
        ]
    }
    assert _parse_picklist_values(raw) == {}


def test_parse_picklist_values_url_decodes_fullnames() -> None:
    # Salesforce returns picklist value fullName percent-encoded so it's a safe
    # XML/identifier token; we decode it back to the SF setup-UI label.
    raw = {
        "picklistValues": [
            {
                "picklist": "Xact_impacted_sites__c",
                "values": [
                    {"fullName": "HMSP %28GHQ%29"},
                    {"fullName": "Global %28All Sites%29"},
                    {"fullName": "GDC"},
                ],
            }
        ]
    }
    assert _parse_picklist_values(raw) == {
        "Xact_impacted_sites__c": ["HMSP (GHQ)", "Global (All Sites)", "GDC"]
    }


def test_parse_picklist_values_skips_entries_without_picklist_name() -> None:
    raw = {
        "picklistValues": [
            {"values": [{"fullName": "Foo"}]},  # no picklist key
            {"picklist": "", "values": [{"fullName": "Bar"}]},  # empty picklist
        ]
    }
    assert _parse_picklist_values(raw) == {}
