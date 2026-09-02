from api.connectors import _default_branch_first


def test_default_branch_is_first_without_dropping_provider_order():
    branches = ["develop", "main", "release"]
    assert _default_branch_first(branches, "main") == ["main", "develop", "release"]


def test_default_branch_is_added_when_provider_page_omits_it():
    branches = ["develop", "release"]
    assert _default_branch_first(branches, "main") == ["main", "develop", "release"]


def test_missing_default_branch_is_added_for_paginated_provider_results():
    branches = ["develop", "release"]
    assert _default_branch_first(branches, "trunk") == ["trunk", "develop", "release"]
