"""Focused edge coverage for nested merge and replacement path mechanics."""

from typing import Any

import pytest

from vltconfig.errors import ConfigurationApplyError
from vltconfig.operations import (
    _added_leaf_paths,
    _apply_replacements,
    _lookup_value,
    _merge_missing,
    _set_value,
)


@pytest.mark.unit
def test_added_leaf_paths_handles_empty_and_nested_containers() -> None:
    """Empty containers and list indexes remain visible in redacted results."""
    assert _added_leaf_paths({}, ("mapping",)) == [("mapping",)]
    assert _added_leaf_paths([], ("items",)) == [("items",)]
    assert _added_leaf_paths(
        [{}, [], {"token": "placeholder"}],
        ("items",),
    ) == [
        ("items", 0),
        ("items", 1),
        ("items", 2, "token"),
    ]


@pytest.mark.unit
def test_merge_missing_recurses_through_lists_without_overwriting() -> None:
    """List-backed AliasPath templates add only absent nested structure."""
    current: list[Any] = [{"existing": "kept"}, []]
    required: list[Any] = [
        {"existing": "ignored", "missing": "placeholder"},
        ["placeholder"],
        {"new": "placeholder"},
    ]

    added = _merge_missing(current, required, prefix=("items",))

    assert current == [
        {"existing": "kept", "missing": "placeholder"},
        ["placeholder"],
        {"new": "placeholder"},
    ]
    assert added == [
        ("items", 0, "missing"),
        ("items", 1, 0),
        ("items", 2, "new"),
    ]


@pytest.mark.unit
def test_lookup_distinguishes_missing_indexes_keys_and_wrong_shapes() -> None:
    """Concrete replacement paths fail closed without rendering encountered values."""
    payload = {"items": [{"token": None}]}

    assert _lookup_value(payload, ("items", 0, "token")) == (True, None)
    assert _lookup_value(payload, ("missing",)) == (False, None)
    assert _lookup_value(payload, ("items", 2)) == (False, None)
    assert _lookup_value(payload, ("items", -1)) == (False, None)
    assert _lookup_value(payload, ("items", "wrong")) == (False, None)


@pytest.mark.unit
def test_set_value_builds_list_paths_and_rejects_conflicting_shapes() -> None:
    """Nested addressed writes construct missing containers but never coerce conflicts."""
    document: dict[str, Any] = {}

    _set_value(document, ("items", 1, "token"), "value")

    assert document == {"items": [None, {"token": "value"}]}

    with pytest.raises(ConfigurationApplyError):
        _set_value({}, (), "value")
    with pytest.raises(ConfigurationApplyError):
        _set_value({"items": "scalar"}, ("items", 0), "value")
    with pytest.raises(ConfigurationApplyError):
        _set_value({"items": []}, ("items", -1), "value")
    with pytest.raises(ConfigurationApplyError):
        _set_value({"items": ["scalar"]}, ("items", 0, "token"), "value")


@pytest.mark.unit
def test_apply_replacements_skips_unavailable_proposed_paths() -> None:
    """Internal copying still refuses an address with no separate proposed value."""
    candidate = {"token": "old"}

    changed = _apply_replacements(
        candidate,
        (("token",), ("missing",)),
        {"token": "new"},
    )

    assert changed == (("token",),)
    assert candidate == {"token": "new"}
