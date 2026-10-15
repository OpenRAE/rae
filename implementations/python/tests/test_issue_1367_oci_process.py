"""The OCI command leaf bounds bytes/deadline and excludes inherited credentials."""

import sys
from time import monotonic

import pytest


def invoke(code, *, output_limit=64, seconds=2):
    from raes_reference_backend.drivers.oci_process import run_bounded_process

    return run_bounded_process(
        [sys.executable, "-c", code], deadline=monotonic() + seconds, max_output_bytes=output_limit
    )


def test_bounded_process_returns_only_admitted_output_and_no_host_credentials(monkeypatch):
    monkeypatch.setenv("RAES_TEST_1367_CREDENTIAL", "private-test-value")
    assert invoke("import os; print(os.environ.get('RAES_TEST_1367_CREDENTIAL', 'absent'))") == b"absent\n"


def test_excessive_native_output_is_refused_without_disclosing_it():
    with pytest.raises(ValueError, match="output bound") as error:
        invoke("print('private-test-output' * 10000)")
    assert "private-test-output" not in str(error.value)


def test_deadline_terminates_and_reaps_the_local_cli_process():
    start = monotonic()
    with pytest.raises(ValueError, match="deadline"):
        invoke("import time; time.sleep(10)", seconds=0.05)
    assert monotonic() - start < 2


def test_failed_native_command_has_a_value_free_error():
    with pytest.raises(ValueError) as error:
        invoke("import sys; print('private-test-output'); sys.exit(1)")
    assert "private-test-output" not in str(error.value)
