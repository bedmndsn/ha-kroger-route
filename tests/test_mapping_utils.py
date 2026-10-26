"""Tests for mapping_utils (pure functions, no Home Assistant needed)."""

from conftest import load_component_module

mapping_utils = load_component_module("mapping_utils")
lines_to_list = mapping_utils.lines_to_list
lines_to_mapping = mapping_utils.lines_to_mapping
list_to_lines = mapping_utils.list_to_lines
mapping_to_lines = mapping_utils.mapping_to_lines


def test_lines_to_list_basic():
    assert lines_to_list("Milk\nEggs\n") == ["milk", "eggs"]


def test_lines_to_list_skips_blanks_comments_and_lowercases():
    text = "\n  # a comment\nMilk\n\n  EGGS  \n#another comment\n"
    assert lines_to_list(text) == ["milk", "eggs"]


def test_lines_to_list_none_and_empty():
    assert lines_to_list(None) == []
    assert lines_to_list("") == []


def test_list_to_lines_round_trip():
    assert list_to_lines(["milk", "eggs"]) == "milk\neggs"
    assert list_to_lines([]) == ""
    assert list_to_lines(None) == ""


def test_lines_to_mapping_separators():
    text = "yogrt = yogurt\noj: orange juice\nmaple syrup => 0001111050000\n"
    assert lines_to_mapping(text) == {
        "yogrt": "yogurt",
        "oj": "orange juice",
        "maple syrup": "0001111050000",
    }


def test_lines_to_mapping_skips_comments_blanks_and_malformed():
    text = "# comment\nyogrt = yogurt\n\nno separator here\n= missing key\nkey =\n"
    assert lines_to_mapping(text) == {"yogrt": "yogurt"}


def test_lines_to_mapping_lowercases_keys_only():
    assert lines_to_mapping("YOGRT = Yogurt") == {"yogrt": "Yogurt"}


def test_lines_to_mapping_none_and_empty():
    assert lines_to_mapping(None) == {}
    assert lines_to_mapping("") == {}


def test_mapping_to_lines_sorted():
    assert mapping_to_lines({"yogrt": "yogurt", "oj": "orange juice"}) == (
        "oj = orange juice\nyogrt = yogurt"
    )
    assert mapping_to_lines({}) == ""
    assert mapping_to_lines(None) == ""
