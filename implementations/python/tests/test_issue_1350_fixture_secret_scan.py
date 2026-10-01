"""The retained DBOS fixture exception must not hide other credentials."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest


def test_retained_experiment_sources_match_recorded_hashes() -> None:
    research = Path(__file__).resolve().parents[3] / "docs/research/execution-architecture"
    evidence = json.loads((research / "evidence.json").read_text(encoding="utf-8"))
    for record in evidence["source_sha256"]:
        expected, filename = record.split(maxsplit=1)
        assert hashlib.sha256((research / "experiments" / filename).read_bytes()).hexdigest() == expected, filename


@pytest.mark.integration
def test_dbos_fixture_exception_preserves_secret_detection(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    scan = tmp_path / "scan"
    fixture = scan / "docs/research/execution-architecture/experiments/probe_dbos.py"
    fixture.parent.mkdir(parents=True)
    known_fixture = 'key = "' + "dbos-" + "r2-cancel" + '"\n'
    # Synthetic scanner canaries, never usable credentials. Construct them so
    # this regression source itself does not contain a credential-shaped literal.
    generic_canary = "Ab9x" + "Q7mR" + "4vN2" + "kL8p" + "W6zT"
    aws_canary = "AKIA" + "QW7R" + "TM3P" + "X5NH" + "Z2VS"
    fixture.write_text(
        known_fixture + f'api_key = "{generic_canary}"\naccess_id = "{aws_canary}"\n',
        encoding="utf-8",
    )
    elsewhere = scan / "other.py"
    elsewhere.write_text(known_fixture, encoding="utf-8")
    report = tmp_path / "report.json"
    # The installer belongs to the frozen tooling closure, not the runtime's
    # Python compatibility environment. Use the existing external-tool boundary.
    installed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repo / "implementations/tooling/python"),
            "--frozen",
            "--no-default-groups",
            "python",
            "-c",
            "from tools.gitleaks_tool import ensure_gitleaks; print(ensure_gitleaks())",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=90,
    )
    result = subprocess.run(
        [
            installed.stdout.strip(),
            "dir",
            "--config",
            str(repo / ".gitleaks.toml"),
            "--no-banner",
            "--redact",
            "--log-level",
            "error",
            "--report-format",
            "json",
            "--report-path",
            str(report),
            str(scan),
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 1
    findings = json.loads(report.read_text(encoding="utf-8"))
    observed = {(Path(item["File"]).name, item["StartLine"], item["RuleID"]) for item in findings}
    assert (fixture.name, 1, "generic-api-key") not in observed
    assert (fixture.name, 2, "generic-api-key") in observed
    assert (fixture.name, 3, "aws-access-token") in observed
    assert (elsewhere.name, 1, "generic-api-key") in observed
