"""Shared operational logging keeps log records value-free (issue #1678)."""

import importlib.util
import io
import logging
import sys
from contextlib import contextmanager

import pytest
from raes_contracts.errors import ConflictError
from raes_contracts.operational_logging import (
    ForeignCodeFailure,
    ValueFreeFormatter,
    configure_application_logging,
    describe_exception,
    foreign_failure_record,
    get_logger,
    run_application,
    set_application_log_level,
)

SENTINEL = "sentinel-7f3a-value"
_LOGGER_NAME = "raes_tests.issue_1678"


@contextmanager
def _isolated_root_logging():
    """Isolate application handlers, then restore the host handlers and level."""

    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    for handler in handlers:
        if getattr(handler, "_raes_application_handler", False):
            root.removeHandler(handler)
    try:
        yield root
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(level)


@pytest.fixture
def root_logging():
    with _isolated_root_logging() as root:
        yield root


@pytest.fixture
def host_stream(root_logging):
    """Capture records the way a host does: a plain handler and the standard formatter."""

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root_logging.addHandler(handler)
    root_logging.setLevel(logging.DEBUG)
    return stream


def _raise_chained_error():
    try:
        raise KeyError(SENTINEL)
    except KeyError as exc:
        error = ValueError(f"wrapped {SENTINEL}")
        error.add_note(f"note {SENTINEL}")
        raise error from exc


def _raise_hidden_cause():
    try:
        raise LookupError(SENTINEL)
    except LookupError:
        raise ConflictError("refused") from None


def test_first_party_record_omits_exception_values_for_a_host_formatter(host_stream):
    try:
        _raise_chained_error()
    except ValueError:
        get_logger(_LOGGER_NAME).exception("operation failed")

    output = host_stream.getvalue()
    assert SENTINEL not in output
    assert "operation failed" in output
    assert "ValueError" in output
    assert "KeyError" in output
    assert "_raise_chained_error" in output
    assert "direct cause" in output


def test_record_keeps_the_types_and_locations_of_a_hidden_cause(host_stream):
    try:
        _raise_hidden_cause()
    except ConflictError:
        get_logger(_LOGGER_NAME).exception("operation refused")

    output = host_stream.getvalue()
    assert SENTINEL not in output
    assert "raes_contracts.errors.ConflictError" in output
    assert "LookupError" in output
    assert "_raise_hidden_cause" in output


def test_record_omits_exception_group_member_values(host_stream):
    group = ExceptionGroup("several", [ValueError(SENTINEL), ConflictError(SENTINEL)])
    try:
        raise group
    except ExceptionGroup:
        get_logger(_LOGGER_NAME).exception("several operations failed")

    output = host_stream.getvalue()
    assert SENTINEL not in output
    assert "ExceptionGroup" in output
    assert "ValueError" in output
    assert "ConflictError" in output


def test_record_escapes_control_characters_in_the_message(host_stream):
    get_logger(_LOGGER_NAME).warning("identifier %s", "a\r\nERROR root forged\x1b[31m\u2028end")

    output = host_stream.getvalue()
    assert output.count("\n") == 1
    assert "\r" not in output
    assert "\x1b" not in output
    assert "\u2028" not in output
    assert "\\r\\nERROR root forged\\x1b[31m\\u2028end" in output


def test_record_with_bad_arguments_does_not_raise(host_stream):
    get_logger(_LOGGER_NAME).warning("needs two values: %s %s", "one")

    output = host_stream.getvalue()
    assert "needs two values" in output
    assert "arguments did not match" in output


def test_record_with_a_failing_message_object_does_not_raise(host_stream):
    class Unprintable:
        def __str__(self):
            raise RuntimeError(SENTINEL)

    get_logger(_LOGGER_NAME).warning(Unprintable())

    output = host_stream.getvalue()
    assert SENTINEL not in output
    assert "<log message object>" in output


def test_record_omits_stack_information(host_stream):
    get_logger(_LOGGER_NAME).warning("with stack", stack_info=True)

    output = host_stream.getvalue()
    assert "with stack" in output
    assert "Stack (most recent call last)" not in output


def test_failing_sink_does_not_break_the_caller(root_logging, monkeypatch):
    class BrokenStream(io.StringIO):
        def write(self, text):
            raise OSError("sink unavailable")

    monkeypatch.setattr(logging, "raiseExceptions", False)
    root_logging.addHandler(logging.StreamHandler(BrokenStream()))

    get_logger(_LOGGER_NAME).error("still returns %s", "normally")


def test_get_logger_returns_the_named_logger_with_one_filter():
    first = get_logger(_LOGGER_NAME)
    second = get_logger(_LOGGER_NAME)

    assert first is second
    assert first is logging.getLogger(_LOGGER_NAME)
    assert len(first.filters) == 1


def test_value_free_formatter_omits_values_from_third_party_records():
    try:
        _raise_chained_error()
    except ValueError:
        record = logging.LogRecord("third.party", logging.ERROR, __file__, 1, "failed %s", ("x\ny",), sys.exc_info())
    record.exc_text = f"cached by another formatter {SENTINEL}"

    output = ValueFreeFormatter("%(name)s %(message)s").format(record)

    assert SENTINEL not in output
    assert output.startswith("third.party failed x\\ny")
    assert "KeyError" in output


def test_describe_exception_gives_types_and_locations_on_one_line():
    try:
        _raise_chained_error()
    except ValueError as exc:
        description = describe_exception(exc)

    assert "\n" not in description
    assert SENTINEL not in description
    assert description.startswith("ValueError (")
    assert "_raise_chained_error" in description
    assert "KeyError" in description


