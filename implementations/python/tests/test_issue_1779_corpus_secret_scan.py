"""The parity corpus copies of the random-stream vectors must not hide other credentials."""

import json
import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_corpus_vector_exception_preserves_secret_detection(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    scan = tmp_path / "scan"
    corpus_input = scan / "implementations/go/internal/parity/testdata/inputs" / ("0" * 64)
    corpus_input.parent.mkdir(parents=True)
    # Synthetic scanner canaries, never usable credentials. Construct them so
    # this regression source itself does not contain a credential-shaped literal.
    vector = '"stream_key_hex": "' + "0123456789abcdef" * 4 + '"\n'
    generic_canary = "Ab9x" + "Q7mR" + "4vN2" + "kL8p" + "W6zT"
    corpus_input.write_text(vector + f'"api_key": "{generic_canary}"\n', encoding="utf-8")
    elsewhere = scan / "implementations/go/internal/parity/other.json"
    elsewhere.write_text(vector, encoding="utf-8")
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
    assert (corpus_input.name, 1, "generic-api-key") not in observed
    assert (corpus_input.name, 2, "generic-api-key") in observed
    assert (elsewhere.name, 1, "generic-api-key") in observed
