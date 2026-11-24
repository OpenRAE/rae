"""A case file that does not collect, for the issue #1919 design acceptance tests."""

import raes_missing_design_acceptance_module


def test_unreachable() -> None:
    assert raes_missing_design_acceptance_module is not None
