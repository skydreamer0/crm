import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from create_appointments import _lookup_item_matches, _resolved_lookup_selector


def test_resolved_lookup_selector_targets_read_and_edit_lookup_items():
    selector = _resolved_lookup_selector("new_product")

    assert "#new_product span.ms-crm-Lookup-Item[resolved='true']" in selector
    assert "#new_product_lookupDiv span.ms-crm-Lookup-Item[oid]" in selector


def test_lookup_item_matches_expected_from_productnumber_keyvalues():
    keyvalues = '{"productnumber":{"name":"productnumber","value":"T5EL1"}}'

    assert _lookup_item_matches(
        text="ELI 22.5 cancer medicine",
        title="ELI 22.5 cancer medicine",
        keyvalues=keyvalues,
        expected="T5EL1",
    )


def test_lookup_item_matches_expected_from_visible_text():
    assert _lookup_item_matches(
        text="了解需求",
        title="",
        keyvalues="",
        expected="了解需求",
    )


def test_lookup_item_rejects_unrelated_value():
    assert not _lookup_item_matches(
        text="ELI 22.5 cancer medicine",
        title="ELI 22.5 cancer medicine",
        keyvalues='{"productnumber":{"value":"T5EL1"}}',
        expected="T5EL2",
    )
