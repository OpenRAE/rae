"""Concern classification retains leaves without quadratic path comparisons."""

from pathlib import Path

import pytest
from raes.explicitness import ExplicitnessRecord
from raes_contracts.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_processor.compiler.realization_concern_explicitness import semantic_explicitness_leaves
from raes_processor.semantics.realization_requirement import CompiledRealizationRequirement
from tools.check_formal_semantic_validation import load_retest_bundle, replay_case


def test_leaf_selection_scales_with_input_paths():
    probes = []

    class CountedPath(str):
        def startswith(self, *args):
            probes.append(1)
            return super().startswith(*args)

    paths = [CountedPath(f"root.secrets[{index}].native_id") for index in range(512)]
    records = {path: ExplicitnessRecord(path, ExplicitnessClass.EXACT) for path in paths}
    leaves = semantic_explicitness_leaves(records, field_path="root", excluded_fields=frozenset())
    assert leaves == list(records.values())
    assert len(probes) < 5000


def test_leaf_selection_preserves_sibling_prefixes_indices_and_exclusions():
    paths = [
        "root",
        "root.item",
        "root.item2",
        "root.item[0]",
        "root.item[0].name",
        "root.item.description",
        "root.other",
    ]
    records = {path: ExplicitnessRecord(path, ExplicitnessClass.EXACT) for path in paths}
    records["elsewhere"] = ExplicitnessRecord("elsewhere", ExplicitnessClass.EXACT)
    leaves = semantic_explicitness_leaves(records, field_path="root", excluded_fields=frozenset({"description"}))
    assert [item.path for item in leaves] == ["root.item2", "root.item[0].name", "root.other"]


def test_compiled_requirement_keeps_original_positional_pending_argument():
    requirement = CompiledRealizationRequirement(
        "nodes.host.runtime.platform_applications",
        "provision.node.host",
        "runtime-realization",
        "runtime-platform-applications",
        ExplicitnessClass.EXACT,
        ExplicitnessProvenance.AUTHOR_DECLARED,
        None,
        False,
        None,
        None,
        None,
        None,
        None,
        (),
        (),
        None,
        None,
        None,
        False,
        True,
    )
    assert requirement.recursive_pending is True
    assert requirement.structure_error is False


@pytest.mark.parametrize("case_id", ["compile-repeatability-control", "compile-non-vacuity-control"])
def test_unchanged_compilation_keeps_retained_semantic_fingerprint(case_id):
    root = Path(__file__).resolve().parents[3]
    _, _, corpus, snapshot, _ = load_retest_bundle(root)
    case = next(item for item in corpus["cases"] if item["case_id"] == case_id)
    expected = next(item for item in snapshot["observations"] if item["case_id"] == case_id)
    actual = replay_case(root, case)
    assert actual["actual_outcome"] == expected["actual_outcome"]
    assert actual["result_digest"] == expected["result_digest"]
