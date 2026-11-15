# Adaptive-difficulty nested contract fixtures

This reference describes SCE-003 policy and resolver cases.
The models are nested in `experiment-authoring-input-v1` and `experiment-run-v1`.
These are fragment fixtures, not another top-level contract.

- Policy inputs bind a versioned and digest-bound measurement-source definition
  separately from the exact evidence or derived-measure instance used at a
  decision cut.
- `positive.json` selects the declared harder follow-up at the exact threshold.
- `boundary.json` reaches the declared intervention-count terminal boundary.
- `unsupported.json` names a digest-bound evaluator profile the reference
  resolver does not implement and must not silently replace.
- `policy-violation.json` points a threshold rule at an undeclared action and
  must fail closed during model validation.

The [experiment reference](../../../../specs/formal/experiment-core/README.md)
defines the contract boundary.
`test_sce_003_adaptive_difficulty.py::test_positive_boundary_unsupported_and_policy_violation_fixtures`
checks these four outcomes.
Resolver selection does not perform the selected intervention.
