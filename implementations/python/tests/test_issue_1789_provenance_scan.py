"""Only the three verified provenance checksums receive a scanner exception."""

import hashlib
import json
import re
import tomllib
from pathlib import Path


def test_provenance_checksum_exception_is_bound_to_sources_and_one_file():
    root = Path(__file__).resolve().parents[3]
    relative = "implementations/go/processor/analysis/testdata/cli-v2-provenance.json"
    manifest = json.loads((root / relative).read_text())
    config = tomllib.loads((root / ".gitleaks.toml").read_text())
    exceptions = [entry for entry in config["allowlists"] if entry["description"].startswith("Issue #1789:")]
    assert len(exceptions) == 1
    exception = exceptions[0]
    assert exception["targetRules"] == ["generic-api-key"]
    assert exception["condition"] == "AND"
    assert exception["regexTarget"] == "secret"
    names = {"account_credentials.py", "_bundle_access.py", "secret_references.py"}
    checksums = {value for path, value in manifest["source_sha256"].items() if Path(path).name in names}
    assert len(checksums) == len(exception["regexes"]) == 3
    for path, value in manifest["source_sha256"].items():
        if value in checksums:
            assert value == hashlib.sha256((root / path).read_bytes()).hexdigest()
            assert any(re.fullmatch(pattern, value) for pattern in exception["regexes"])
    for value in ["0" * 64, "not-a-checksum", *(value + "0" for value in checksums)]:
        assert not any(re.search(pattern, value) for pattern in exception["regexes"])
    for path in [relative, "/work/" + relative]:
        assert any(re.search(pattern, path) for pattern in exception["paths"])
    for path in [relative + ".bak", "not-" + relative, "other.json"]:
        assert not any(re.search(pattern, path) for pattern in exception["paths"])
