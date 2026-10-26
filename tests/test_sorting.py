"""Tests for build_route (the aisle/department sort key in api.py).

Component modules are loaded via tests/conftest.py under a stub
package name, because the real package __init__ imports Home
Assistant. Only the pure sort logic is exercised; no network or HA
calls are made.
"""

from conftest import load_component_module

api = load_component_module("api")
STORE_PRESETS = load_component_module("const").STORE_PRESETS


def _sorted_aisles(preset, aisles):
    key = api.build_route(STORE_PRESETS[preset]["order"])
    items = [{"aisle": aisle} for aisle in aisles]
    return [item["aisle"] for item in sorted(items, key=key)]


def test_standard_right_produce_before_aisles_before_unsorted():
    assert _sorted_aisles("standard_right", ["UNSORTED", "AISLE 5", "PRODUCE"]) == [
        "PRODUCE",
        "AISLE 5",
        "UNSORTED",
    ]


def test_numbered_aisles_sort_numerically_not_lexically():
    assert _sorted_aisles("standard_right", ["AISLE 12", "AISLE 2"]) == ["AISLE 2", "AISLE 12"]


def test_longest_department_match_wins():
    # PACKAGED MEAT must match its own bucket, not the generic MEAT bucket.
    assert _sorted_aisles("standard_right", ["PACKAGED MEAT", "MEAT"]) == ["MEAT", "PACKAGED MEAT"]


def test_marketplace_range_tokens_interleave():
    # Aisles 1-20 come before the fresh wall; aisles 21+ come after it.
    assert _sorted_aisles("marketplace", ["AISLE 25", "DAIRY", "AISLE 5"]) == [
        "AISLE 5",
        "DAIRY",
        "AISLE 25",
    ]


def test_urban_compact_interleaved_ranges():
    assert _sorted_aisles("urban_compact", ["AISLE 10", "DELI", "AISLE 2"]) == [
        "AISLE 2",
        "DELI",
        "AISLE 10",
    ]


def test_cold_chain_last_keeps_frozen_at_the_end():
    assert _sorted_aisles("cold_chain_last", ["FROZEN", "AISLE 3", "PRODUCE"]) == [
        "PRODUCE",
        "AISLE 3",
        "FROZEN",
    ]


def test_custom_empty_order_falls_back_to_aisle_string():
    assert _sorted_aisles("custom", ["PRODUCE", "AISLE 2"]) == ["AISLE 2", "PRODUCE"]
