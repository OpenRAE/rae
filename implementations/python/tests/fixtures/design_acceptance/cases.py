"""Cases that tools/design_acceptance.py observes in the issue #1919 tests.

The file name does not match ``test_*.py``, so the normal suite does not collect it.
Some cases fail on purpose.
"""

import pytest


def test_failing_assertion() -> None:
    assert 1 + 1 == 3, "the acceptance behavior is missing"


def test_passing() -> None:
    assert 1 + 1 == 2


@pytest.mark.skip(reason="fixture skip")
def test_skipped() -> None:
    raise AssertionError("a skipped case does not run")


@pytest.mark.xfail(reason="fixture expected failure", strict=True)
def test_expected_failure() -> None:
    raise AssertionError("an expected failure")


def test_name_error() -> None:
    undefined_acceptance_name  # noqa: B018, F821


@pytest.fixture
def broken_setup() -> None:
    raise RuntimeError("the fixture setup failed")


def test_setup_error(broken_setup: None) -> None:
    assert broken_setup is None


@pytest.mark.integration
def test_integration_marked() -> None:
    assert True


@pytest.mark.parametrize("value", [1, 2])
def test_parametrized(value: int) -> None:
    assert value in (1, 2)


class TestFirst:
    def test_duplicate(self) -> None:
        assert True


class TestSecond:
    def test_duplicate(self) -> None:
        assert True