def test_application_configuration_is_repeatable_and_keeps_host_handlers(root_logging):
    host_handler = logging.NullHandler()
    root_logging.addHandler(host_handler)
    stream = io.StringIO()

    first = configure_application_logging(level="INFO", stream=stream)
    second = configure_application_logging(level="ERROR")

    assert first is second
    assert host_handler in root_logging.handlers
    assert sum(1 for handler in root_logging.handlers if handler is first) == 1
    assert isinstance(first.formatter, ValueFreeFormatter)
    assert root_logging.level == logging.ERROR


def test_diagnostic_capture_isolates_host_sink_and_preserves_value_free_records(root_logging, capsys):
    host_sink = io.StringIO()
    configure_application_logging(level="ERROR", stream=host_sink)
    host_handlers = list(root_logging.handlers)
    host_level = root_logging.level

    with _isolated_root_logging():
        configure_application_logging()
        try:
            _raise_chained_error()
        except ValueError:
            get_logger(_LOGGER_NAME).exception("isolated failure")

        captured = capsys.readouterr()
        assert "isolated failure" in captured.err
        assert "ValueError" in captured.err
        assert SENTINEL not in captured.err
        assert host_sink.getvalue() == ""

    assert root_logging.handlers == host_handlers
    assert root_logging.level == host_level
    get_logger(_LOGGER_NAME).error("host sink restored")
    assert "host sink restored" in host_sink.getvalue()


def test_application_configuration_writes_to_standard_error(root_logging, capsys):
    configure_application_logging()

    get_logger(_LOGGER_NAME).warning("to standard error")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "to standard error" in captured.err


def test_application_handler_writes_to_the_current_standard_error(root_logging, monkeypatch):
    configure_application_logging()
    replaced = io.StringIO()
    monkeypatch.setattr(sys, "stderr", replaced)

    get_logger(_LOGGER_NAME).warning("after the host replaced standard error")

    assert "after the host replaced standard error" in replaced.getvalue()


def test_application_handler_reports_a_failed_write_without_values(root_logging, monkeypatch):
    class ClosedStream(io.StringIO):
        def write(self, text):
            raise ValueError("I/O operation on closed file.")

    report = io.StringIO()
    configure_application_logging(stream=ClosedStream())
    monkeypatch.setattr(logging, "raiseExceptions", True)
    monkeypatch.setattr(sys, "stderr", report)

    try:
        raise RuntimeError(SENTINEL)
    except RuntimeError:
        get_logger(_LOGGER_NAME).exception("operation stopped")

    output = report.getvalue()
    assert output.startswith("--- Logging error ---\n")
    assert SENTINEL not in output
    assert "RuntimeError" in output
    assert "I/O operation" not in output


def test_level_change_installs_no_handler(root_logging):
    handlers = list(root_logging.handlers)

    set_application_log_level("debug")

    assert root_logging.handlers == handlers
    assert root_logging.level == logging.DEBUG


def test_application_configuration_rejects_an_unknown_level(root_logging):
    with pytest.raises(ValueError, match="log level"):
        configure_application_logging(level="VERBOSE")


def test_run_application_returns_the_status_of_main(root_logging):
    assert run_application(lambda: 3) == 3
    assert run_application(lambda: None) == 0


def test_run_application_logs_an_unexpected_failure_without_values(root_logging, capsys):
    def main():
        _raise_chained_error()

    status = run_application(main)

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert SENTINEL not in captured.err
    assert "unexpected error" in captured.err
    assert "_raise_chained_error" in captured.err


def test_run_application_returns_the_unexpected_status_that_the_caller_selects(root_logging, capsys):
    def main():
        raise RuntimeError(SENTINEL)

    assert run_application(main, unexpected_status=70) == 70
    assert SENTINEL not in capsys.readouterr().err


@pytest.mark.parametrize("signal", [SystemExit(4), KeyboardInterrupt()])
def test_run_application_lets_exit_and_interrupt_propagate(root_logging, signal):
    def main():
        raise signal

    with pytest.raises(type(signal)):
        run_application(main)


def test_foreign_failure_record_omits_the_foreign_type_message_chain_and_frames(host_stream, tmp_path):
    source = tmp_path / "provider_secret_module.py"
    source.write_text(
        "class ProviderSecretType(RuntimeError):\n"
        "    pass\n"
        "def provider_secret_function(secret):\n"
        "    try:\n"
        "        raise KeyError(secret)\n"
        "    except KeyError as cause:\n"
        "        raise ProviderSecretType(secret) from cause\n",
        encoding="utf-8",
    )
    caller_source = tmp_path / "raes_caller_probe.py"
    caller_source.write_text("def call_backend(function, secret):\n    return function(secret)\n", encoding="utf-8")
    provider = _load_module("provider_secret_module", source)
    caller = _load_module("raes_caller_probe", caller_source)

    try:
        caller.call_backend(provider.provider_secret_function, SENTINEL)
    except RuntimeError as exc:
        record = foreign_failure_record(exc)
        get_logger(_LOGGER_NAME).error("backend call failed", exc_info=record)

    output = host_stream.getvalue()
    assert isinstance(record, ForeignCodeFailure)
    for foreign in (SENTINEL, "ProviderSecretType", "provider_secret_function", "provider_secret_module", "KeyError"):
        assert foreign not in output
    assert "ForeignCodeFailure" in output
    assert "backend call failed" in output
    assert "call_backend" in output


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frame_locations_survive_interpreter_shutdown_state(monkeypatch):
    import sys

    from raes_contracts.operational_logging import describe_exception

    try:
        raise ValueError("shutdown-state-1678")
    except ValueError as caught:
        error = caught
    # At interpreter shutdown sys.path can be None; a finalizer that logs must not raise.
    monkeypatch.setattr(sys, "path", None)
    described = describe_exception(error)

    assert "ValueError" in described
    assert "shutdown-state-1678" not in described
