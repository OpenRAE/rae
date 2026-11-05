"""Architecture checksum exceptions must preserve credential detection."""

import json
import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_architecture_checksum_exception_preserves_secret_detection(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    scan = tmp_path / "scan"
    source = tmp_path / "source"
    model = source / "implementations/architecture.json"
    model.parent.mkdir(parents=True)
    checksum = "0123456789abcdef" * 4
    allowed = f'"existing_api_sha256": "{checksum}"\n"docs/decisions/issue-1825-public-go-api.md": "{checksum}"\n'
    # Synthetic scanner canaries, never usable credentials. Construct them so
    # this regression source contains no credential-shaped literal.
    generic_canary = "Ab9x" + "Q7mR" + "4vN2" + "kL8p" + "W6zT"
    aws_canary = "AKIA" + "QW7R" + "TM3P" + "X5NH" + "Z2VS"
    model.write_text(
        allowed
        + f'"api_key": "{checksum}"\n'
        + f'"existing_api_sha256": "{generic_canary}"\n'
        + f'"existing_api_sha256": "{aws_canary}"\n',
        encoding="utf-8",
    )
    for relative in ("other.json", "not-implementations/architecture.json", "implementations/architecture.json.bak"):
        elsewhere = source / relative
        elsewhere.parent.mkdir(parents=True, exist_ok=True)
        elsewhere.write_text(allowed, encoding="utf-8")
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
    # Match hygiene: a real scan directory containing file symlinks. Gitleaks
    # does not traverse a directory symlink supplied as the scan root.
    for original in source.rglob("*"):
        if original.is_file():
            linked = scan / original.relative_to(source)
            linked.parent.mkdir(parents=True, exist_ok=True)
            linked.symlink_to(original)
    report = tmp_path / "report.json"
    result = subprocess.run(
        [
            installed.stdout.strip(),
            "dir",
            "--config",
            str(repo / ".gitleaks.toml"),
            "--follow-symlinks",
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
    observed = {
        (Path(item["File"]).relative_to(source).as_posix(), item["StartLine"], item["RuleID"])
        for item in json.loads(report.read_text(encoding="utf-8"))
    }
    expected = {
        ("implementations/architecture.json", 3, "generic-api-key"),
        ("implementations/architecture.json", 4, "generic-api-key"),
        ("implementations/architecture.json", 5, "aws-access-token"),
    }
    for relative in ("other.json", "not-implementations/architecture.json", "implementations/architecture.json.bak"):
        expected.update((relative, line, "generic-api-key") for line in (1, 2))
    assert expected <= observed
    assert not any(path == "implementations/architecture.json" and line in (1, 2) for path, line, _ in observed)
