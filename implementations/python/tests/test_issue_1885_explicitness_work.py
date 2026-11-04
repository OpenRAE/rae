"""Concern classification retains leaves without quadratic path comparisons."""

from raes.explicitness import ExplicitnessRecord
from raes_contracts.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_processor.compiler.realization_concern_explicitness import semantic_explicitness_leaves
from raes_processor.semantics.realization_requirement import CompiledRealizationRequirement


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
    assert requirement.constraint_limit_message is None
