"""A case file that does not collect, for the issue #1919 design acceptance tests."""

import raes_missing_design_acceptance_module  # noqa: F401


def test_unreachable() -> None:
    assert True
