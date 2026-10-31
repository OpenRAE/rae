"""The independent driver measures every fixed comparison and checked witness."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from raes_contracts.errors import EvidenceIntegrityError
from test_issue_973_crossing_corpus import constructed as constructed
from test_issue_974_machine_check import result as result

ROOT = Path(__file__).resolve().parents[3]


def test_independent_inventory_rebuilds_the_exact_original_bundle(result):
    from implementations.formal.participant_crossing import counterexample_corpus as corpus
    from implementations.formal.participant_crossing import reproduction_checks as checks
    from tools.mcrl2_tool import Comparison

    calls = []

    def recorded(root, name, left, right, mode, *, formula=False):
        calls.append((name, mode, formula))
        if name == "baseline":
            assert left == result["abstract.aut"] and right == result["concrete.aut"]
            return Comparison(True, None)
        return corpus.compare(root, left, right, mode, formula=formula)

    assert checks.rebuild_bundle(ROOT, comparison=recorded) == result
    assert len(calls) == 46
    assert sum(formula for _, _, formula in calls) == 4


def test_always_accepting_native_checker_cannot_supply_a_measurement(constructed):
    from implementations.formal.participant_crossing import reproduction_checks as checks
    from tools.mcrl2_tool import Comparison

    with pytest.raises(EvidenceIntegrityError):
        checks.rebuild_bundle(ROOT, comparison=lambda *args, **kwargs: Comparison(True, None))


def test_prepared_pairs_are_only_fixed_complete_model_inputs(tmp_path):
    from implementations.formal.participant_crossing import export
    from implementations.formal.participant_crossing import reproduction_checks as checks

    checks.prepare_inputs(ROOT, tmp_path)
    model = export.build_bundle(ROOT)
    assert (tmp_path / "baseline/left.aut").read_bytes() == model["abstract.aut"]
    assert (tmp_path / "baseline/right.aut").read_bytes() == model["concrete.aut"]
    assert len(list(tmp_path.iterdir())) == 15
    assert {path.name for path in tmp_path.rglob("*.aut")} == {"left.aut", "right.aut"}


def test_changed_valid_input_is_refused_before_native_execution(tmp_path, monkeypatch):
    from implementations.formal.participant_crossing import export
    from implementations.formal.participant_crossing import reproduction_checks as checks

    checks.prepare_inputs(ROOT, tmp_path)
    model = export.build_bundle(ROOT)
    (tmp_path / "baseline/left.aut").write_bytes(model["concrete.aut"])
    original_read = checks.read_bytes

    def mounted_read(root, relative, **kwargs):
        assert root == Path("/checks")
        return original_read(tmp_path, relative, **kwargs)

    monkeypatch.setattr(checks, "read_bytes", mounted_read)
    monkeypatch.setattr(checks.os, "statvfs", lambda root: SimpleNamespace(f_flag=checks.os.ST_RDONLY))
    monkeypatch.setattr(
        checks, "require_mcrl2", lambda root: pytest.fail("altered inputs reached native tool admission")
    )
    with pytest.raises(EvidenceIntegrityError, match="input drift"):
        checks.compare(
            Path("/reproduction"), "baseline", model["abstract.aut"], model["concrete.aut"], "dpbranching-bisim"
        )
