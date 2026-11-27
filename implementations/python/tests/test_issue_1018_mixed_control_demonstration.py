"""The mixed-control demonstration must preserve failures and fresh execution."""

from copy import deepcopy

import pytest


@pytest.fixture(scope="module")
def collected(tmp_path_factory):
    from mixed_control_demonstration import collect

    return collect(tmp_path_factory.mktemp("demonstration") / "first")


def test_collect_executes_mixed_and_control_paths_with_bounded_claims(collected):
    from mixed_control_demonstration import verify

    verify(collected)
    report = collected["reports"]["mixed"]
    outcomes = {case["name"]: case["outcome"] for case in report["cases"]}
    assert outcomes["edge-executes"] == "passed"
    assert outcomes["handoff-commits"] == "passed"
    assert outcomes["control-repeated-cycles"] == "passed"
    assert outcomes["combination-reusable-control-with-mixed-runtime"] == "unsupported"
    assert not report["passed"]
    assert all(not report["native_conformance"] for report in collected["reports"].values())
    assert collected["reports"]["effect"]["cases"][0]["modular_control"]["owner_outcomes"] == {"effect-1": "applied"}
    assert collected["reports"]["denial"]["cases"][0]["modular_control"]["actual_calls"] == {}


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "false-pass", "failed"])
def test_incomplete_or_misleading_matrix_fails(collected, mutation):
    from mixed_control_demonstration import verify

    altered = deepcopy(collected)
    cases = altered["reports"]["mixed"]["cases"]
    if mutation == "missing":
        cases.pop()
    elif mutation == "duplicate":
        cases.append(deepcopy(cases[0]))
    else:
        case = (
            next(item for item in cases if item["outcome"] == "unsupported") if mutation == "false-pass" else cases[0]
        )
        case.update(outcome="passed" if mutation == "false-pass" else "failed", passed=mutation == "false-pass")
    with pytest.raises(ValueError):
        verify(altered)


def test_collection_directory_cannot_be_reused(tmp_path):
    from mixed_control_demonstration import collect

    destination = tmp_path / "exists"
    destination.mkdir()
    with pytest.raises(FileExistsError):
        collect(destination)


@pytest.fixture(scope="module")
def recollected(tmp_path_factory):
    from mixed_control_demonstration import collect

    return collect(tmp_path_factory.mktemp("recollection") / "second")


def test_fresh_recollection_agrees_without_reusing_execution_identity(collected, recollected):
    from mixed_control_demonstration import compare

    result = compare(collected, recollected)
    assert result["agrees"]
    assert result["first_collection"] != result["second_collection"]
    original = {
        operation["operation_id"]
        for item in collected["observations"]["compositions"]
        for operation in item["operations"]
    }
    repeated = {
        operation["operation_id"]
        for item in recollected["observations"]["compositions"]
        for operation in item["operations"]
    }
    assert original.isdisjoint(repeated)


@pytest.mark.parametrize(
    "change", ["source", "environment", "configuration", "modular-authority", "readback", "reused"]
)
def test_reproduction_drift_is_rejected(collected, recollected, change):
    from mixed_control_demonstration import compare

    altered = deepcopy(recollected)
    if change == "source":
        altered["source"]["digest"] = "sha256:" + "0" * 64
    elif change == "environment":
        altered["environment"]["python"] = "different"
    elif change == "configuration":
        altered["reports"]["mixed"]["cases"][0]["configuration_digest"] = "sha256:" + "0" * 64
    elif change == "modular-authority":
        altered["reports"]["effect"]["cases"][0]["modular_control"]["artifact_digests"]["authority"] = (
            "sha256:" + "0" * 64
        )
    elif change == "readback":
        altered["observations"]["compositions"][0]["provider_readback"]["role_calls"].append("unexpected")
    else:
        altered["collection_id"] = collected["collection_id"]
    with pytest.raises(ValueError):
        compare(collected, altered)


def test_retagging_the_first_execution_is_not_reproduction(collected):
    from mixed_control_demonstration import compare

    copied = deepcopy(collected)
    copied["collection_id"] = "different-wrapper-with-the-same-execution"
    with pytest.raises(ValueError, match="execution"):
        compare(collected, copied)


@pytest.mark.parametrize("change", ["missing-observation", "prohibited-effect", "missing-stage"])
def test_runtime_facts_must_agree_with_report_claims(collected, change):
    from mixed_control_demonstration import verify

    altered = deepcopy(collected)
    observations = altered["observations"]["compositions"]
    if change == "missing-observation":
        altered["observations"]["compositions"] = [
            item for item in observations if item["case"] != "edge-missing-delivery"
        ]
    elif change == "prohibited-effect":
        item = next(item for item in observations if item["case"] == "edge-refused-after-time-grant")
        item["provider_readback"]["component_actions"]["emu"] = 1
    else:
        for item in observations:
            if item["case"] == "edge-executes":
                for operation in item["operations"]:
                    operation["stages"] = []
    with pytest.raises(ValueError):
        verify(altered)
