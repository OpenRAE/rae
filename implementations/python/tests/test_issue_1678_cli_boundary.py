"""The raes command reports unexpected failures without exception values (issue #1678)."""

import logging
import sys

import pytest
import raes_cli.entrypoint as cli_entrypoint
import raes_cli.sdl as sdl_commands
from typer.testing import CliRunner

SECRET = "sentinel-5c1e-secret"


@pytest.fixture(autouse=True)
def restore_root_logging():
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(level)


def test_unexpected_command_failure_exits_70_without_values(monkeypatch, capsys, tmp_path):
    source = tmp_path / "scenario.yaml"
    source.write_text("name: probe\n", encoding="utf-8")

    def _fail(*_args, **_kwargs):
        raise RuntimeError(f"defect with {SECRET}")

    monkeypatch.setattr(sdl_commands, "format_sdl_source", _fail)
    monkeypatch.setattr(sys, "argv", ["raes", "sdl", "format", str(source)])

    with pytest.raises(SystemExit) as exited:
        cli_entrypoint.main()

    captured = capsys.readouterr()
    assert exited.value.code == 70
    assert SECRET not in captured.out + captured.err
    assert "unexpected error" in captured.err
    assert "RuntimeError" in captured.err
    assert "Traceback (most recent call last; values omitted)" in captured.err


def test_log_level_option_sets_the_application_level_without_a_handler():
    from raes_cli.main import app

    handlers = list(logging.getLogger().handlers)
    result = CliRunner().invoke(app, ["--log-level", "debug", "sdl", "--help"])

    assert result.exit_code == 0
    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger().handlers == handlers


def test_log_level_option_rejects_an_unknown_level():
    from raes_cli.main import app

    result = CliRunner().invoke(app, ["--log-level", "verbose", "sdl", "--help"])

    assert result.exit_code == 2
